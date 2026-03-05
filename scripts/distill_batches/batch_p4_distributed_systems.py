"""
Batch P4 — Distributed Systems Theory & Practice
Covers: consensus algorithms, distributed transactions, vector clocks,
consistent hashing, CRDTs.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "distributed-systems/raft-consensus",
        "Explain the Raft consensus algorithm in detail including leader election with randomized timeouts, log replication with commit indices, safety guarantees, membership changes with joint consensus, and provide a complete Python implementation of a Raft node with state machine, heartbeat mechanism, and vote handling suitable for understanding the protocol internals.",
        r"""# Raft Consensus: Understandable Distributed Consensus

## Why Raft Over Paxos

Raft was designed by Diego Ongaro and John Ousterhout specifically because Paxos is notoriously difficult to understand and implement correctly. Raft achieves the **same safety guarantees** as Paxos but decomposes the problem into three relatively independent subproblems: **leader election**, **log replication**, and **safety**. This decomposition is why Raft is the consensus algorithm behind etcd, CockroachDB, TiKV, and Consul.

**The fundamental problem**: How do N servers agree on a sequence of commands, even when some servers crash and the network drops or reorders messages? Raft guarantees that all non-crashed servers eventually agree on the same log of commands, and each server applies commands in the same order.

## Core Concepts

### Terms and Roles

Every Raft node is in one of three states: **Follower**, **Candidate**, or **Leader**. Time is divided into **terms** (logical clocks) — each term has at most one leader. If a node sees a higher term number, it immediately steps down to Follower.

### Leader Election

1. All nodes start as Followers with a randomized election timeout (150-300ms)
2. If a Follower receives no heartbeat before timeout, it becomes a Candidate
3. Candidate increments its term, votes for itself, and requests votes from all peers
4. A node grants its vote if: (a) it hasn't voted in this term yet, and (b) the candidate's log is at least as up-to-date as its own
5. Candidate becomes Leader when it receives votes from a majority

The **randomized timeout** is critical — it prevents split votes where multiple candidates run simultaneously. In practice, this resolves most elections in a single round.

## Complete Implementation

```python
"""Raft consensus protocol — educational implementation."""
from __future__ import annotations

import dataclasses
import enum
import logging
import random
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class Role(enum.Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclasses.dataclass
class LogEntry:
    """A single entry in the replicated log."""
    term: int
    index: int
    command: Any  # the state machine command

    def __repr__(self) -> str:
        return f"LogEntry(term={self.term}, idx={self.index}, cmd={self.command!r})"


@dataclasses.dataclass
class RequestVoteArgs:
    """Arguments for RequestVote RPC."""
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


@dataclasses.dataclass
class RequestVoteReply:
    """Reply to RequestVote RPC."""
    term: int
    vote_granted: bool


@dataclasses.dataclass
class AppendEntriesArgs:
    """Arguments for AppendEntries RPC (heartbeat + log replication)."""
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[LogEntry]
    leader_commit: int


@dataclasses.dataclass
class AppendEntriesReply:
    """Reply to AppendEntries RPC."""
    term: int
    success: bool
    # Optimization: on failure, tell leader where to back up to
    conflict_index: int = 0
    conflict_term: int = 0


class RaftNode:
    """A single Raft consensus node.

    This implementation covers the core protocol: leader election,
    log replication, and safety. It uses a message-passing interface
    rather than real RPCs for testability.

    The key invariant maintained: if two logs contain an entry with
    the same index and term, then all entries up to that point are
    identical across both logs. This is the Log Matching Property
    that guarantees consistency.
    """

    # Election timeout range in seconds
    ELECTION_TIMEOUT_MIN = 0.150
    ELECTION_TIMEOUT_MAX = 0.300
    HEARTBEAT_INTERVAL = 0.050

    def __init__(
        self,
        node_id: str,
        peers: list[str],
        apply_fn: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self.node_id = node_id
        self.peers = peers
        self.apply_fn = apply_fn or (lambda cmd: cmd)

        # Persistent state (must survive restarts)
        self.current_term: int = 0
        self.voted_for: Optional[str] = None
        self.log: list[LogEntry] = []  # 0-indexed internally

        # Volatile state
        self.role: Role = Role.FOLLOWER
        self.commit_index: int = -1
        self.last_applied: int = -1

        # Leader-only volatile state
        self.next_index: dict[str, int] = {}  # per-peer
        self.match_index: dict[str, int] = {}  # per-peer

        # Timing
        self._election_deadline = self._new_election_deadline()
        self._last_heartbeat = 0.0

        # Vote tracking for current election
        self._votes_received: set[str] = set()

        # Message outbox (collected by the test harness / network layer)
        self.outbox: list[tuple[str, Any]] = []

    @property
    def majority(self) -> int:
        """Number of nodes needed for a majority (including self)."""
        return (len(self.peers) + 1) // 2 + 1

    def _new_election_deadline(self) -> float:
        """Randomized election timeout — this prevents split votes.

        The randomization is the simplest mechanism in Raft and arguably
        the most important. Without it, all followers would timeout
        simultaneously and split the vote indefinitely.
        """
        timeout = random.uniform(
            self.ELECTION_TIMEOUT_MIN,
            self.ELECTION_TIMEOUT_MAX,
        )
        return time.monotonic() + timeout

    # --- Log helpers ---

    def _last_log_index(self) -> int:
        return len(self.log) - 1

    def _last_log_term(self) -> int:
        if not self.log:
            return -1
        return self.log[-1].term

    def _log_term_at(self, index: int) -> int:
        if index < 0 or index >= len(self.log):
            return -1
        return self.log[index].term

    # --- Tick (called periodically by the event loop) ---

    def tick(self) -> None:
        """Advance the node's timer. Call this every ~10ms.

        This drives leader election timeouts and heartbeat sending.
        In production Raft implementations, this is driven by a
        ticker goroutine (Go) or async timer (Python/Rust).
        """
        now = time.monotonic()

        if self.role == Role.LEADER:
            if now - self._last_heartbeat >= self.HEARTBEAT_INTERVAL:
                self._send_heartbeats()
                self._last_heartbeat = now
        else:
            if now >= self._election_deadline:
                self._start_election()

    # --- Leader Election ---

    def _start_election(self) -> None:
        """Transition to Candidate and request votes from all peers.

        Raft's election safety guarantee: at most one leader per term.
        This follows because each node votes for at most one candidate
        per term, and a candidate needs a majority to win.
        """
        self.current_term += 1
        self.role = Role.CANDIDATE
        self.voted_for = self.node_id
        self._votes_received = {self.node_id}  # vote for self
        self._election_deadline = self._new_election_deadline()

        logger.info(
            f"[{self.node_id}] Starting election for term {self.current_term}"
        )

        args = RequestVoteArgs(
            term=self.current_term,
            candidate_id=self.node_id,
            last_log_index=self._last_log_index(),
            last_log_term=self._last_log_term(),
        )

        for peer in self.peers:
            self.outbox.append((peer, ("request_vote", args)))

    def handle_request_vote(self, args: RequestVoteArgs) -> RequestVoteReply:
        """Handle an incoming RequestVote RPC.

        A node grants its vote if:
        1. The candidate's term >= our term
        2. We haven't already voted for someone else this term
        3. The candidate's log is at least as up-to-date as ours

        Condition 3 is the Election Restriction — it ensures the leader
        always has all committed entries. This is what makes Raft safe:
        a candidate with a stale log cannot win an election.
        """
        if args.term > self.current_term:
            self._step_down(args.term)

        if args.term < self.current_term:
            return RequestVoteReply(term=self.current_term, vote_granted=False)

        # Check if we can vote for this candidate
        can_vote = (
            self.voted_for is None or self.voted_for == args.candidate_id
        )

        # Election Restriction: candidate's log must be at least as current
        log_ok = (
            args.last_log_term > self._last_log_term()
            or (
                args.last_log_term == self._last_log_term()
                and args.last_log_index >= self._last_log_index()
            )
        )

        if can_vote and log_ok:
            self.voted_for = args.candidate_id
            self._election_deadline = self._new_election_deadline()
            return RequestVoteReply(term=self.current_term, vote_granted=True)

        return RequestVoteReply(term=self.current_term, vote_granted=False)

    def handle_vote_reply(self, reply: RequestVoteReply, from_peer: str) -> None:
        """Process a vote reply. Become leader if we have majority."""
        if reply.term > self.current_term:
            self._step_down(reply.term)
            return

        if self.role != Role.CANDIDATE or reply.term != self.current_term:
            return

        if reply.vote_granted:
            self._votes_received.add(from_peer)
            if len(self._votes_received) >= self.majority:
                self._become_leader()

    def _become_leader(self) -> None:
        """Transition to Leader state and initialize peer tracking."""
        self.role = Role.LEADER
        logger.info(
            f"[{self.node_id}] Became leader for term {self.current_term}"
        )

        # Initialize next_index to end of our log (optimistic)
        # and match_index to -1 (pessimistic)
        for peer in self.peers:
            self.next_index[peer] = len(self.log)
            self.match_index[peer] = -1

        # Send initial heartbeats immediately
        self._send_heartbeats()

    # --- Log Replication ---

    def _send_heartbeats(self) -> None:
        """Send AppendEntries RPCs to all peers.

        These serve dual purpose: heartbeat (preventing elections)
        and log replication (catching up followers).
        """
        for peer in self.peers:
            next_idx = self.next_index.get(peer, len(self.log))
            prev_idx = next_idx - 1
            prev_term = self._log_term_at(prev_idx)

            entries = self.log[next_idx:] if next_idx < len(self.log) else []

            args = AppendEntriesArgs(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_idx,
                prev_log_term=prev_term,
                entries=entries,
                leader_commit=self.commit_index,
            )
            self.outbox.append((peer, ("append_entries", args)))

    def handle_append_entries(self, args: AppendEntriesArgs) -> AppendEntriesReply:
        """Handle incoming AppendEntries RPC (heartbeat + replication).

        The Log Matching Property is enforced here: we only accept
        entries if our log matches the leader's at prev_log_index.
        If it doesn't, we tell the leader to back up.
        """
        if args.term > self.current_term:
            self._step_down(args.term)
        elif args.term == self.current_term and self.role == Role.CANDIDATE:
            self._step_down(args.term)

        # Reset election timer on valid heartbeat
        self._election_deadline = self._new_election_deadline()

        if args.term < self.current_term:
            return AppendEntriesReply(
                term=self.current_term, success=False
            )

        # Check log consistency at prev_log_index
        if args.prev_log_index >= 0:
            if args.prev_log_index >= len(self.log):
                return AppendEntriesReply(
                    term=self.current_term,
                    success=False,
                    conflict_index=len(self.log),
                )
            if self.log[args.prev_log_index].term != args.prev_log_term:
                # Conflict — find the first index of the conflicting term
                conflict_term = self.log[args.prev_log_index].term
                conflict_idx = args.prev_log_index
                while conflict_idx > 0 and self.log[conflict_idx - 1].term == conflict_term:
                    conflict_idx -= 1
                # Truncate our log at the conflict point
                self.log = self.log[:args.prev_log_index]
                return AppendEntriesReply(
                    term=self.current_term,
                    success=False,
                    conflict_index=conflict_idx,
                    conflict_term=conflict_term,
                )

        # Append new entries (overwriting conflicts)
        for entry in args.entries:
            idx = entry.index
            if idx < len(self.log):
                if self.log[idx].term != entry.term:
                    self.log = self.log[:idx]
                    self.log.append(entry)
                # else: already have this entry, skip
            else:
                self.log.append(entry)

        # Update commit index
        if args.leader_commit > self.commit_index:
            self.commit_index = min(
                args.leader_commit, len(self.log) - 1
            )
            self._apply_committed()

        return AppendEntriesReply(term=self.current_term, success=True)

    def handle_append_reply(
        self, reply: AppendEntriesReply, from_peer: str
    ) -> None:
        """Process AppendEntries reply and advance commit index."""
        if reply.term > self.current_term:
            self._step_down(reply.term)
            return

        if self.role != Role.LEADER:
            return

        if reply.success:
            # Advance next_index and match_index for this peer
            if from_peer in self.next_index:
                self.match_index[from_peer] = self.next_index[from_peer] - 1 + max(
                    1, self.next_index.get(from_peer, 0)
                )
                # Simplified: just set to end of log
                self.next_index[from_peer] = len(self.log)
                self.match_index[from_peer] = len(self.log) - 1

            self._advance_commit_index()
        else:
            # Decrement next_index and retry
            if reply.conflict_index > 0:
                self.next_index[from_peer] = reply.conflict_index
            else:
                self.next_index[from_peer] = max(
                    0, self.next_index.get(from_peer, 1) - 1
                )

    # --- Client Interface ---

    def propose(self, command: Any) -> bool:
        """Propose a new command to the replicated log.

        Only the leader can accept proposals. Clients must find the
        leader (by trying nodes or following redirects) and retry
        if the leader changes.

        Returns True if this node is the leader and accepted the proposal.
        """
        if self.role != Role.LEADER:
            return False

        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command,
        )
        self.log.append(entry)
        self.match_index[self.node_id] = len(self.log) - 1

        # Replicate immediately
        self._send_heartbeats()
        return True

    # --- Internal helpers ---

    def _step_down(self, new_term: int) -> None:
        """Step down to Follower when we see a higher term."""
        self.current_term = new_term
        self.role = Role.FOLLOWER
        self.voted_for = None
        self._election_deadline = self._new_election_deadline()

    def _advance_commit_index(self) -> None:
        """Leader: advance commit_index based on majority replication.

        A log entry is committed when it's replicated to a majority
        AND it was created in the leader's current term. This second
        condition prevents the "Figure 8" problem from the Raft paper.
        """
        for n in range(len(self.log) - 1, self.commit_index, -1):
            if self.log[n].term != self.current_term:
                continue  # Only commit entries from current term

            replicated_count = 1  # count self
            for peer in self.peers:
                if self.match_index.get(peer, -1) >= n:
                    replicated_count += 1

            if replicated_count >= self.majority:
                self.commit_index = n
                self._apply_committed()
                break

    def _apply_committed(self) -> None:
        """Apply committed but unapplied entries to the state machine."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            result = self.apply_fn(entry.command)
            logger.debug(
                f"[{self.node_id}] Applied entry {entry.index}: "
                f"{entry.command} -> {result}"
            )


def test_raft_election():
    """Test that a 3-node cluster elects a leader."""
    nodes = {
        "node1": RaftNode("node1", ["node2", "node3"]),
        "node2": RaftNode("node2", ["node1", "node3"]),
        "node3": RaftNode("node3", ["node1", "node2"]),
    }

    # Simulate ticks until one node starts an election
    # Force node1 to have shortest timeout
    nodes["node1"]._election_deadline = time.monotonic()

    nodes["node1"].tick()  # starts election

    # Process vote requests
    for target, msg in nodes["node1"].outbox:
        msg_type, args = msg
        if msg_type == "request_vote":
            reply = nodes[target].handle_request_vote(args)
            nodes["node1"].handle_vote_reply(reply, target)

    assert nodes["node1"].role == Role.LEADER, "node1 should be leader"
    assert nodes["node1"].current_term == 1
    print("Election test passed: node1 elected leader in term 1")


def test_log_replication():
    """Test that the leader replicates log entries to followers."""
    state_machine: dict[str, str] = {}

    def apply_cmd(cmd: dict) -> None:
        state_machine[cmd["key"]] = cmd["value"]

    nodes = {
        "n1": RaftNode("n1", ["n2", "n3"], apply_fn=apply_cmd),
        "n2": RaftNode("n2", ["n1", "n3"], apply_fn=apply_cmd),
        "n3": RaftNode("n3", ["n1", "n2"], apply_fn=apply_cmd),
    }

    # Make n1 leader directly for testing
    nodes["n1"].role = Role.LEADER
    nodes["n1"].current_term = 1
    for peer in ["n2", "n3"]:
        nodes["n1"].next_index[peer] = 0
        nodes["n1"].match_index[peer] = -1

    # Propose a command
    assert nodes["n1"].propose({"key": "x", "value": "42"})
    assert len(nodes["n1"].log) == 1

    # Process AppendEntries
    for target, msg in nodes["n1"].outbox:
        msg_type, args = msg
        if msg_type == "append_entries":
            reply = nodes[target].handle_append_entries(args)
            nodes["n1"].handle_append_reply(reply, target)

    # After majority replication, entry should be committed
    assert nodes["n1"].commit_index >= 0, "Leader should have committed"
    print("Log replication test passed")


if __name__ == "__main__":
    test_raft_election()
    test_log_replication()
```

## Safety Guarantees

Raft provides five guarantees, each enforced by a specific mechanism:

| Property | Guarantee | Mechanism |
|----------|-----------|-----------|
| **Election Safety** | At most one leader per term | Each node votes once per term + majority required |
| **Leader Append-Only** | Leader never overwrites/deletes its log | Leader only appends entries |
| **Log Matching** | Same index+term → identical prefix | AppendEntries consistency check |
| **Leader Completeness** | Committed entries appear in all future leaders | Election Restriction (vote only for up-to-date candidates) |
| **State Machine Safety** | All servers apply same command at each index | Committed = replicated to majority + same term |

## Common Pitfalls in Raft Implementations

1. **Forgetting the "current term" check**: Every RPC handler must check if the message's term is stale. This is the #1 source of bugs in Raft implementations because it's easy to miss in one of many code paths.

2. **Not persisting state before responding**: `currentTerm`, `votedFor`, and `log` must be persisted to disk before sending any RPC response. Otherwise, a crash and restart can violate the "vote once per term" invariant.

3. **The Figure 8 problem**: A leader must not commit entries from previous terms by counting replicas alone. It can only commit entries from its own term — which implicitly commits all prior entries. Ignoring this leads to committed entries being overwritten.

4. **Linearizable reads**: A naive implementation where the leader serves reads directly can return stale data if a network partition causes a new leader to be elected. Production implementations use **ReadIndex** (leader confirms it's still leader before reading) or **lease-based reads** (time-bounded leader lease).

## Key Takeaways

- Raft decomposes consensus into **leader election**, **log replication**, and **safety** — making it significantly easier to implement correctly than Paxos
- **Randomized election timeouts** prevent split votes and are the simplest yet most critical mechanism in the protocol
- The **Election Restriction** (only vote for candidates with up-to-date logs) is what ensures committed entries are never lost — this is Raft's core safety invariant
- Production Raft implementations need additional features: **log compaction** (snapshotting), **membership changes** (joint consensus), and **linearizable reads** — each adding significant complexity
- Performance in production: Raft typically achieves **10,000-100,000 writes/second** depending on entry size, network latency, and disk sync policy
"""
    ),
    (
        "distributed-systems/consistent-hashing",
        "Explain consistent hashing for distributed systems including the ring-based algorithm, virtual nodes for load balancing, bounded-load consistent hashing, and provide a production-grade Python implementation with jump consistent hashing comparison, rebalancing metrics, and handling of node failures with data migration strategies.",
        r"""# Consistent Hashing: The Foundation of Distributed Data Systems

## Why Simple Hashing Fails

With N nodes and simple modular hashing (`hash(key) % N`), adding or removing one node remaps **nearly all keys** — requiring massive data migration. Consistent hashing solves this: when a node is added or removed, only **K/N keys** need to move (where K is total keys and N is total nodes). This property makes consistent hashing the backbone of DynamoDB, Cassandra, Memcached, and every content delivery network.

## The Ring Algorithm

Map both nodes and keys to positions on a circular hash space (0 to 2^32-1). Each key is assigned to the first node encountered when walking clockwise from the key's hash position. This means adding a node only affects keys between it and its predecessor — all other mappings remain stable.

**The load balancing problem**: With few physical nodes, the hash ring can become unbalanced — one node might own 60% of the keyspace. Virtual nodes solve this by mapping each physical node to many positions on the ring.

```python
"""Production-grade consistent hashing with virtual nodes and metrics."""
from __future__ import annotations

import bisect
import dataclasses
import hashlib
import math
import statistics
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclasses.dataclass
class NodeStats:
    """Statistics for a single node."""
    node_id: str
    num_keys: int = 0
    num_virtual_nodes: int = 0
    load_fraction: float = 0.0
    keyspace_fraction: float = 0.0


class ConsistentHashRing(Generic[T]):
    """Consistent hash ring with virtual nodes and bounded load.

    Virtual nodes dramatically improve load balance. With V virtual
    nodes per physical node, the standard deviation of load is
    O(1/sqrt(V*N)) — meaning 150 virtual nodes with 10 physical
    nodes gives ~1% standard deviation. Without virtual nodes,
    load imbalance can reach 50%+.

    The bounded-load extension (Mirrokni et al., 2018) adds a hard
    upper bound: no node handles more than (1 + epsilon) * average_load.
    This is critical for preventing hotspots in production.
    """

    def __init__(
        self,
        virtual_nodes: int = 150,
        load_bound_epsilon: float = 0.25,
    ) -> None:
        self.virtual_nodes = virtual_nodes
        self.load_bound_epsilon = load_bound_epsilon

        # Core ring data structures
        self._ring: dict[int, str] = {}  # hash position -> node_id
        self._sorted_keys: list[int] = []  # sorted hash positions
        self._nodes: dict[str, T] = {}  # node_id -> node metadata

        # Load tracking for bounded-load consistent hashing
        self._node_loads: dict[str, int] = {}  # node_id -> current load

    def _hash(self, key: str) -> int:
        """Compute hash position on the ring.

        Using MD5 for good distribution (not cryptographic security).
        SHA-256 would also work but is slower for no benefit here.
        We take the first 4 bytes as a 32-bit integer.
        """
        digest = hashlib.md5(key.encode()).digest()
        return int.from_bytes(digest[:4], byteorder="big")

    def add_node(self, node_id: str, metadata: Optional[T] = None) -> list[str]:
        """Add a node to the ring with virtual nodes.

        Returns list of key ranges that should be migrated TO this node
        from their current owners. In production, this triggers a
        background rebalancing process.
        """
        if node_id in self._nodes:
            raise ValueError(f"Node {node_id} already exists in the ring")

        self._nodes[node_id] = metadata
        self._node_loads[node_id] = 0
        affected_ranges = []

        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:vn{i}"
            hash_val = self._hash(virtual_key)

            # Track what range this virtual node takes over
            if self._sorted_keys:
                pos = bisect.bisect_right(self._sorted_keys, hash_val)
                if pos < len(self._sorted_keys):
                    old_owner = self._ring[self._sorted_keys[pos % len(self._sorted_keys)]]
                    affected_ranges.append(
                        f"range before {hash_val} migrates from {old_owner} to {node_id}"
                    )

            self._ring[hash_val] = node_id
            bisect.insort(self._sorted_keys, hash_val)

        return affected_ranges

    def remove_node(self, node_id: str) -> dict[str, str]:
        """Remove a node, returning migration map: range -> new_owner.

        All keys owned by the removed node must be migrated to their
        new owners (the next node clockwise for each virtual node's
        range). This is why consistent hashing is better than modular
        hashing — only this node's keys move, not everyone's.
        """
        if node_id not in self._nodes:
            raise ValueError(f"Node {node_id} not in ring")

        migration_map = {}
        positions_to_remove = []

        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:vn{i}"
            hash_val = self._hash(virtual_key)

            if hash_val in self._ring:
                # Find the next node clockwise (new owner of this range)
                pos = self._sorted_keys.index(hash_val)
                # Look for next position owned by a different node
                for offset in range(1, len(self._sorted_keys)):
                    next_pos = (pos + offset) % len(self._sorted_keys)
                    next_node = self._ring[self._sorted_keys[next_pos]]
                    if next_node != node_id:
                        migration_map[f"vn{i}@{hash_val}"] = next_node
                        break

                positions_to_remove.append(hash_val)

        # Remove from ring
        for h in positions_to_remove:
            del self._ring[h]
            self._sorted_keys.remove(h)

        del self._nodes[node_id]
        del self._node_loads[node_id]

        return migration_map

    def get_node(self, key: str) -> str:
        """Find the node responsible for a key.

        Uses standard consistent hashing: hash the key, walk clockwise
        on the ring to find the first node.
        """
        if not self._sorted_keys:
            raise RuntimeError("No nodes in the ring")

        hash_val = self._hash(key)
        pos = bisect.bisect_right(self._sorted_keys, hash_val)

        if pos >= len(self._sorted_keys):
            pos = 0  # wrap around the ring

        return self._ring[self._sorted_keys[pos]]

    def get_node_bounded(self, key: str) -> str:
        """Find node with bounded-load constraint.

        Standard consistent hashing can create hotspots when certain
        keys are accessed much more frequently than others. Bounded-load
        consistent hashing adds a constraint: no node can have load
        exceeding (1 + epsilon) * (total_load / num_nodes).

        If the natural owner is overloaded, we walk clockwise until
        we find a node under the bound. This guarantees O(1/epsilon^2)
        maximum load factor.
        """
        if not self._sorted_keys:
            raise RuntimeError("No nodes in the ring")

        total_load = sum(self._node_loads.values())
        avg_load = total_load / max(len(self._nodes), 1)
        max_load = math.ceil((1 + self.load_bound_epsilon) * avg_load) + 1

        hash_val = self._hash(key)
        pos = bisect.bisect_right(self._sorted_keys, hash_val)

        # Walk clockwise until we find a node under the load bound
        for offset in range(len(self._sorted_keys)):
            idx = (pos + offset) % len(self._sorted_keys)
            node_id = self._ring[self._sorted_keys[idx]]

            if self._node_loads[node_id] < max_load:
                self._node_loads[node_id] += 1
                return node_id

        # Fallback: all nodes at capacity, use natural owner
        node_id = self._ring[self._sorted_keys[pos % len(self._sorted_keys)]]
        self._node_loads[node_id] += 1
        return node_id

    def get_replicas(self, key: str, n: int = 3) -> list[str]:
        """Get N distinct nodes for replication.

        For fault tolerance, keys are replicated to multiple nodes.
        We walk clockwise and collect distinct physical nodes
        (skipping virtual nodes of the same physical node).
        """
        if len(self._nodes) < n:
            return list(self._nodes.keys())

        hash_val = self._hash(key)
        pos = bisect.bisect_right(self._sorted_keys, hash_val)

        replicas: list[str] = []
        seen: set[str] = set()

        for offset in range(len(self._sorted_keys)):
            idx = (pos + offset) % len(self._sorted_keys)
            node_id = self._ring[self._sorted_keys[idx]]

            if node_id not in seen:
                replicas.append(node_id)
                seen.add(node_id)

            if len(replicas) >= n:
                break

        return replicas

    def get_stats(self) -> dict[str, Any]:
        """Compute load distribution statistics.

        The key metric is the coefficient of variation (CV) of the
        keyspace distribution. A CV < 0.1 means good balance;
        CV > 0.3 means you need more virtual nodes.
        """
        if not self._nodes:
            return {"error": "no nodes"}

        # Count keyspace owned by each node
        ownership: dict[str, int] = {n: 0 for n in self._nodes}
        for i, hash_val in enumerate(self._sorted_keys):
            node_id = self._ring[hash_val]
            # Each position owns the range from previous position to itself
            if i == 0:
                range_size = hash_val + (2**32 - self._sorted_keys[-1])
            else:
                range_size = hash_val - self._sorted_keys[i - 1]
            ownership[node_id] = ownership.get(node_id, 0) + range_size

        total_range = 2**32
        fractions = [v / total_range for v in ownership.values()]

        ideal = 1.0 / len(self._nodes)
        max_deviation = max(abs(f - ideal) for f in fractions)

        return {
            "num_nodes": len(self._nodes),
            "virtual_nodes_per_node": self.virtual_nodes,
            "total_ring_positions": len(self._sorted_keys),
            "load_fractions": {
                node: f"{frac:.4f}"
                for node, frac in zip(self._nodes, fractions)
            },
            "ideal_fraction": f"{ideal:.4f}",
            "max_deviation": f"{max_deviation:.4f}",
            "std_deviation": f"{statistics.stdev(fractions):.4f}" if len(fractions) > 1 else "N/A",
        }


def jump_consistent_hash(key: int, num_buckets: int) -> int:
    """Jump Consistent Hash (Lamping & Veach, Google, 2014).

    An alternative to ring-based consistent hashing that:
    - Uses O(1) memory (vs O(N * V) for ring)
    - Requires no data structure setup
    - Produces perfectly uniform distribution
    - Runs in O(ln(N)) time

    However, it only works with numbered buckets (0 to N-1) and doesn't
    support arbitrary node names or weighted nodes. Best for homogeneous
    clusters like sharded databases.

    The algorithm uses a clever mathematical trick: it computes the
    "jump" points where a key would move to a new bucket as N increases,
    and directly jumps to the final bucket.
    """
    b: int = -1
    j: int = 0
    seed = key

    while j < num_buckets:
        b = j
        seed = (seed * 2862933555777941757 + 1) & 0xFFFFFFFFFFFFFFFF
        j = int((b + 1) * (1 << 31) / ((seed >> 33) + 1))

    return b


def benchmark_distribution():
    """Compare load distribution across different virtual node counts."""
    import random

    random.seed(42)
    num_nodes = 10
    num_keys = 100_000

    for vn_count in [1, 10, 50, 150, 500]:
        ring = ConsistentHashRing(virtual_nodes=vn_count)
        for i in range(num_nodes):
            ring.add_node(f"node-{i}")

        # Distribute keys
        node_counts: dict[str, int] = {f"node-{i}": 0 for i in range(num_nodes)}
        for k in range(num_keys):
            node = ring.get_node(f"key-{k}")
            node_counts[node] += 1

        counts = list(node_counts.values())
        ideal = num_keys / num_nodes
        cv = statistics.stdev(counts) / statistics.mean(counts)
        max_load = max(counts) / ideal

        print(
            f"VNodes={vn_count:>3}: "
            f"CV={cv:.3f}, "
            f"Max/Ideal={max_load:.2f}x, "
            f"Min={min(counts)}, Max={max(counts)}"
        )


if __name__ == "__main__":
    benchmark_distribution()
```

## Virtual Nodes: Impact on Load Balance

| Virtual Nodes | Coefficient of Variation | Max/Ideal Load | Memory Overhead |
|--------------|-------------------------|----------------|-----------------|
| 1 | ~0.50 | ~2.5x | O(N) |
| 10 | ~0.25 | ~1.6x | O(10N) |
| 50 | ~0.12 | ~1.3x | O(50N) |
| **150** | **~0.07** | **~1.15x** | **O(150N)** |
| 500 | ~0.04 | ~1.08x | O(500N) |

**Best practice**: 150 virtual nodes is the sweet spot for most systems — it achieves <10% load imbalance while keeping memory overhead manageable. Going to 500+ gives diminishing returns because the lookup time increases (binary search over more positions).

## Node Failure and Data Migration

When a node fails or is removed, its data must be migrated. The strategies differ based on whether the failure is planned (graceful) or unexpected (crash):

**Graceful removal**: The leaving node actively transfers its data to the new owners before departing. This is the preferred approach because it avoids any data unavailability window.

**Crash failure**: The system detects the failure (via heartbeat timeout), removes the node from the ring, and the new owners rebuild their data from replicas. This is why replication factor ≥ 3 is standard — it tolerates one node loss without data unavailability and two without data loss.

**Common pitfall**: Triggering rebalancing too aggressively. A brief network partition can cause a node to appear failed, triggering expensive data migration — only for the node to come back moments later. Production systems use **suspicion protocols** (like SWIM) that require multiple failed heartbeats before declaring a node dead.

## Key Takeaways

- Consistent hashing ensures **only K/N keys move** when a node is added or removed, compared to nearly all keys with modular hashing — this is fundamental to elastic scaling
- **Virtual nodes** are essential for load balance: 150 virtual nodes per physical node reduces load imbalance from ~50% to ~7%
- **Bounded-load consistent hashing** adds a hard upper bound on per-node load, preventing hotspots from popular keys — critical for production cache systems
- **Jump consistent hash** is a simpler alternative when you have numbered buckets — O(1) memory and O(ln N) time with perfect uniformity, but no support for weighted or named nodes
- Replication on the ring (storing keys on N successive distinct nodes) provides fault tolerance, but **suspicion protocols** should gate rebalancing to avoid thrashing during transient failures
"""
    ),
    (
        "distributed-systems/crdts",
        "Explain Conflict-free Replicated Data Types (CRDTs) for building eventually consistent distributed systems, covering the mathematical foundations of join-semilattices, state-based vs operation-based CRDTs, and implement a comprehensive CRDT library in Python including G-Counter, PN-Counter, LWW-Register, OR-Set, and LWW-Element-Graph with merge operations and convergence proofs.",
        r"""# CRDTs: Conflict-Free Replicated Data Types

## The Motivation: Consistency Without Coordination

In distributed systems, you must choose between **strong consistency** (which requires coordination and sacrifices availability) and **eventual consistency** (which allows concurrent updates but risks conflicts). CRDTs offer a third option: **strong eventual consistency** — replicas can update independently, and they're guaranteed to converge to the same state when they've seen the same updates, **without any conflict resolution logic**.

This property makes CRDTs ideal for collaborative editing (Google Docs, Figma), distributed caches, multi-datacenter databases (Riak, Redis CRDT), and offline-first applications.

## Mathematical Foundation

A CRDT is built on a **join-semilattice**: a set with a partial order and a **least upper bound** (join) operation that is:

1. **Commutative**: `a ⊔ b = b ⊔ a` — merge order doesn't matter
2. **Associative**: `(a ⊔ b) ⊔ c = a ⊔ (b ⊔ c)` — grouping doesn't matter
3. **Idempotent**: `a ⊔ a = a` — duplicate merges are harmless

Because the join operation has these properties, replicas always converge regardless of message ordering, duplication, or timing. This is a mathematical guarantee, not a probabilistic one.

## Complete CRDT Library

```python
"""Comprehensive CRDT library for distributed systems."""
from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any, Generic, Optional, TypeVar, Hashable

T = TypeVar("T")
V = TypeVar("V")


class GCounter:
    """Grow-only Counter — each replica increments its own slot.

    The merge operation takes the max of each slot. Because max is
    commutative, associative, and idempotent, this forms a valid CRDT.

    The total count is the sum of all slots. This can only increase,
    hence "grow-only." For decrements, use a PN-Counter.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self.counts: dict[str, int] = {replica_id: 0}

    def increment(self, amount: int = 1) -> None:
        """Increment this replica's counter."""
        if amount < 0:
            raise ValueError("GCounter only supports positive increments")
        self.counts[self.replica_id] = (
            self.counts.get(self.replica_id, 0) + amount
        )

    @property
    def value(self) -> int:
        """The total count across all replicas."""
        return sum(self.counts.values())

    def merge(self, other: GCounter) -> GCounter:
        """Merge with another replica's state.

        Takes the max of each slot — this is the join operation.
        Convergence proof: max is commutative, associative, and
        idempotent, so repeated merges in any order converge.
        """
        result = GCounter(self.replica_id)
        all_keys = set(self.counts) | set(other.counts)
        for key in all_keys:
            result.counts[key] = max(
                self.counts.get(key, 0),
                other.counts.get(key, 0),
            )
        return result

    def __repr__(self) -> str:
        return f"GCounter(value={self.value}, slots={self.counts})"


class PNCounter:
    """Positive-Negative Counter — supports both increment and decrement.

    Implemented as two GCounters: one for increments (P), one for
    decrements (N). The value is P.value - N.value.

    This works because subtraction of two monotonically increasing
    values can represent any integer, and each component individually
    satisfies the CRDT convergence properties.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self.p = GCounter(replica_id)  # positive
        self.n = GCounter(replica_id)  # negative

    def increment(self, amount: int = 1) -> None:
        self.p.increment(amount)

    def decrement(self, amount: int = 1) -> None:
        self.n.increment(amount)

    @property
    def value(self) -> int:
        return self.p.value - self.n.value

    def merge(self, other: PNCounter) -> PNCounter:
        result = PNCounter(self.replica_id)
        result.p = self.p.merge(other.p)
        result.n = self.n.merge(other.n)
        return result

    def __repr__(self) -> str:
        return f"PNCounter(value={self.value}, p={self.p.value}, n={self.n.value})"


@dataclasses.dataclass(frozen=True)
class Timestamped(Generic[T]):
    """A value with a Lamport timestamp for LWW semantics."""
    value: T
    timestamp: float
    replica_id: str  # tiebreaker for equal timestamps


class LWWRegister(Generic[T]):
    """Last-Writer-Wins Register — concurrent writes resolve by timestamp.

    The "last write wins" policy is simple and predictable, but it
    can silently discard concurrent updates. This is acceptable for
    many use cases (user preferences, status fields) but inappropriate
    for others (bank balances, inventory counts — use counters instead).

    Common mistake: Using wall-clock time for timestamps. Clock skew
    between replicas can cause "earlier" writes to win. Use Hybrid
    Logical Clocks (HLC) for better ordering guarantees.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self._state: Optional[Timestamped[T]] = None

    def set(self, value: T, timestamp: Optional[float] = None) -> None:
        """Set the register's value with current timestamp."""
        ts = timestamp or time.time()
        new_state = Timestamped(value=value, timestamp=ts, replica_id=self.replica_id)

        if self._state is None or self._compare(new_state, self._state) > 0:
            self._state = new_state

    @property
    def value(self) -> Optional[T]:
        return self._state.value if self._state else None

    def merge(self, other: LWWRegister[T]) -> LWWRegister[T]:
        """Merge: keep the entry with the highest timestamp."""
        result = LWWRegister[T](self.replica_id)
        if self._state is None:
            result._state = other._state
        elif other._state is None:
            result._state = self._state
        elif self._compare(self._state, other._state) >= 0:
            result._state = self._state
        else:
            result._state = other._state
        return result

    @staticmethod
    def _compare(a: Timestamped, b: Timestamped) -> int:
        """Compare two timestamped values. Tiebreak by replica_id."""
        if a.timestamp != b.timestamp:
            return 1 if a.timestamp > b.timestamp else -1
        return 1 if a.replica_id > b.replica_id else -1


class ORSet(Generic[T]):
    """Observed-Remove Set — supports both add and remove.

    The naive approach (tracking adds and removes separately) has the
    "add-remove anomaly": if add and remove happen concurrently, which
    wins? The OR-Set resolves this by tagging each add with a unique ID.
    Remove only removes specific tagged versions, so a concurrent add
    (with a different tag) survives.

    This gives intuitive semantics: if you add an element after someone
    else removed it, your add is preserved. Only removes that have
    "observed" a specific add can remove it.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        # element -> set of unique tags (each add creates a new tag)
        self._elements: dict[T, set[str]] = {}
        # Tombstones: tags that have been removed
        self._tombstones: set[str] = set()

    def add(self, element: T) -> None:
        """Add an element with a unique tag."""
        tag = f"{self.replica_id}:{uuid.uuid4().hex[:8]}"
        if element not in self._elements:
            self._elements[element] = set()
        self._elements[element].add(tag)

    def remove(self, element: T) -> None:
        """Remove an element by tombstoning all its current tags.

        Only removes tags we've observed — concurrent adds with
        different tags will survive this remove.
        """
        if element in self._elements:
            self._tombstones.update(self._elements[element])
            del self._elements[element]

    def __contains__(self, element: T) -> bool:
        if element not in self._elements:
            return False
        # Element exists if it has any non-tombstoned tags
        live_tags = self._elements[element] - self._tombstones
        return len(live_tags) > 0

    @property
    def value(self) -> set[T]:
        """Current set contents (elements with live tags)."""
        result = set()
        for element, tags in self._elements.items():
            if tags - self._tombstones:
                result.add(element)
        return result

    def merge(self, other: ORSet[T]) -> ORSet[T]:
        """Merge two OR-Sets.

        Union all tags, union all tombstones. An element is present
        if it has any tag not in the tombstone set.
        """
        result = ORSet[T](self.replica_id)
        result._tombstones = self._tombstones | other._tombstones

        all_elements = set(self._elements) | set(other._elements)
        for element in all_elements:
            tags_self = self._elements.get(element, set())
            tags_other = other._elements.get(element, set())
            merged_tags = tags_self | tags_other
            # Only keep non-tombstoned tags
            live_tags = merged_tags - result._tombstones
            if live_tags:
                result._elements[element] = live_tags

        return result

    def __repr__(self) -> str:
        return f"ORSet({self.value})"


class LWWElementGraph:
    """Last-Writer-Wins Element Graph — CRDT graph structure.

    Supports vertices and edges with LWW add/remove semantics.
    Each vertex and edge has an add-timestamp and remove-timestamp.
    The element exists if add-timestamp > remove-timestamp.

    This is useful for collaborative graph editing, social networks
    (follow/unfollow), and distributed knowledge graphs.

    Design decision: An edge can only exist if both its endpoints
    exist. This is the "add-precondition" — we check it on read,
    not on write, to avoid coordination.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        # vertex_id -> (add_ts, remove_ts)
        self._vertices: dict[str, tuple[float, float]] = {}
        # (src, dst) -> (add_ts, remove_ts)
        self._edges: dict[tuple[str, str], tuple[float, float]] = {}

    def add_vertex(self, vertex_id: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        current = self._vertices.get(vertex_id, (0.0, 0.0))
        self._vertices[vertex_id] = (max(current[0], ts), current[1])

    def remove_vertex(self, vertex_id: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        current = self._vertices.get(vertex_id, (0.0, 0.0))
        self._vertices[vertex_id] = (current[0], max(current[1], ts))

    def add_edge(self, src: str, dst: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        key = (src, dst)
        current = self._edges.get(key, (0.0, 0.0))
        self._edges[key] = (max(current[0], ts), current[1])

    def remove_edge(self, src: str, dst: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        key = (src, dst)
        current = self._edges.get(key, (0.0, 0.0))
        self._edges[key] = (current[0], max(current[1], ts))

    def _vertex_exists(self, vertex_id: str) -> bool:
        if vertex_id not in self._vertices:
            return False
        add_ts, rm_ts = self._vertices[vertex_id]
        return add_ts > rm_ts

    def _edge_exists(self, src: str, dst: str) -> bool:
        key = (src, dst)
        if key not in self._edges:
            return False
        add_ts, rm_ts = self._edges[key]
        # Edge exists only if both endpoints exist AND edge add > remove
        return (
            add_ts > rm_ts
            and self._vertex_exists(src)
            and self._vertex_exists(dst)
        )

    @property
    def vertices(self) -> set[str]:
        return {v for v in self._vertices if self._vertex_exists(v)}

    @property
    def edges(self) -> set[tuple[str, str]]:
        return {(s, d) for (s, d) in self._edges if self._edge_exists(s, d)}

    def neighbors(self, vertex_id: str) -> set[str]:
        if not self._vertex_exists(vertex_id):
            return set()
        result = set()
        for (src, dst) in self._edges:
            if src == vertex_id and self._edge_exists(src, dst):
                result.add(dst)
            elif dst == vertex_id and self._edge_exists(src, dst):
                result.add(src)
        return result

    def merge(self, other: LWWElementGraph) -> LWWElementGraph:
        """Merge two graphs: max of all timestamps."""
        result = LWWElementGraph(self.replica_id)

        all_verts = set(self._vertices) | set(other._vertices)
        for v in all_verts:
            self_ts = self._vertices.get(v, (0.0, 0.0))
            other_ts = other._vertices.get(v, (0.0, 0.0))
            result._vertices[v] = (
                max(self_ts[0], other_ts[0]),
                max(self_ts[1], other_ts[1]),
            )

        all_edges = set(self._edges) | set(other._edges)
        for e in all_edges:
            self_ts = self._edges.get(e, (0.0, 0.0))
            other_ts = other._edges.get(e, (0.0, 0.0))
            result._edges[e] = (
                max(self_ts[0], other_ts[0]),
                max(self_ts[1], other_ts[1]),
            )

        return result


def test_crdt_convergence():
    """Verify that all CRDTs converge regardless of merge order."""

    # --- GCounter convergence ---
    g1 = GCounter("r1")
    g2 = GCounter("r2")
    g1.increment(5)
    g2.increment(3)
    # Merge in different orders
    m1 = g1.merge(g2)
    m2 = g2.merge(g1)
    assert m1.value == m2.value == 8, f"GCounter diverged: {m1.value} vs {m2.value}"

    # --- PNCounter convergence ---
    pn1 = PNCounter("r1")
    pn2 = PNCounter("r2")
    pn1.increment(10)
    pn2.decrement(3)
    m1 = pn1.merge(pn2)
    m2 = pn2.merge(pn1)
    assert m1.value == m2.value == 7, f"PNCounter diverged: {m1.value} vs {m2.value}"

    # --- OR-Set convergence with concurrent add/remove ---
    s1 = ORSet[str]("r1")
    s2 = ORSet[str]("r2")
    s1.add("x")
    # Sync s1 -> s2
    s2 = s1.merge(s2)
    # Concurrent: r1 removes x, r2 adds x again
    s1.remove("x")
    s2.add("x")
    # Merge both ways
    m1 = s1.merge(s2)
    m2 = s2.merge(s1)
    assert m1.value == m2.value, f"OR-Set diverged: {m1.value} vs {m2.value}"
    # x should be present because r2's add happened after observing the original
    assert "x" in m1, "Concurrent add should survive remove in OR-Set"

    # --- LWW-Element-Graph convergence ---
    lg1 = LWWElementGraph("r1")
    lg2 = LWWElementGraph("r2")
    lg1.add_vertex("A", ts=1.0)
    lg1.add_vertex("B", ts=1.0)
    lg1.add_edge("A", "B", ts=2.0)
    lg2.remove_vertex("B", ts=3.0)  # concurrent remove
    m1 = lg1.merge(lg2)
    m2 = lg2.merge(lg1)
    assert m1.vertices == m2.vertices, "Graph vertices diverged"
    assert m1.edges == m2.edges, "Graph edges diverged"
    # B removed at ts=3 > added at ts=1, so edge A->B should not exist
    assert "B" not in m1.vertices, "B should be removed"
    assert ("A", "B") not in m1.edges, "Edge should not exist without endpoint"

    print("All CRDT convergence tests passed!")
    print(f"  GCounter: {m1.value if isinstance(m1, GCounter) else 'OK'}")
    print(f"  PNCounter: OK")
    print(f"  OR-Set: {m1.value if isinstance(m1, ORSet) else 'OK'}")
    print(f"  LWW-Graph: vertices={lg1.merge(lg2).vertices}")


if __name__ == "__main__":
    test_crdt_convergence()
```

## CRDT Comparison Table

| CRDT Type | Operations | Merge Strategy | Metadata Overhead | Best For |
|-----------|-----------|---------------|-------------------|----------|
| **G-Counter** | Increment | Max per slot | O(replicas) | View counts, metrics |
| **PN-Counter** | Inc/Dec | Max per slot × 2 | O(2 × replicas) | Likes, inventory |
| **LWW-Register** | Set | Higher timestamp wins | O(1) | User profiles, status |
| **OR-Set** | Add/Remove | Union tags + tombstones | O(adds) | Shopping carts, tags |
| **LWW-Graph** | Add/Remove vertices/edges | Max timestamps | O(vertices + edges) | Social graphs, knowledge bases |

## Key Takeaways

- CRDTs guarantee **strong eventual consistency** through the mathematical properties of join-semilattices — commutativity, associativity, and idempotency of the merge operation
- **State-based CRDTs** (shown here) ship full state on sync and merge with a join function; **operation-based CRDTs** ship individual operations and require exactly-once delivery
- The **OR-Set** solves the add-remove anomaly by tagging each add uniquely — concurrent adds survive removes, giving intuitive semantics
- **Metadata overhead** is the main cost: OR-Sets accumulate tombstones, G-Counters grow with the number of replicas. Production systems need **garbage collection** (causal stability) to bound metadata
- CRDTs are used in production at massive scale: **Redis CRDTs** for geo-distributed caching, **Riak** for distributed databases, **Figma** and **Google Docs** for collaborative editing, and **Automerge/Yjs** for local-first applications
"""
    ),
    (
        "distributed-systems/vector-clocks",
        "Explain vector clocks and their role in tracking causality in distributed systems, covering the happens-before relation, limitations of Lamport timestamps, how vector clocks detect concurrent events, and provide a Python implementation of a vector clock system with causal delivery, conflict detection for a key-value store, and comparison with hybrid logical clocks.",
        r"""# Vector Clocks: Tracking Causality in Distributed Systems

## The Problem: Ordering Events Without a Global Clock

In a distributed system, there is no shared global clock. Each node has its own clock, and these clocks drift. We need a way to determine: did event A happen before event B, or were they concurrent? This distinction is critical because **concurrent events may conflict** and require resolution, while causally related events have a natural ordering.

## Lamport Timestamps: Necessary but Insufficient

Leslie Lamport's logical clocks (1978) provide a simple rule: if event A happened before B, then `L(A) < L(B)`. However, the **converse is not true**: `L(A) < L(B)` does NOT mean A happened before B — they might be concurrent. Lamport timestamps can detect potential causality but cannot distinguish causality from concurrency.

**Why this matters**: If two users concurrently update the same key, we need to know they're concurrent (to trigger conflict resolution). Lamport timestamps would just pick the higher timestamp, silently discarding one update. Vector clocks solve this by capturing **which events each node has seen**.

## How Vector Clocks Work

Each node maintains a vector of counters, one per node in the system. When:
1. A local event occurs: increment your own counter
2. Sending a message: attach the full vector
3. Receiving a message: take element-wise max, then increment your own

Two vector clocks can be compared to determine the **causal relationship**:
- `VC(A) < VC(B)`: A happened before B (A causally precedes B)
- `VC(A) > VC(B)`: B happened before A
- Neither: A and B are **concurrent** (conflict!)

```python
"""Vector clocks with causal delivery and conflict detection."""
from __future__ import annotations

import copy
import dataclasses
import enum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class CausalRelation(enum.Enum):
    """Possible causal relationships between two events."""
    BEFORE = "before"        # a happens-before b
    AFTER = "after"          # b happens-before a
    CONCURRENT = "concurrent"  # neither ordered — potential conflict
    EQUAL = "equal"          # same logical time


class VectorClock:
    """Vector clock for tracking causality in distributed systems.

    Each node maintains a vector of logical timestamps, one per node.
    The vector captures "how much of each node's history I've observed."
    This allows precise detection of concurrent events — something
    Lamport timestamps cannot do.

    Space complexity: O(N) per clock where N is the number of nodes.
    This is the fundamental trade-off: precise causality tracking
    requires space proportional to the number of participants.
    """

    def __init__(self, node_id: str, initial: Optional[dict[str, int]] = None) -> None:
        self.node_id = node_id
        self.clock: dict[str, int] = initial or {node_id: 0}

    def increment(self) -> VectorClock:
        """Record a local event by incrementing this node's counter."""
        self.clock[self.node_id] = self.clock.get(self.node_id, 0) + 1
        return self

    def merge(self, other: VectorClock) -> VectorClock:
        """Merge with a received clock (element-wise max) and increment.

        This is called when receiving a message. The merge captures
        the causal history of both this node and the sender.
        """
        all_nodes = set(self.clock) | set(other.clock)
        for node in all_nodes:
            self.clock[node] = max(
                self.clock.get(node, 0),
                other.clock.get(node, 0),
            )
        self.increment()
        return self

    def copy(self) -> VectorClock:
        """Create an independent copy of this vector clock."""
        return VectorClock(self.node_id, dict(self.clock))

    @staticmethod
    def compare(a: VectorClock, b: VectorClock) -> CausalRelation:
        """Determine the causal relationship between two events.

        This is the key advantage over Lamport timestamps:
        - If all of a's counters <= b's counters (and at least one <):
          a happened before b.
        - If all of b's counters <= a's counters: b happened before a.
        - If some of a's are greater AND some of b's are greater:
          the events are CONCURRENT — a conflict that must be resolved.

        This precise concurrency detection is why distributed databases
        (Riak, Dynamo) use vector clocks for conflict resolution.
        """
        all_nodes = set(a.clock) | set(b.clock)

        a_le_b = True  # all a[i] <= b[i]
        b_le_a = True  # all b[i] <= a[i]
        equal = True

        for node in all_nodes:
            av = a.clock.get(node, 0)
            bv = b.clock.get(node, 0)

            if av > bv:
                b_le_a = True
                a_le_b = False
                equal = False
            elif bv > av:
                a_le_b = True
                b_le_a = False
                equal = False

        if equal:
            return CausalRelation.EQUAL
        if a_le_b and not b_le_a:
            return CausalRelation.BEFORE
        if b_le_a and not a_le_b:
            return CausalRelation.AFTER
        return CausalRelation.CONCURRENT

    def __repr__(self) -> str:
        return f"VC({self.clock})"

    def __le__(self, other: VectorClock) -> bool:
        """Check if this clock is causally before or equal to other."""
        for node in set(self.clock) | set(other.clock):
            if self.clock.get(node, 0) > other.clock.get(node, 0):
                return False
        return True


@dataclasses.dataclass
class VersionedValue(Generic[T]):
    """A value tagged with its vector clock for conflict detection."""
    value: T
    clock: VectorClock
    node_id: str  # which node wrote this version


class CausalKVStore:
    """Key-value store with vector clock conflict detection.

    When a client reads a key, it gets the value AND the vector clock.
    When writing, the client sends back the clock it read, allowing
    the store to detect concurrent writes.

    If two writes are concurrent (neither causally dominates), the
    store keeps BOTH versions as "siblings" — the application must
    resolve the conflict (e.g., merge shopping cart contents, take
    the longer text, etc.).

    This is the approach used by Amazon Dynamo and Riak. The trade-off
    is that applications must handle siblings, but they get to use
    domain-specific merge logic rather than a generic last-write-wins
    policy that might silently lose data.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.clock = VectorClock(node_id)
        # key -> list of VersionedValues (siblings for concurrent writes)
        self._store: dict[str, list[VersionedValue]] = {}

    def get(self, key: str) -> list[VersionedValue]:
        """Read a key, returning all concurrent versions (siblings).

        If there's exactly one version, no conflict exists.
        If there are multiple versions, the client must resolve the
        conflict and write back the resolved value.
        """
        return self._store.get(key, [])

    def put(
        self,
        key: str,
        value: Any,
        context: Optional[VectorClock] = None,
    ) -> VectorClock:
        """Write a value with causal context.

        The context is the vector clock from the client's last read.
        If provided, we can determine which existing versions this
        write supersedes vs. which are concurrent.

        Args:
            key: The key to write.
            value: The value to store.
            context: Vector clock from the client's last read of this key.
                If None, this is a blind write (treated as concurrent with
                everything).

        Returns:
            The vector clock assigned to this write.
        """
        self.clock.increment()
        write_clock = self.clock.copy()

        new_version = VersionedValue(
            value=value,
            clock=write_clock,
            node_id=self.node_id,
        )

        existing = self._store.get(key, [])

        if context is not None:
            # Remove versions that are causally dominated by this write
            # (the client has seen them and is superseding them)
            surviving = []
            for version in existing:
                relation = VectorClock.compare(version.clock, context)
                if relation == CausalRelation.AFTER or relation == CausalRelation.CONCURRENT:
                    # This version happened after the client's read,
                    # or is concurrent — keep it as a sibling
                    surviving.append(version)
                # BEFORE or EQUAL: this version is superseded by the new write
            surviving.append(new_version)
            self._store[key] = surviving
        else:
            # Blind write — concurrent with everything existing
            existing.append(new_version)
            self._store[key] = existing

        return write_clock

    def replicate_from(self, key: str, versions: list[VersionedValue]) -> None:
        """Receive replicated versions from another node.

        Merge incoming versions with local versions, keeping only
        causally maximal versions (no version dominated by another).
        """
        existing = self._store.get(key, [])
        all_versions = existing + versions

        # Keep only causally maximal versions
        maximal: list[VersionedValue] = []
        for candidate in all_versions:
            dominated = False
            for other in all_versions:
                if other is candidate:
                    continue
                rel = VectorClock.compare(candidate.clock, other.clock)
                if rel == CausalRelation.BEFORE:
                    dominated = True
                    break
            if not dominated:
                # Check not already in maximal (by clock equality)
                already_present = any(
                    VectorClock.compare(candidate.clock, m.clock) == CausalRelation.EQUAL
                    for m in maximal
                )
                if not already_present:
                    maximal.append(candidate)

        self._store[key] = maximal

        # Update our clock
        for v in versions:
            self.clock.merge(v.clock)


class HybridLogicalClock:
    """Hybrid Logical Clock (HLC) — combines physical and logical time.

    Vector clocks have O(N) space per timestamp, which is problematic
    for systems with many nodes. HLCs use a single 64-bit timestamp
    that embeds both physical time and a logical counter:

    - Physical component: millisecond wall clock (48 bits)
    - Logical component: counter for sub-millisecond ordering (16 bits)

    HLCs provide a total order (unlike vector clocks which give partial
    order) and are bounded by real time (within clock skew). However,
    they CANNOT detect concurrency — only ordering. This is the trade-off:
    O(1) space but no conflict detection.

    Used by: CockroachDB, YugabyteDB, TiDB.
    """

    def __init__(self) -> None:
        self.physical: int = 0   # max physical time seen
        self.logical: int = 0    # logical counter for same physical time

    def now(self, wall_time_ms: int) -> tuple[int, int]:
        """Generate a new timestamp.

        The key invariant: timestamps are always >= wall clock time
        and strictly monotonically increasing.
        """
        if wall_time_ms > self.physical:
            self.physical = wall_time_ms
            self.logical = 0
        else:
            # Wall clock hasn't advanced — increment logical
            self.logical += 1

        return (self.physical, self.logical)

    def receive(self, msg_physical: int, msg_logical: int, wall_time_ms: int) -> tuple[int, int]:
        """Update clock on receiving a message.

        Takes the max of local clock, message clock, and wall clock,
        then increments the logical component.
        """
        old_physical = self.physical

        self.physical = max(self.physical, msg_physical, wall_time_ms)

        if self.physical == old_physical == msg_physical:
            self.logical = max(self.logical, msg_logical) + 1
        elif self.physical == old_physical:
            self.logical += 1
        elif self.physical == msg_physical:
            self.logical = msg_logical + 1
        else:
            self.logical = 0

        return (self.physical, self.logical)

    def to_int(self) -> int:
        """Pack into a single 64-bit integer for storage."""
        return (self.physical << 16) | (self.logical & 0xFFFF)


def test_vector_clocks():
    """Comprehensive test of vector clock causality detection."""

    # Scenario: Two nodes write to the same key concurrently
    vc_a = VectorClock("A")
    vc_b = VectorClock("B")

    # A does a local event
    vc_a.increment()  # A: {A:1}

    # B does a local event
    vc_b.increment()  # B: {B:1}

    # These are concurrent — neither has seen the other's event
    rel = VectorClock.compare(vc_a, vc_b)
    assert rel == CausalRelation.CONCURRENT, f"Should be concurrent, got {rel}"

    # A sends message to B
    vc_a_copy = vc_a.copy()
    vc_b.merge(vc_a_copy)  # B: {A:1, B:2}

    # Now B has seen A's event — B's new events are AFTER A's
    vc_b.increment()  # B: {A:1, B:3}
    rel = VectorClock.compare(vc_a, vc_b)
    assert rel == CausalRelation.BEFORE, f"A should be before B, got {rel}"

    print("Vector clock causality tests passed!")

    # --- KV Store conflict detection ---
    store1 = CausalKVStore("node1")
    store2 = CausalKVStore("node2")

    # Both nodes write to same key concurrently
    ctx1 = store1.put("user:1", {"name": "Alice"})
    ctx2 = store2.put("user:1", {"name": "Alicia"})

    # Replicate to store1
    store1.replicate_from("user:1", store2.get("user:1"))

    # Should have 2 siblings (concurrent writes)
    versions = store1.get("user:1")
    assert len(versions) == 2, f"Expected 2 siblings, got {len(versions)}"
    print(f"Conflict detected: {len(versions)} siblings for user:1")
    for v in versions:
        print(f"  {v.value} from {v.node_id}")

    # Resolve conflict by reading both siblings and writing merged value
    merged_value = {"name": "Alice (Alicia)"}  # app-specific merge
    # Use the max clock as context to supersede both siblings
    max_clock = versions[0].clock.copy()
    for v in versions[1:]:
        max_clock.merge(v.clock)
    store1.put("user:1", merged_value, context=max_clock)

    # Now should have 1 version
    resolved = store1.get("user:1")
    assert len(resolved) == 1, f"Expected 1 version after resolution, got {len(resolved)}"
    print(f"Resolved to: {resolved[0].value}")


if __name__ == "__main__":
    test_vector_clocks()
```

## Comparison of Clock Mechanisms

| Mechanism | Space | Detects Concurrency | Total Order | Bounded Drift | Used By |
|-----------|-------|--------------------:|-------------|---------------|---------|
| **Lamport** | O(1) | No | Yes | No | General |
| **Vector Clock** | O(N) | **Yes** | No (partial) | No | Riak, Dynamo |
| **HLC** | O(1) | No | Yes | Yes (bounded) | CockroachDB, TiDB |
| **Dotted Version Vector** | O(N) | **Yes** | No | No | Riak 2.0+ |
| **TrueTime** | O(1) | No | Yes | Yes (GPS + atomic) | Google Spanner |

## Key Takeaways

- **Vector clocks** are the only general mechanism that can **detect concurrent events** — Lamport timestamps and HLCs can order events but cannot distinguish causality from concurrency
- The **happens-before relation** is a partial order: some events are genuinely unordered, and this concurrency is meaningful (it indicates potential conflicts)
- In the **Dynamo model**, concurrent writes produce "siblings" that the application resolves — this preserves all concurrent updates rather than silently discarding one with last-write-wins
- **Hybrid Logical Clocks** sacrifice concurrency detection for O(1) space — a good trade-off for strongly-consistent systems (like CockroachDB) that use Raft consensus rather than eventual consistency
- The fundamental trade-off is **space vs. information**: O(N) per timestamp for full causal tracking, or O(1) for ordering-only, and each application must choose based on its consistency model
"""
    ),
    (
        "distributed-systems/consistent-transactions",
        "Explain distributed transaction protocols including two-phase commit (2PC), three-phase commit, and Saga pattern, covering their failure modes, performance characteristics, and trade-offs, and implement a complete 2PC coordinator in Python with timeout handling, participant recovery, and comparison against Saga-based eventual consistency with compensating transactions.",
        r"""# Distributed Transactions: 2PC, 3PC, and Sagas

## The Distributed Transaction Problem

When a business operation spans multiple services or databases, we need **atomicity** — either all changes commit or all roll back. A single-database transaction uses write-ahead logging, but across network boundaries, we need a **protocol** to coordinate the commit decision because any participant might crash at any point.

## Two-Phase Commit (2PC)

2PC is the classic solution. A **coordinator** drives the protocol:

**Phase 1 (Prepare/Vote)**: Coordinator asks all participants "Can you commit?" Each participant acquires locks, writes to its WAL, and votes YES or NO.

**Phase 2 (Commit/Abort)**: If ALL voted YES → coordinator sends COMMIT. If ANY voted NO → coordinator sends ABORT. Participants execute accordingly.

**The blocking problem**: If the coordinator crashes after collecting votes but before sending the decision, participants are **stuck** — they're holding locks and don't know whether to commit or abort. This is 2PC's fundamental weakness and why it's a **blocking protocol**.

```python
"""Two-phase commit coordinator with timeout and recovery."""
from __future__ import annotations

import dataclasses
import enum
import logging
import time
import uuid
from typing import Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError

logger = logging.getLogger(__name__)


class TxnState(enum.Enum):
    INIT = "init"
    PREPARING = "preparing"
    PREPARED = "prepared"      # all voted yes
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"


class Vote(enum.Enum):
    YES = "yes"
    NO = "no"
    TIMEOUT = "timeout"


@dataclasses.dataclass
class TransactionLog:
    """Write-ahead log entry for coordinator recovery.

    The coordinator MUST persist its decision to the WAL before
    sending commit/abort messages. This is what allows recovery
    after coordinator crash — the recovered coordinator reads the
    WAL and resends the decision.

    Common mistake: Sending the commit message before persisting
    the decision. If the coordinator crashes after sending to some
    participants but before persisting, the recovered coordinator
    doesn't know the decision and cannot complete the protocol.
    """
    txn_id: str
    state: TxnState
    participants: list[str]
    votes: dict[str, Vote]
    timestamp: float
    decision: Optional[str] = None  # "commit" or "abort"


class Participant:
    """A participant in the 2PC protocol.

    Each participant manages its own local transaction and votes
    based on whether it can commit locally. After voting YES,
    the participant is "in doubt" until it receives the decision.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._prepared_txns: dict[str, Any] = {}
        self._committed_txns: set[str] = set()
        self._aborted_txns: set[str] = set()

    def prepare(self, txn_id: str, operation: dict[str, Any]) -> Vote:
        """Phase 1: Prepare to commit.

        Validate the operation, acquire locks, write to WAL.
        Return YES if we can guarantee commit, NO otherwise.

        After voting YES, we MUST be able to commit later, even
        after a crash and restart. This means the WAL entry must
        be fsynced before returning YES.
        """
        try:
            # Simulate validation
            if operation.get("should_fail"):
                logger.info(f"[{self.name}] Voting NO for {txn_id}")
                return Vote.NO

            # Write to WAL and acquire locks
            self._prepared_txns[txn_id] = {
                "operation": operation,
                "prepared_at": time.time(),
            }
            logger.info(f"[{self.name}] Voting YES for {txn_id}")
            return Vote.YES

        except Exception as e:
            logger.error(f"[{self.name}] Prepare failed: {e}")
            return Vote.NO

    def commit(self, txn_id: str) -> bool:
        """Phase 2: Commit the prepared transaction."""
        if txn_id not in self._prepared_txns:
            # Idempotent: already committed or never prepared
            return txn_id in self._committed_txns

        del self._prepared_txns[txn_id]
        self._committed_txns.add(txn_id)
        logger.info(f"[{self.name}] Committed {txn_id}")
        return True

    def abort(self, txn_id: str) -> bool:
        """Phase 2: Abort the prepared transaction."""
        self._prepared_txns.pop(txn_id, None)
        self._aborted_txns.add(txn_id)
        logger.info(f"[{self.name}] Aborted {txn_id}")
        return True

    def query_status(self, txn_id: str) -> str:
        """Recovery: participant asks coordinator for decision."""
        if txn_id in self._committed_txns:
            return "committed"
        if txn_id in self._aborted_txns:
            return "aborted"
        if txn_id in self._prepared_txns:
            return "prepared"  # in doubt
        return "unknown"


class TwoPhaseCommitCoordinator:
    """Coordinator for the Two-Phase Commit protocol.

    Responsibilities:
    1. Drive the prepare and commit/abort phases
    2. Persist the transaction decision to WAL before acting
    3. Handle participant timeouts and failures
    4. Recover and complete in-doubt transactions after crash

    The coordinator is a single point of failure in 2PC. If it
    crashes while participants are in the "prepared" state, those
    participants are blocked until the coordinator recovers. This
    is the fundamental limitation that 3PC and Paxos Commit address.
    """

    def __init__(
        self,
        participants: dict[str, Participant],
        prepare_timeout: float = 5.0,
        commit_timeout: float = 10.0,
    ) -> None:
        self.participants = participants
        self.prepare_timeout = prepare_timeout
        self.commit_timeout = commit_timeout

        # Write-ahead log for recovery
        self._wal: dict[str, TransactionLog] = {}

        # Thread pool for parallel participant communication
        self._executor = ThreadPoolExecutor(
            max_workers=len(participants),
            thread_name_prefix="2pc",
        )

    def execute(self, operations: dict[str, dict[str, Any]]) -> bool:
        """Execute a distributed transaction across participants.

        Args:
            operations: Map of participant_name -> operation to execute.

        Returns:
            True if committed, False if aborted.
        """
        txn_id = str(uuid.uuid4())[:8]
        participant_names = list(operations.keys())

        # Initialize WAL
        log = TransactionLog(
            txn_id=txn_id,
            state=TxnState.INIT,
            participants=participant_names,
            votes={},
            timestamp=time.time(),
        )
        self._wal[txn_id] = log

        # === Phase 1: Prepare ===
        log.state = TxnState.PREPARING
        votes = self._collect_votes(txn_id, operations)
        log.votes = votes

        # Check for unanimous YES
        all_yes = all(v == Vote.YES for v in votes.values())

        if all_yes:
            # === Commit path ===
            # CRITICAL: persist decision BEFORE sending commit messages
            log.state = TxnState.PREPARED
            log.decision = "commit"
            self._persist_wal(log)  # must be durable before proceeding

            log.state = TxnState.COMMITTING
            self._send_decision(txn_id, participant_names, commit=True)
            log.state = TxnState.COMMITTED
            self._persist_wal(log)
            return True
        else:
            # === Abort path ===
            log.decision = "abort"
            self._persist_wal(log)

            log.state = TxnState.ABORTING
            # Only abort participants that voted YES (others already aborted)
            yes_voters = [p for p, v in votes.items() if v == Vote.YES]
            self._send_decision(txn_id, yes_voters, commit=False)
            log.state = TxnState.ABORTED
            self._persist_wal(log)
            return False

    def _collect_votes(
        self, txn_id: str, operations: dict[str, dict]
    ) -> dict[str, Vote]:
        """Phase 1: Collect votes from all participants in parallel."""
        futures: dict[str, Future] = {}
        for name, op in operations.items():
            participant = self.participants[name]
            futures[name] = self._executor.submit(
                participant.prepare, txn_id, op
            )

        votes: dict[str, Vote] = {}
        for name, future in futures.items():
            try:
                votes[name] = future.result(timeout=self.prepare_timeout)
            except TimeoutError:
                logger.warning(f"Participant {name} timed out during prepare")
                votes[name] = Vote.TIMEOUT
            except Exception as e:
                logger.error(f"Participant {name} prepare error: {e}")
                votes[name] = Vote.NO

        return votes

    def _send_decision(
        self, txn_id: str, participants: list[str], commit: bool
    ) -> None:
        """Phase 2: Send commit/abort to all participants in parallel."""
        futures = {}
        for name in participants:
            p = self.participants[name]
            fn = p.commit if commit else p.abort
            futures[name] = self._executor.submit(fn, txn_id)

        for name, future in futures.items():
            try:
                future.result(timeout=self.commit_timeout)
            except Exception as e:
                # Phase 2 retries are critical — the decision is made,
                # we must keep trying until all participants acknowledge
                logger.error(
                    f"Failed to send {'commit' if commit else 'abort'} "
                    f"to {name}: {e}. Will retry on recovery."
                )

    def recover(self) -> None:
        """Recover in-doubt transactions after coordinator restart.

        Read the WAL and complete any transactions that were in
        progress when we crashed. This is why the WAL must be
        persisted before sending phase 2 messages.
        """
        for txn_id, log in self._wal.items():
            if log.state in (TxnState.COMMITTED, TxnState.ABORTED):
                continue  # already completed

            if log.decision == "commit":
                logger.info(f"Recovery: completing commit for {txn_id}")
                self._send_decision(txn_id, log.participants, commit=True)
                log.state = TxnState.COMMITTED
            elif log.decision == "abort":
                logger.info(f"Recovery: completing abort for {txn_id}")
                yes_voters = [
                    p for p, v in log.votes.items() if v == Vote.YES
                ]
                self._send_decision(txn_id, yes_voters, commit=False)
                log.state = TxnState.ABORTED
            else:
                # No decision recorded — safe to abort
                logger.info(f"Recovery: aborting undecided {txn_id}")
                log.decision = "abort"
                yes_voters = [
                    p for p, v in log.votes.items() if v == Vote.YES
                ]
                self._send_decision(txn_id, yes_voters, commit=False)
                log.state = TxnState.ABORTED

    def _persist_wal(self, log: TransactionLog) -> None:
        """Persist WAL entry to durable storage.

        In production, this would fsync to disk. The coordinator
        must not proceed until the WAL write is confirmed durable.
        """
        self._wal[log.txn_id] = log
        logger.debug(f"WAL persisted: {log.txn_id} -> {log.state}")


# === Saga Pattern: The Alternative ===

@dataclasses.dataclass
class SagaStep:
    """A single step in a saga with its compensating action."""
    name: str
    action: Callable[[], bool]
    compensation: Callable[[], bool]


class SagaOrchestrator:
    """Saga pattern for distributed transactions without locking.

    Unlike 2PC, sagas don't hold locks across services. Each step
    commits independently. If a step fails, previously committed
    steps are undone via compensating transactions.

    Trade-offs vs 2PC:
    - No distributed locks → better performance and availability
    - Eventual consistency → intermediate states are visible
    - Compensations must be idempotent and semantically correct
    - More complex application logic

    Best practice: Use sagas for long-running business processes
    (order fulfillment, booking). Use 2PC for short, critical
    operations (financial transfers between accounts in the same DB).
    """

    def __init__(self, steps: list[SagaStep]) -> None:
        self.steps = steps
        self.completed_steps: list[SagaStep] = []

    def execute(self) -> bool:
        """Execute the saga forward, compensating on failure."""
        for step in self.steps:
            logger.info(f"Saga: executing {step.name}")
            try:
                success = step.action()
                if not success:
                    logger.warning(f"Saga: {step.name} failed, compensating")
                    self._compensate()
                    return False
                self.completed_steps.append(step)
            except Exception as e:
                logger.error(f"Saga: {step.name} error: {e}, compensating")
                self._compensate()
                return False

        logger.info("Saga: all steps completed successfully")
        return True

    def _compensate(self) -> None:
        """Run compensating transactions in reverse order.

        Compensations must be idempotent because they may be retried
        on failure. They should also be "best effort" — a failed
        compensation is logged for manual intervention, not retried
        forever.
        """
        for step in reversed(self.completed_steps):
            try:
                logger.info(f"Saga: compensating {step.name}")
                step.compensation()
            except Exception as e:
                logger.error(
                    f"Saga: compensation for {step.name} failed: {e}. "
                    f"Manual intervention required!"
                )
        self.completed_steps.clear()


def test_2pc_commit():
    """Test successful 2PC commit."""
    participants = {
        "orders": Participant("orders"),
        "payments": Participant("payments"),
        "inventory": Participant("inventory"),
    }
    coordinator = TwoPhaseCommitCoordinator(participants)

    result = coordinator.execute({
        "orders": {"action": "create_order", "order_id": "O-001"},
        "payments": {"action": "charge", "amount": 99.99},
        "inventory": {"action": "reserve", "item": "WIDGET-42"},
    })

    assert result is True, "Transaction should commit"
    assert "orders" in [
        p for p in participants if participants[p]._committed_txns
    ]
    print("2PC commit test passed")


def test_2pc_abort():
    """Test 2PC abort when one participant votes NO."""
    participants = {
        "orders": Participant("orders"),
        "payments": Participant("payments"),
    }
    coordinator = TwoPhaseCommitCoordinator(participants)

    result = coordinator.execute({
        "orders": {"action": "create_order"},
        "payments": {"action": "charge", "should_fail": True},
    })

    assert result is False, "Transaction should abort"
    print("2PC abort test passed")


def test_saga_compensation():
    """Test saga with compensation on failure."""
    actions_log: list[str] = []

    saga = SagaOrchestrator([
        SagaStep(
            name="reserve_inventory",
            action=lambda: (actions_log.append("reserved"), True)[1],
            compensation=lambda: (actions_log.append("unreserved"), True)[1],
        ),
        SagaStep(
            name="charge_payment",
            action=lambda: (actions_log.append("charged"), True)[1],
            compensation=lambda: (actions_log.append("refunded"), True)[1],
        ),
        SagaStep(
            name="ship_order",
            action=lambda: False,  # This step fails
            compensation=lambda: (actions_log.append("unshipped"), True)[1],
        ),
    ])

    result = saga.execute()
    assert result is False
    assert "reserved" in actions_log
    assert "charged" in actions_log
    assert "refunded" in actions_log
    assert "unreserved" in actions_log
    print(f"Saga compensation test passed. Actions: {actions_log}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_2pc_commit()
    test_2pc_abort()
    test_saga_compensation()
```

## Protocol Comparison

| Property | 2PC | 3PC | Saga |
|----------|-----|-----|------|
| **Atomicity** | Strong | Strong | Eventual |
| **Blocking on coordinator failure** | **Yes** | No (non-blocking) | N/A |
| **Network partitions** | Blocks | Can be unsafe | Handles gracefully |
| **Lock duration** | Entire transaction | Entire transaction | Per-step only |
| **Performance** | Slow (2 round-trips + fsync) | Slower (3 round-trips) | Fast (no coordination) |
| **Complexity** | Medium | High | High (compensations) |
| **Best for** | Short DB transactions | Theoretical interest | Long-running business processes |

## Key Takeaways

- **2PC** guarantees atomicity but is a **blocking protocol** — if the coordinator crashes after collecting votes, participants hold locks indefinitely until recovery
- The coordinator's **WAL** is the most critical component: the decision must be persisted before sending phase 2 messages, otherwise recovery is impossible
- **3PC** adds a "pre-commit" phase to make the protocol non-blocking, but it's **not partition-tolerant** and rarely used in practice — modern systems use Paxos/Raft-based commit protocols instead
- **Sagas** trade strong consistency for availability and performance — each step commits independently, and failures trigger compensating transactions in reverse order
- **Best practice**: Use 2PC within a single database cluster (where coordinator failure is rare) and Sagas across service boundaries (where long-held locks are unacceptable and business-level compensation is natural)
"""
    ),
]
