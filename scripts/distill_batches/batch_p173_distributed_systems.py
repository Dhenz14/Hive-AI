"""Distributed systems — consensus (Raft simplified), distributed locks (Redis Redlock), leader election, vector clocks, CRDTs."""

PAIRS = [
    (
        "distributed/raft-consensus",
        "Implement a simplified Raft consensus algorithm in Python with leader election, log replication, and term management for a distributed key-value store.",
        '''Simplified Raft consensus implementation in Python:

```python
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Raft node states and data structures ──────────────────────────


class NodeState(str, Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    term: int
    index: int
    command: str        # e.g. "SET key value"
    committed: bool = False


@dataclass
class AppendEntriesRequest:
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[LogEntry]
    leader_commit: int


@dataclass
class AppendEntriesResponse:
    term: int
    success: bool
    match_index: int = 0


@dataclass
class VoteRequest:
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


@dataclass
class VoteResponse:
    term: int
    vote_granted: bool


class RaftNode:
    """Simplified Raft consensus node.

    Implements leader election, log replication, and commitment.
    Uses asyncio for timers and RPC simulation.
    """

    HEARTBEAT_INTERVAL = 0.15          # seconds
    ELECTION_TIMEOUT_MIN = 0.3
    ELECTION_TIMEOUT_MAX = 0.6

    def __init__(self, node_id: str, peers: list[str]) -> None:
        self.node_id = node_id
        self.peers = peers
        self.state = NodeState.FOLLOWER

        # Persistent state (would be on disk in production)
        self.current_term: int = 0
        self.voted_for: str | None = None
        self.log: list[LogEntry] = []

        # Volatile state
        self.commit_index: int = 0
        self.last_applied: int = 0

        # Leader-only volatile state
        self.next_index: dict[str, int] = {}
        self.match_index: dict[str, int] = {}

        # State machine (simple key-value store)
        self.state_machine: dict[str, str] = {}

        # Internal
        self._election_timer: asyncio.Task | None = None
        self._heartbeat_timer: asyncio.Task | None = None
        self._rpc_handler: Any = None   # injected transport

    # ── Election logic ────────────────────────────────────────────

    def _random_election_timeout(self) -> float:
        return random.uniform(
            self.ELECTION_TIMEOUT_MIN,
            self.ELECTION_TIMEOUT_MAX,
        )

    async def _reset_election_timer(self) -> None:
        if self._election_timer and not self._election_timer.done():
            self._election_timer.cancel()
        self._election_timer = asyncio.create_task(self._election_timeout_task())

    async def _election_timeout_task(self) -> None:
        await asyncio.sleep(self._random_election_timeout())
        if self.state != NodeState.LEADER:
            await self._start_election()

    async def _start_election(self) -> None:
        """Transition to candidate and request votes."""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        votes_received = 1                   # vote for self

        last_log_index = len(self.log)
        last_log_term = self.log[-1].term if self.log else 0

        request = VoteRequest(
            term=self.current_term,
            candidate_id=self.node_id,
            last_log_index=last_log_index,
            last_log_term=last_log_term,
        )

        async def request_vote(peer: str) -> bool:
            try:
                resp = await self._send_vote_request(peer, request)
                if resp.term > self.current_term:
                    self.current_term = resp.term
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    return False
                return resp.vote_granted
            except Exception:
                return False

        results = await asyncio.gather(
            *(request_vote(p) for p in self.peers),
            return_exceptions=True,
        )

        votes_received += sum(1 for r in results if r is True)
        majority = (len(self.peers) + 1) // 2 + 1

        if votes_received >= majority and self.state == NodeState.CANDIDATE:
            await self._become_leader()
        else:
            await self._reset_election_timer()

    async def _become_leader(self) -> None:
        self.state = NodeState.LEADER
        next_idx = len(self.log) + 1
        for peer in self.peers:
            self.next_index[peer] = next_idx
            self.match_index[peer] = 0
        await self._send_heartbeats()

    # ── Log replication ───────────────────────────────────────────

    async def client_request(self, command: str) -> bool:
        """Accept a client command (leader only)."""
        if self.state != NodeState.LEADER:
            return False

        entry = LogEntry(
            term=self.current_term,
            index=len(self.log) + 1,
            command=command,
        )
        self.log.append(entry)
        await self._replicate_log()
        return True

    async def _replicate_log(self) -> None:
        """Send AppendEntries to all peers and advance commit index."""
        async def replicate_to(peer: str) -> bool:
            ni = self.next_index.get(peer, 1)
            prev_index = ni - 1
            prev_term = self.log[prev_index - 1].term if prev_index > 0 else 0
            entries = self.log[ni - 1:]

            request = AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_index,
                prev_log_term=prev_term,
                entries=entries,
                leader_commit=self.commit_index,
            )
            try:
                resp = await self._send_append_entries(peer, request)
                if resp.success:
                    self.next_index[peer] = resp.match_index + 1
                    self.match_index[peer] = resp.match_index
                    return True
                else:
                    # Decrement next_index and retry
                    self.next_index[peer] = max(1, ni - 1)
                    return False
            except Exception:
                return False

        await asyncio.gather(*(replicate_to(p) for p in self.peers))
        self._advance_commit_index()

    def _advance_commit_index(self) -> None:
        """Advance commit_index if a majority has replicated."""
        for n in range(self.commit_index + 1, len(self.log) + 1):
            if self.log[n - 1].term != self.current_term:
                continue
            replicas = 1  # leader counts
            for peer in self.peers:
                if self.match_index.get(peer, 0) >= n:
                    replicas += 1
            if replicas > (len(self.peers) + 1) // 2:
                self.commit_index = n
                self.log[n - 1].committed = True

    # ── Handling incoming RPCs ────────────────────────────────────

    async def handle_vote_request(self, req: VoteRequest) -> VoteResponse:
        if req.term > self.current_term:
            self.current_term = req.term
            self.state = NodeState.FOLLOWER
            self.voted_for = None

        vote_granted = False
        if req.term >= self.current_term:
            if self.voted_for in (None, req.candidate_id):
                last_term = self.log[-1].term if self.log else 0
                last_idx = len(self.log)
                if (req.last_log_term > last_term or
                    (req.last_log_term == last_term and req.last_log_index >= last_idx)):
                    self.voted_for = req.candidate_id
                    vote_granted = True
                    await self._reset_election_timer()

        return VoteResponse(term=self.current_term, vote_granted=vote_granted)

    async def handle_append_entries(self, req: AppendEntriesRequest) -> AppendEntriesResponse:
        if req.term < self.current_term:
            return AppendEntriesResponse(term=self.current_term, success=False)

        self.current_term = req.term
        self.state = NodeState.FOLLOWER
        await self._reset_election_timer()

        # Check log consistency
        if req.prev_log_index > 0:
            if len(self.log) < req.prev_log_index:
                return AppendEntriesResponse(term=self.current_term, success=False)
            if self.log[req.prev_log_index - 1].term != req.prev_log_term:
                self.log = self.log[:req.prev_log_index - 1]
                return AppendEntriesResponse(term=self.current_term, success=False)

        # Append new entries
        for entry in req.entries:
            if entry.index <= len(self.log):
                if self.log[entry.index - 1].term != entry.term:
                    self.log = self.log[:entry.index - 1]
                    self.log.append(entry)
            else:
                self.log.append(entry)

        if req.leader_commit > self.commit_index:
            self.commit_index = min(req.leader_commit, len(self.log))

        self._apply_committed()
        return AppendEntriesResponse(
            term=self.current_term,
            success=True,
            match_index=len(self.log),
        )

    # ── State machine application ─────────────────────────────────

    def _apply_committed(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied - 1]
            self._apply_command(entry.command)

    def _apply_command(self, command: str) -> None:
        parts = command.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "SET":
            self.state_machine[parts[1]] = parts[2]
        elif len(parts) == 2 and parts[0] == "DEL":
            self.state_machine.pop(parts[1], None)

    # ── Stubs for network transport (inject real transport) ───────

    async def _send_vote_request(self, peer: str, req: VoteRequest) -> VoteResponse:
        raise NotImplementedError("Inject transport layer")

    async def _send_append_entries(self, peer: str, req: AppendEntriesRequest) -> AppendEntriesResponse:
        raise NotImplementedError("Inject transport layer")

    async def _send_heartbeats(self) -> None:
        while self.state == NodeState.LEADER:
            await self._replicate_log()
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
```

Key concepts in Raft consensus:

| Concept | Purpose | Implementation detail |
|---|---|---|
| Leader election | Single leader per term | Random election timeout, majority vote |
| Log replication | Consistent state across nodes | AppendEntries RPC with prev-log check |
| Term numbers | Logical clock for elections | Monotonically increasing, reject stale terms |
| Commit index | Durability guarantee | Advance when majority has replicated |
| Log matching | Consistency invariant | Entries at same index+term are identical |

Critical safety properties:
- **Election safety**: At most one leader per term (ensured by majority vote + single vote per term)
- **Log matching**: If two logs have same index and term, all preceding entries match
- **Leader completeness**: A committed entry appears in all future leaders\' logs
- **State machine safety**: All nodes apply same commands in same order
'''
    ),
    (
        "distributed/redis-redlock",
        "Implement the Redis Redlock distributed locking algorithm with proper fencing tokens, automatic renewal, and deadlock prevention across multiple Redis instances.",
        '''Redis Redlock distributed locking with fencing tokens and auto-renewal:

```python
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

import redis.asyncio as aioredis


@dataclass
class LockResult:
    acquired: bool
    fencing_token: int | None = None
    owner_id: str = ""
    validity_ms: int = 0


class RedlockInstance:
    """Single Redis instance lock operations with Lua scripts."""

    ACQUIRE_SCRIPT = """
    if redis.call("SET", KEYS[1], ARGV[1], "NX", "PX", ARGV[2]) then
        return redis.call("INCR", KEYS[2])
    end
    return nil
    """

    RELEASE_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        redis.call("DEL", KEYS[1])
        return 1
    end
    return 0
    """

    EXTEND_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("PEXPIRE", KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client
        self._acquire_sha: str | None = None
        self._release_sha: str | None = None
        self._extend_sha: str | None = None

    async def _load_scripts(self) -> None:
        if self._acquire_sha is None:
            self._acquire_sha = await self._client.script_load(self.ACQUIRE_SCRIPT)
            self._release_sha = await self._client.script_load(self.RELEASE_SCRIPT)
            self._extend_sha = await self._client.script_load(self.EXTEND_SCRIPT)

    async def acquire(
        self, resource: str, owner: str, ttl_ms: int,
    ) -> int | None:
        await self._load_scripts()
        fence_key = f"redlock:fence:{resource}"
        result = await self._client.evalsha(
            self._acquire_sha, 2,
            f"redlock:{resource}", fence_key,
            owner, str(ttl_ms),
        )
        return int(result) if result is not None else None

    async def release(self, resource: str, owner: str) -> bool:
        await self._load_scripts()
        result = await self._client.evalsha(
            self._release_sha, 1,
            f"redlock:{resource}",
            owner,
        )
        return result == 1

    async def extend(self, resource: str, owner: str, ttl_ms: int) -> bool:
        await self._load_scripts()
        result = await self._client.evalsha(
            self._extend_sha, 1,
            f"redlock:{resource}",
            owner, str(ttl_ms),
        )
        return result == 1


class Redlock:
    """Distributed lock across N Redis instances (Redlock algorithm).

    Acquires lock on majority of instances within a time budget.
    Uses fencing tokens to prevent stale lock holders from writing.
    """

    CLOCK_DRIFT_FACTOR = 0.01
    RETRY_DELAY_BASE_MS = 50

    def __init__(
        self,
        instances: list[aioredis.Redis],
        ttl_ms: int = 10_000,
        retry_count: int = 3,
    ) -> None:
        if len(instances) < 3:
            raise ValueError("Redlock requires at least 3 Redis instances")
        self._instances = [RedlockInstance(c) for c in instances]
        self._quorum = len(instances) // 2 + 1
        self._ttl_ms = ttl_ms
        self._retry_count = retry_count

    async def acquire(self, resource: str) -> LockResult:
        owner = str(uuid.uuid4())

        for attempt in range(self._retry_count):
            start_ms = _monotonic_ms()
            fencing_tokens: list[int] = []
            acquired_count = 0

            # Try to acquire on all instances concurrently
            tasks = [
                inst.acquire(resource, owner, self._ttl_ms)
                for inst in self._instances
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, int):
                    acquired_count += 1
                    fencing_tokens.append(result)

            elapsed_ms = _monotonic_ms() - start_ms
            drift = int(self._ttl_ms * self.CLOCK_DRIFT_FACTOR) + 2
            validity = self._ttl_ms - elapsed_ms - drift

            if acquired_count >= self._quorum and validity > 0:
                return LockResult(
                    acquired=True,
                    fencing_token=max(fencing_tokens),
                    owner_id=owner,
                    validity_ms=validity,
                )

            # Failed — release whatever we acquired
            await self._release_all(resource, owner)

            # Jittered backoff before retry
            jitter = self.RETRY_DELAY_BASE_MS * (attempt + 1)
            import random
            await asyncio.sleep(random.uniform(0, jitter) / 1000)

        return LockResult(acquired=False)

    async def release(self, resource: str, owner: str) -> None:
        await self._release_all(resource, owner)

    async def extend(self, resource: str, owner: str) -> bool:
        tasks = [
            inst.extend(resource, owner, self._ttl_ms)
            for inst in self._instances
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in results if r is True)
        return success_count >= self._quorum

    async def _release_all(self, resource: str, owner: str) -> None:
        tasks = [inst.release(resource, owner) for inst in self._instances]
        await asyncio.gather(*tasks, return_exceptions=True)

    @asynccontextmanager
    async def lock(
        self, resource: str, auto_extend: bool = True,
    ) -> AsyncGenerator[LockResult, None]:
        """Context manager that acquires, optionally auto-extends, and releases."""
        result = await self.acquire(resource)
        if not result.acquired:
            raise RuntimeError(f"Failed to acquire Redlock on '{resource}'")

        extend_task: asyncio.Task | None = None

        async def _auto_extend() -> None:
            interval = self._ttl_ms / 3 / 1000
            while True:
                await asyncio.sleep(interval)
                ok = await self.extend(resource, result.owner_id)
                if not ok:
                    break

        try:
            if auto_extend:
                extend_task = asyncio.create_task(_auto_extend())
            yield result
        finally:
            if extend_task:
                extend_task.cancel()
                try:
                    await extend_task
                except asyncio.CancelledError:
                    pass
            await self.release(resource, result.owner_id)


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


# ── Usage ─────────────────────────────────────────────────────────

async def process_with_lock(redlock: Redlock) -> None:
    async with redlock.lock("orders:batch-42") as lock_result:
        print(f"Acquired lock, fencing token: {lock_result.fencing_token}")
        # Use fencing token in downstream writes:
        # db.update({"_fencing_token": {"$lt": lock_result.fencing_token}}, ...)
        await asyncio.sleep(1)  # simulate work
```

Redlock safety analysis:

| Property | How Redlock ensures it |
|---|---|
| Mutual exclusion | Majority quorum (N/2+1) must grant lock |
| Deadlock freedom | TTL auto-expires; no indefinite holds |
| Fault tolerance | Tolerates minority instance failures |
| Fencing | Monotonic token prevents stale writes |
| Clock drift | Validity window subtracts drift estimate |

Important operational considerations:
- Use at least 5 Redis instances on separate machines for production
- Fencing tokens must be checked by the storage layer, not just the client
- Auto-extend keeps lock alive but check validity before long operations
- The algorithm assumes bounded clock drift between nodes
- Consider single-instance locks for simpler use cases where split-brain is acceptable
'''
    ),
    (
        "distributed/leader-election",
        "Implement leader election using etcd leases in Python with health monitoring, graceful handoff, and automatic failover for a distributed service.",
        '''Leader election with etcd leases, health monitoring, and failover:

```python
from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import etcd3


class LeaderStatus(str, Enum):
    FOLLOWER = "follower"
    LEADER = "leader"
    TRANSITIONING = "transitioning"


@dataclass
class ElectionConfig:
    election_key: str = "/services/myapp/leader"
    lease_ttl: int = 15               # seconds
    renewal_interval: float = 5.0     # renew lease every N seconds
    health_check_interval: float = 3.0
    max_missed_renewals: int = 2


@dataclass
class LeaderInfo:
    node_id: str
    address: str
    elected_at: float
    term: int


class LeaderElection:
    """Leader election using etcd leases.

    Uses etcd\'s compare-and-swap to atomically claim leadership.
    The leader holds a lease that must be renewed; if the leader
    dies, the lease expires and another node can claim leadership.
    """

    def __init__(
        self,
        node_id: str,
        address: str,
        config: ElectionConfig | None = None,
        etcd_host: str = "localhost",
        etcd_port: int = 2379,
    ) -> None:
        self.node_id = node_id
        self.address = address
        self.config = config or ElectionConfig()
        self.status = LeaderStatus.FOLLOWER
        self.current_leader: LeaderInfo | None = None
        self.term: int = 0

        self._client = etcd3.client(host=etcd_host, port=etcd_port)
        self._lease: Any = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {
            "on_elected": [],
            "on_demoted": [],
            "on_leader_changed": [],
        }
        self._health_checks: list[Callable[[], Coroutine[Any, Any, bool]]] = []

    # ── Public API ────────────────────────────────────────────────

    def on_elected(self, callback: Callable) -> None:
        self._callbacks["on_elected"].append(callback)

    def on_demoted(self, callback: Callable) -> None:
        self._callbacks["on_demoted"].append(callback)

    def on_leader_changed(self, callback: Callable) -> None:
        self._callbacks["on_leader_changed"].append(callback)

    def add_health_check(self, check: Callable[[], Coroutine[Any, Any, bool]]) -> None:
        self._health_checks.append(check)

    @property
    def is_leader(self) -> bool:
        return self.status == LeaderStatus.LEADER

    async def start(self) -> None:
        """Start the election loop."""
        self._running = True
        await asyncio.gather(
            self._election_loop(),
            self._health_monitor(),
            self._watch_leader(),
        )

    async def stop(self) -> None:
        """Graceful shutdown — resign leadership if held."""
        self._running = False
        if self.is_leader:
            await self._resign()

    async def _resign(self) -> None:
        """Voluntarily give up leadership."""
        self.status = LeaderStatus.TRANSITIONING
        try:
            self._client.delete(self.config.election_key)
            if self._lease:
                self._lease.revoke()
        except Exception:
            pass
        self.status = LeaderStatus.FOLLOWER
        await self._fire_callbacks("on_demoted")

    # ── Election loop ─────────────────────────────────────────────

    async def _election_loop(self) -> None:
        while self._running:
            if self.status == LeaderStatus.FOLLOWER:
                await self._try_become_leader()
            elif self.status == LeaderStatus.LEADER:
                await self._renew_lease()
            await asyncio.sleep(self.config.renewal_interval)

    async def _try_become_leader(self) -> None:
        try:
            self._lease = self._client.lease(self.config.lease_ttl)
            leader_value = f"{self.node_id}|{self.address}|{time.time()}"

            # Atomic compare-and-swap: create only if key doesn't exist
            success, _ = self._client.transaction(
                compare=[
                    self._client.transactions.create(self.config.election_key) == 0,
                ],
                success=[
                    self._client.transactions.put(
                        self.config.election_key,
                        leader_value,
                        self._lease,
                    ),
                ],
                failure=[],
            )

            if success:
                self.term += 1
                self.status = LeaderStatus.LEADER
                self.current_leader = LeaderInfo(
                    node_id=self.node_id,
                    address=self.address,
                    elected_at=time.time(),
                    term=self.term,
                )
                await self._fire_callbacks("on_elected")
            else:
                self._lease.revoke()
                self._lease = None
                self._read_current_leader()

        except Exception as e:
            print(f"Election attempt failed: {e}")
            if self._lease:
                try:
                    self._lease.revoke()
                except Exception:
                    pass
                self._lease = None

    async def _renew_lease(self) -> None:
        if not self._lease:
            self.status = LeaderStatus.FOLLOWER
            return
        try:
            self._lease.refresh()
        except Exception:
            self.status = LeaderStatus.FOLLOWER
            self._lease = None
            await self._fire_callbacks("on_demoted")

    def _read_current_leader(self) -> None:
        value, _ = self._client.get(self.config.election_key)
        if value:
            parts = value.decode().split("|")
            if len(parts) >= 3:
                self.current_leader = LeaderInfo(
                    node_id=parts[0],
                    address=parts[1],
                    elected_at=float(parts[2]),
                    term=self.term,
                )

    # ── Health monitoring ─────────────────────────────────────────

    async def _health_monitor(self) -> None:
        consecutive_failures = 0
        while self._running:
            if self.is_leader and self._health_checks:
                results = await asyncio.gather(
                    *(check() for check in self._health_checks),
                    return_exceptions=True,
                )
                all_healthy = all(
                    r is True for r in results if not isinstance(r, Exception)
                )
                if not all_healthy:
                    consecutive_failures += 1
                    if consecutive_failures >= self.config.max_missed_renewals:
                        print("Health checks failing — resigning leadership")
                        await self._resign()
                        consecutive_failures = 0
                else:
                    consecutive_failures = 0

            await asyncio.sleep(self.config.health_check_interval)

    async def _watch_leader(self) -> None:
        """Watch for leader key changes (deletions trigger re-election)."""
        while self._running:
            try:
                events_iterator, cancel = self._client.watch(
                    self.config.election_key,
                )
                for event in events_iterator:
                    if not self._running:
                        break
                    if hasattr(event, "type"):
                        self._read_current_leader()
                        await self._fire_callbacks("on_leader_changed")
                cancel()
            except Exception:
                await asyncio.sleep(1)

    # ── Callbacks ─────────────────────────────────────────────────

    async def _fire_callbacks(self, event: str) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                result = cb(self)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"Callback error for {event}: {e}")


# ── Usage example ─────────────────────────────────────────────────

async def main() -> None:
    election = LeaderElection(
        node_id="node-1",
        address="10.0.1.5:8080",
        config=ElectionConfig(
            election_key="/services/order-processor/leader",
            lease_ttl=15,
        ),
    )

    async def on_elected(node: LeaderElection) -> None:
        print(f"Node {node.node_id} became leader (term {node.term})")

    async def on_demoted(node: LeaderElection) -> None:
        print(f"Node {node.node_id} lost leadership")

    election.on_elected(on_elected)
    election.on_demoted(on_demoted)

    # Health check: can we reach the database?
    async def db_health() -> bool:
        return True  # replace with real check

    election.add_health_check(db_health)
    await election.start()
```

Leader election patterns comparison:

| Approach | Pros | Cons |
|---|---|---|
| etcd lease | Strong consistency, automatic expiry | Requires etcd cluster |
| ZooKeeper ephemeral | Battle-tested, sequential znodes | JVM dependency, complex |
| Redis SETNX | Simple, fast | No strong consistency guarantee |
| Raft built-in | No external deps | Complex to implement correctly |
| Kubernetes lease | Native k8s integration | Tied to k8s platform |

Key patterns:
- Always use TTL/leases to prevent zombie leaders
- Health checks allow voluntary resignation before lease expires
- Fencing tokens/terms prevent split-brain writes
- Graceful handoff reduces service disruption
- Watch mechanisms enable immediate failover detection
'''
    ),
    (
        "distributed/vector-clocks",
        "Implement vector clocks in Python for tracking causality in a distributed system, with conflict detection, clock merging, and happens-before relationship checking.",
        '''Vector clocks for causality tracking and conflict detection:

```python
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CausalOrder(str, Enum):
    BEFORE = "before"           # a happened before b
    AFTER = "after"             # a happened after b
    CONCURRENT = "concurrent"   # a and b are concurrent (conflict)
    EQUAL = "equal"             # same logical time


class VectorClock:
    """Vector clock for tracking causality across distributed nodes.

    Each node maintains a counter; the vector of all counters
    captures the causal history of an event.
    """

    __slots__ = ("_clocks",)

    def __init__(self, clocks: dict[str, int] | None = None) -> None:
        self._clocks: dict[str, int] = dict(clocks) if clocks else {}

    def increment(self, node_id: str) -> VectorClock:
        """Record a local event on the given node."""
        new = VectorClock(self._clocks)
        new._clocks[node_id] = new._clocks.get(node_id, 0) + 1
        return new

    def merge(self, other: VectorClock) -> VectorClock:
        """Merge two vector clocks (take element-wise max)."""
        all_nodes = set(self._clocks) | set(other._clocks)
        merged = {
            node: max(self._clocks.get(node, 0), other._clocks.get(node, 0))
            for node in all_nodes
        }
        return VectorClock(merged)

    def compare(self, other: VectorClock) -> CausalOrder:
        """Determine causal ordering between two vector clocks."""
        all_nodes = set(self._clocks) | set(other._clocks)
        has_less = False
        has_greater = False

        for node in all_nodes:
            a = self._clocks.get(node, 0)
            b = other._clocks.get(node, 0)
            if a < b:
                has_less = True
            elif a > b:
                has_greater = True

        if has_less and has_greater:
            return CausalOrder.CONCURRENT
        elif has_less:
            return CausalOrder.BEFORE
        elif has_greater:
            return CausalOrder.AFTER
        return CausalOrder.EQUAL

    def dominates(self, other: VectorClock) -> bool:
        """True if self happened strictly after other."""
        return self.compare(other) == CausalOrder.AFTER

    def get(self, node_id: str) -> int:
        return self._clocks.get(node_id, 0)

    def to_dict(self) -> dict[str, int]:
        return dict(self._clocks)

    def __repr__(self) -> str:
        entries = ", ".join(f"{k}:{v}" for k, v in sorted(self._clocks.items()))
        return f"VC({entries})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VectorClock):
            return NotImplemented
        return self.compare(other) == CausalOrder.EQUAL


# ── Versioned value with conflict detection ──────────────────────

@dataclass
class VersionedValue:
    """A value tagged with a vector clock for conflict detection."""
    value: Any
    clock: VectorClock
    timestamp: float = field(default_factory=time.time)
    node_id: str = ""


class ConflictResolver:
    """Strategies for resolving concurrent writes."""

    @staticmethod
    def last_writer_wins(versions: list[VersionedValue]) -> VersionedValue:
        """Simple LWW — pick the version with the latest wall-clock time."""
        return max(versions, key=lambda v: v.timestamp)

    @staticmethod
    def merge_sets(versions: list[VersionedValue]) -> VersionedValue:
        """For set-valued data, take the union of all concurrent versions."""
        merged_set: set = set()
        merged_clock = VectorClock()
        for v in versions:
            if isinstance(v.value, (set, frozenset, list)):
                merged_set |= set(v.value)
            merged_clock = merged_clock.merge(v.clock)
        return VersionedValue(value=merged_set, clock=merged_clock)

    @staticmethod
    def application_merge(
        versions: list[VersionedValue],
        merge_fn: Any,
    ) -> VersionedValue:
        """Custom merge function provided by the application."""
        merged_clock = VectorClock()
        values = []
        for v in versions:
            values.append(v.value)
            merged_clock = merged_clock.merge(v.clock)
        merged_value = merge_fn(values)
        return VersionedValue(value=merged_value, clock=merged_clock)


class VectorClockStore:
    """Key-value store with vector clock versioning.

    Maintains sibling versions for concurrent writes until resolved.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        # key -> list of concurrent VersionedValues
        self._store: dict[str, list[VersionedValue]] = {}

    def get(self, key: str) -> list[VersionedValue]:
        """Return all versions (siblings) for a key."""
        return list(self._store.get(key, []))

    def put(
        self,
        key: str,
        value: Any,
        context_clock: VectorClock | None = None,
    ) -> VersionedValue:
        """Write a value with vector clock tracking.

        If context_clock is provided, it means the client read first
        and is resolving any conflicts. Otherwise treat as a fresh write.
        """
        if context_clock:
            new_clock = context_clock.merge(
                self._get_merged_clock(key)
            ).increment(self.node_id)
        else:
            existing_clock = self._get_merged_clock(key)
            new_clock = existing_clock.increment(self.node_id)

        new_version = VersionedValue(
            value=value,
            clock=new_clock,
            node_id=self.node_id,
        )

        # Remove versions dominated by the new clock
        existing = self._store.get(key, [])
        surviving: list[VersionedValue] = []
        for v in existing:
            order = new_clock.compare(v.clock)
            if order != CausalOrder.AFTER and order != CausalOrder.EQUAL:
                surviving.append(v)  # concurrent — keep as sibling

        surviving.append(new_version)
        self._store[key] = surviving
        return new_version

    def _get_merged_clock(self, key: str) -> VectorClock:
        versions = self._store.get(key, [])
        clock = VectorClock()
        for v in versions:
            clock = clock.merge(v.clock)
        return clock

    def replicate_from(self, key: str, remote_version: VersionedValue) -> None:
        """Accept a replicated value from another node."""
        existing = self._store.get(key, [])
        surviving: list[VersionedValue] = []

        for v in existing:
            order = remote_version.clock.compare(v.clock)
            if order == CausalOrder.AFTER:
                continue  # remote dominates — drop local
            if order == CausalOrder.EQUAL:
                continue  # duplicate
            surviving.append(v)

        # Check if remote is dominated by any surviving version
        dominated = any(
            v.clock.dominates(remote_version.clock) for v in surviving
        )
        if not dominated:
            surviving.append(remote_version)

        self._store[key] = surviving


# ── Demo ──────────────────────────────────────────────────────────

def demo_vector_clocks() -> None:
    store_a = VectorClockStore("node-A")
    store_b = VectorClockStore("node-B")

    # Node A writes
    v1 = store_a.put("user:1", {"name": "Alice", "email": "alice@example.com"})
    print(f"A writes: {v1.clock}")  # VC(node-A:1)

    # Replicate to B
    store_b.replicate_from("user:1", v1)

    # Both nodes write concurrently (network partition)
    v2a = store_a.put("user:1", {"name": "Alice", "email": "alice@new.com"}, v1.clock)
    v2b = store_b.put("user:1", {"name": "Alice B", "email": "alice@example.com"}, v1.clock)

    print(f"A writes: {v2a.clock}")  # VC(node-A:2)
    print(f"B writes: {v2b.clock}")  # VC(node-A:1, node-B:1)

    # Detect conflict
    order = v2a.clock.compare(v2b.clock)
    print(f"Causal order: {order}")  # CONCURRENT — conflict!

    # Replicate and see siblings
    store_a.replicate_from("user:1", v2b)
    siblings = store_a.get("user:1")
    print(f"Siblings on A: {len(siblings)}")  # 2 concurrent versions

    # Resolve conflict with read-repair
    resolved = ConflictResolver.last_writer_wins(siblings)
    store_a.put("user:1", resolved.value, resolved.clock)
```

Causal ordering truth table:

| Relationship | Condition | Meaning |
|---|---|---|
| a BEFORE b | all a[i] <= b[i], some a[i] < b[i] | a causally precedes b |
| a AFTER b | all a[i] >= b[i], some a[i] > b[i] | a causally follows b |
| CONCURRENT | some a[i] < b[i] AND some a[j] > b[j] | no causal relationship — conflict |
| EQUAL | all a[i] == b[i] | same logical time |

Key design decisions:
- **Sibling retention**: Keep all concurrent versions until application resolves
- **Read-repair**: Client reads siblings, picks/merges, writes back with merged clock
- **Crdt alternative**: Use CRDTs (next pair) to auto-resolve without application logic
- **Clock pruning**: Prune entries for nodes that have left the cluster
- **Bounded clocks**: Use dotted version vectors to avoid clock growth
'''
    ),
    (
        "distributed/crdts",
        "Implement CRDTs (Conflict-free Replicated Data Types) in Python including G-Counter, PN-Counter, OR-Set, and LWW-Register for eventually consistent distributed state.",
        '''CRDTs for eventually consistent distributed state management:

```python
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class CRDT(ABC):
    """Base class for Conflict-free Replicated Data Types."""

    @abstractmethod
    def merge(self, other: CRDT) -> CRDT:
        """Merge with another replica. Must be commutative, associative, idempotent."""
        ...

    @abstractmethod
    def value(self) -> Any:
        """Read the current resolved value."""
        ...


# ── G-Counter (grow-only counter) ────────────────────────────────

class GCounter(CRDT):
    """Grow-only counter. Each node increments its own slot.

    merge = element-wise max
    value = sum of all slots
    """

    def __init__(self, node_id: str, counts: dict[str, int] | None = None) -> None:
        self.node_id = node_id
        self._counts: dict[str, int] = counts or {}

    def increment(self, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("GCounter only supports increments")
        self._counts[self.node_id] = self._counts.get(self.node_id, 0) + amount

    def merge(self, other: GCounter) -> GCounter:
        all_nodes = set(self._counts) | set(other._counts)
        merged = {
            n: max(self._counts.get(n, 0), other._counts.get(n, 0))
            for n in all_nodes
        }
        return GCounter(self.node_id, merged)

    def value(self) -> int:
        return sum(self._counts.values())

    def __repr__(self) -> str:
        return f"GCounter(value={self.value()}, nodes={self._counts})"


# ── PN-Counter (positive-negative counter) ───────────────────────

class PNCounter(CRDT):
    """Counter supporting both increments and decrements.

    Internally uses two G-Counters: one for increments, one for decrements.
    value = P.value() - N.value()
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._p = GCounter(node_id)
        self._n = GCounter(node_id)

    def increment(self, amount: int = 1) -> None:
        self._p.increment(amount)

    def decrement(self, amount: int = 1) -> None:
        self._n.increment(amount)

    def merge(self, other: PNCounter) -> PNCounter:
        result = PNCounter(self.node_id)
        result._p = self._p.merge(other._p)
        result._n = self._n.merge(other._n)
        return result

    def value(self) -> int:
        return self._p.value() - self._n.value()

    def __repr__(self) -> str:
        return f"PNCounter(value={self.value()}, +{self._p.value()}, -{self._n.value()})"


# ── LWW-Register (last-writer-wins register) ─────────────────────

@dataclass
class Timestamped(Generic[T]):
    value: T
    timestamp: float
    node_id: str


class LWWRegister(CRDT, Generic[T]):
    """Last-writer-wins register. Resolves conflicts by wall-clock timestamp.

    For ties, uses node_id as a deterministic tiebreaker.
    """

    def __init__(self, node_id: str, initial: T | None = None) -> None:
        self.node_id = node_id
        self._state: Timestamped[T | None] = Timestamped(
            value=initial,
            timestamp=time.time(),
            node_id=node_id,
        )

    def set(self, value: T) -> None:
        self._state = Timestamped(
            value=value,
            timestamp=time.time(),
            node_id=self.node_id,
        )

    def merge(self, other: LWWRegister[T]) -> LWWRegister[T]:
        result = LWWRegister[T](self.node_id)
        # Pick the one with the later timestamp; tiebreak by node_id
        if (other._state.timestamp > self._state.timestamp or
            (other._state.timestamp == self._state.timestamp and
             other._state.node_id > self._state.node_id)):
            result._state = other._state
        else:
            result._state = self._state
        return result

    def value(self) -> T | None:
        return self._state.value

    def __repr__(self) -> str:
        return f"LWWRegister(value={self._state.value}, ts={self._state.timestamp:.3f})"


# ── OR-Set (observed-remove set) ──────────────────────────────────

@dataclass(frozen=True)
class Tagged:
    """A value tagged with a unique ID for tracking add/remove."""
    value: Any
    tag: str = field(default_factory=lambda: str(uuid.uuid4()))


class ORSet(CRDT, Generic[T]):
    """Observed-Remove Set. Supports both add and remove operations.

    Each add creates a unique tag. Remove only removes tags that
    have been observed, so concurrent add+remove results in the
    element remaining (add wins semantics).
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._elements: set[Tagged] = set()    # (value, unique_tag)
        self._tombstones: set[Tagged] = set()  # removed tags

    def add(self, item: T) -> None:
        tagged = Tagged(value=item)
        self._elements.add(tagged)

    def remove(self, item: T) -> None:
        """Remove all observed instances of the item."""
        to_remove = {e for e in self._elements if e.value == item}
        self._elements -= to_remove
        self._tombstones |= to_remove

    def contains(self, item: T) -> bool:
        return any(e.value == item for e in self._elements)

    def merge(self, other: ORSet[T]) -> ORSet[T]:
        result = ORSet[T](self.node_id)

        # Union of all tombstones
        all_tombstones = self._tombstones | other._tombstones

        # Union of elements, minus anything tombstoned by either side
        all_elements = self._elements | other._elements
        result._elements = all_elements - all_tombstones
        result._tombstones = all_tombstones

        return result

    def value(self) -> set:
        return {e.value for e in self._elements}

    def __repr__(self) -> str:
        return f"ORSet({self.value()})"


# ── LWW-Element-Set ──────────────────────────────────────────────

class LWWElementSet(CRDT, Generic[T]):
    """Last-Writer-Wins Element Set.

    Maintains add-set and remove-set with timestamps.
    An element is in the set if its latest add timestamp > latest remove timestamp.
    """

    def __init__(self, node_id: str, bias: str = "add") -> None:
        self.node_id = node_id
        self._bias = bias  # "add" or "remove" for timestamp ties
        self._add_set: dict[Any, float] = {}
        self._remove_set: dict[Any, float] = {}

    def add(self, item: T) -> None:
        self._add_set[item] = time.time()

    def remove(self, item: T) -> None:
        self._remove_set[item] = time.time()

    def contains(self, item: T) -> bool:
        if item not in self._add_set:
            return False
        add_ts = self._add_set[item]
        remove_ts = self._remove_set.get(item, 0.0)
        if self._bias == "add":
            return add_ts >= remove_ts
        return add_ts > remove_ts

    def merge(self, other: LWWElementSet[T]) -> LWWElementSet[T]:
        result = LWWElementSet[T](self.node_id, self._bias)
        # Take max timestamp for each element in both add and remove sets
        for item in set(self._add_set) | set(other._add_set):
            result._add_set[item] = max(
                self._add_set.get(item, 0.0),
                other._add_set.get(item, 0.0),
            )
        for item in set(self._remove_set) | set(other._remove_set):
            result._remove_set[item] = max(
                self._remove_set.get(item, 0.0),
                other._remove_set.get(item, 0.0),
            )
        return result

    def value(self) -> set:
        return {item for item in self._add_set if self.contains(item)}

    def __repr__(self) -> str:
        return f"LWWElementSet({self.value()})"


# ── Demo: distributed shopping cart ──────────────────────────────

def demo_crdt_shopping_cart() -> None:
    """Two replicas of a shopping cart, modified concurrently."""
    cart_dc1 = ORSet[str]("dc-east")
    cart_dc2 = ORSet[str]("dc-west")

    # DC1: user adds items
    cart_dc1.add("widget-A")
    cart_dc1.add("widget-B")
    cart_dc1.add("gadget-C")

    # Sync DC1 -> DC2
    cart_dc2 = cart_dc2.merge(cart_dc1)

    # Concurrent modifications (network partition):
    # DC1: user removes widget-B
    cart_dc1.remove("widget-B")
    # DC2: user adds widget-D
    cart_dc2.add("widget-D")

    # Partition heals — merge both directions
    merged_1 = cart_dc1.merge(cart_dc2)
    merged_2 = cart_dc2.merge(cart_dc1)

    # Both replicas converge to the same set
    print(f"DC1 view: {merged_1.value()}")
    print(f"DC2 view: {merged_2.value()}")
    assert merged_1.value() == merged_2.value()
    # Result: {widget-A, gadget-C, widget-D}  (widget-B was removed)

    # ── Counter example ──
    views_dc1 = PNCounter("dc-east")
    views_dc2 = PNCounter("dc-west")

    views_dc1.increment(100)
    views_dc2.increment(50)
    views_dc1.decrement(3)

    merged_views = views_dc1.merge(views_dc2)
    print(f"Total views: {merged_views.value()}")  # 147
```

CRDT comparison table:

| CRDT Type | Operations | Conflict Resolution | Use Case |
|---|---|---|---|
| G-Counter | increment | Element-wise max | Page views, likes |
| PN-Counter | increment, decrement | Two G-Counters (P-N) | Inventory, votes |
| LWW-Register | set | Latest timestamp wins | User profile fields |
| OR-Set | add, remove | Add-wins (unique tags) | Shopping carts, tags |
| LWW-Element-Set | add, remove | Timestamp per element | Membership lists |

Convergence guarantees:
- **Commutativity**: merge(A, B) == merge(B, A) -- order doesn\'t matter
- **Associativity**: merge(merge(A, B), C) == merge(A, merge(B, C))
- **Idempotency**: merge(A, A) == A -- safe to re-deliver
- These three properties guarantee eventual convergence regardless of message ordering or duplication
'''
    ),
]
