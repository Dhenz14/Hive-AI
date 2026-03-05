"""
Batch P6 — Database Internals: Storage Engines, WAL, Query Optimization, MVCC, Connection Pooling.
Covers: B-tree/LSM-tree internals, write-ahead logging, cost-based query optimization,
multi-version concurrency control, connection pooling architectures.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. B-tree and LSM-tree Storage Engines ---
    (
        "databases/btree-lsm-storage-engines",
        "Explain the internal architecture of B+ tree and LSM-tree storage engines used in modern databases, covering page structure, page splits, merge strategies, compaction algorithms, write amplification analysis, and read/write trade-offs. Include a Python B-tree implementation with search, insert, split, and range scan operations, and compare when to use each engine type.",
        r"""# B-tree and LSM-tree Storage Engines: The Foundation of Every Database

## Why Storage Engine Choice Matters

Every database you interact with is fundamentally limited by its storage engine. The storage engine determines **how data is physically organized on disk**, and this single decision cascades into every performance characteristic: read latency, write throughput, space amplification, and recovery time. Understanding the two dominant paradigms -- B+ trees and LSM-trees -- is essential because they represent fundamentally different trade-offs that affect every query your application executes.

The core tension is this: **optimizing for reads and optimizing for writes are opposing goals**. B+ trees optimize for reads by maintaining a sorted, in-place structure that enables point lookups in O(log n) I/O operations. LSM-trees optimize for writes by converting random writes into sequential writes through buffering and periodic compaction. However, neither approach is universally superior -- the best choice depends on your workload's read/write ratio, latency requirements, and storage constraints.

## B+ Tree Architecture

### Page Structure and Organization

A B+ tree is a self-balancing tree where **all data lives in the leaf nodes** and internal nodes contain only keys and pointers. This is the critical difference from a plain B-tree: because internal nodes don't store values, they can hold more keys per page, resulting in a shallower tree and fewer I/O operations per lookup.

The fundamental unit is a **page** (typically 4KB-16KB, matching the OS page size). Each page contains:
- A page header (page type, number of keys, free space pointer, right-sibling pointer)
- An array of key-pointer pairs (internal nodes) or key-value pairs (leaf nodes)
- Free space for future insertions

A typical B+ tree with 4KB pages and 8-byte keys can fit approximately 500 keys per internal node. Therefore, a tree of height 3 can index over 125 million rows (500^3), meaning any row can be found with just **3 disk reads** -- this is why B+ trees dominate OLTP databases.

### Page Splits and Merges

When inserting into a full leaf page, a **page split** occurs:

1. Allocate a new page
2. Move the upper half of the keys to the new page
3. Insert the new separator key into the parent internal node
4. If the parent is also full, split recursively up the tree

Page splits are expensive because they require multiple page writes and can cascade up to the root. A common mistake is assuming splits are rare -- in write-heavy workloads with sequential keys (auto-increment IDs), every insertion hits the rightmost leaf and causes frequent splits. **Best practice**: some databases (like PostgreSQL) use "fastpath" insertion that caches the rightmost leaf page to avoid repeated tree traversals for sequential inserts.

### Python B+ Tree Implementation

```python
# B+ tree implementation with search, insert, split, and range scan
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any, Generic, Iterator, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")

# Maximum keys per node (order of the B+ tree)
# In production databases this is determined by page size / key size
MAX_KEYS = 4


@dataclass
class LeafNode(Generic[K, V]):
    # Leaf nodes store actual key-value pairs and a pointer to the next leaf
    keys: list[K] = field(default_factory=list)
    values: list[V] = field(default_factory=list)
    next_leaf: Optional[LeafNode[K, V]] = field(default=None, repr=False)

    @property
    def is_full(self) -> bool:
        return len(self.keys) >= MAX_KEYS

    def insert(self, key: K, value: V) -> None:
        # Insert key-value pair in sorted order within the leaf
        idx = bisect.bisect_left(self.keys, key)
        if idx < len(self.keys) and self.keys[idx] == key:
            # Key exists -- update value in place
            self.values[idx] = value
        else:
            self.keys.insert(idx, key)
            self.values.insert(idx, value)

    def search(self, key: K) -> Optional[V]:
        idx = bisect.bisect_left(self.keys, key)
        if idx < len(self.keys) and self.keys[idx] == key:
            return self.values[idx]
        return None


@dataclass
class InternalNode(Generic[K, V]):
    # Internal nodes store keys (separators) and child pointers
    # children[i] contains all keys < keys[i]
    # children[i+1] contains all keys >= keys[i]
    keys: list[K] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)

    @property
    def is_full(self) -> bool:
        return len(self.keys) >= MAX_KEYS


class BPlusTree(Generic[K, V]):
    # B+ tree supporting search, insert, range scan, and automatic splitting.
    #
    # Invariants maintained:
    # 1. All leaves are at the same depth
    # 2. Each node has between ceil(MAX_KEYS/2) and MAX_KEYS keys
    # 3. Leaves are linked left-to-right for efficient range scans
    # 4. Internal nodes only store separator keys, not values

    def __init__(self) -> None:
        self.root: LeafNode[K, V] | InternalNode[K, V] = LeafNode()
        self.height: int = 0

    def search(self, key: K) -> Optional[V]:
        # Point lookup: O(log_B n) where B is the branching factor
        leaf = self._find_leaf(key)
        return leaf.search(key)

    def _find_leaf(self, key: K) -> LeafNode[K, V]:
        # Traverse from root to the correct leaf node
        node = self.root
        while isinstance(node, InternalNode):
            idx = bisect.bisect_right(node.keys, key)
            node = node.children[idx]
        return node

    def insert(self, key: K, value: V) -> None:
        # Insert a key-value pair, splitting nodes as necessary
        result = self._insert_recursive(self.root, key, value)
        if result is not None:
            # Root was split -- create new root
            new_key, new_child = result
            new_root: InternalNode[K, V] = InternalNode()
            new_root.keys = [new_key]
            new_root.children = [self.root, new_child]
            self.root = new_root
            self.height += 1

    def _insert_recursive(
        self, node: Any, key: K, value: V
    ) -> Optional[tuple[K, Any]]:
        if isinstance(node, LeafNode):
            node.insert(key, value)
            if node.is_full:
                return self._split_leaf(node)
            return None

        # Internal node: find correct child and recurse
        idx = bisect.bisect_right(node.keys, key)
        result = self._insert_recursive(node.children[idx], key, value)

        if result is not None:
            new_key, new_child = result
            node.keys.insert(idx, new_key)
            node.children.insert(idx + 1, new_child)
            if node.is_full:
                return self._split_internal(node)
        return None

    def _split_leaf(
        self, leaf: LeafNode[K, V]
    ) -> tuple[K, LeafNode[K, V]]:
        # Split a full leaf into two halves and return the separator key
        mid = len(leaf.keys) // 2
        new_leaf: LeafNode[K, V] = LeafNode()
        new_leaf.keys = leaf.keys[mid:]
        new_leaf.values = leaf.values[mid:]
        new_leaf.next_leaf = leaf.next_leaf
        leaf.keys = leaf.keys[:mid]
        leaf.values = leaf.values[:mid]
        leaf.next_leaf = new_leaf
        # Separator is the first key of the new leaf
        return new_leaf.keys[0], new_leaf

    def _split_internal(
        self, node: InternalNode[K, V]
    ) -> tuple[K, InternalNode[K, V]]:
        mid = len(node.keys) // 2
        push_up_key = node.keys[mid]
        new_node: InternalNode[K, V] = InternalNode()
        new_node.keys = node.keys[mid + 1:]
        new_node.children = node.children[mid + 1:]
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]
        return push_up_key, new_node

    def range_scan(self, start: K, end: K) -> Iterator[tuple[K, V]]:
        # Efficient range scan using leaf-level linked list.
        # This is why B+ trees use leaf pointers -- sequential
        # access without re-traversing the tree for each key.
        leaf = self._find_leaf(start)
        while leaf is not None:
            for i, key in enumerate(leaf.keys):
                if key > end:
                    return
                if key >= start:
                    yield key, leaf.values[i]
            leaf = leaf.next_leaf
```

## LSM-Tree Architecture

### Write Path: MemTable to SSTables

LSM-trees (Log-Structured Merge-trees) take a radically different approach. Instead of modifying data in-place like B+ trees, they **buffer writes in memory and periodically flush to immutable sorted files** (SSTables):

1. **MemTable**: An in-memory sorted structure (typically a skip list or red-black tree) that absorbs all writes
2. **Immutable MemTable**: When the MemTable reaches a size threshold (e.g., 64MB), it becomes immutable and a new MemTable is created
3. **Flush to Level 0**: The immutable MemTable is written as a sorted SSTable file on disk
4. **Compaction**: Background threads merge overlapping SSTables to reduce read amplification

### Compaction Strategies

The compaction strategy is the **most important configuration decision** for an LSM-tree database. There are two primary strategies:

**Size-Tiered Compaction (STCS)**: SSTables of similar size are merged together. This minimizes write amplification but can have high space amplification (because multiple SSTables may contain overlapping key ranges).

**Leveled Compaction (LCS)**: SSTables are organized into levels where each level is 10x larger than the previous. Each level (except L0) has non-overlapping key ranges. This provides better read performance and lower space amplification but increases write amplification.

```python
# LSM-tree compaction simulator showing write amplification analysis
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class SSTable:
    # Represents an immutable sorted string table on disk
    level: int
    size_bytes: int
    min_key: str
    max_key: str
    num_entries: int
    bloom_filter_bits: int = 10  # bits per key for Bloom filter

    @property
    def false_positive_rate(self) -> float:
        # Bloom filter false positive probability
        # p = (1 - e^(-k*n/m))^k where k=optimal hash count
        import math
        m = self.bloom_filter_bits * self.num_entries
        k = int(0.693 * m / self.num_entries)  # optimal hash functions
        if k == 0:
            return 1.0
        return (1 - math.exp(-k * self.num_entries / m)) ** k


@dataclass
class LeveledCompactionEngine:
    # Leveled compaction: each level has non-overlapping key ranges
    # and is ~10x larger than the previous level.
    #
    # Write amplification analysis:
    #   - Level 0 -> 1: each byte written once
    #   - Level N -> N+1: in the worst case, one L(N) SSTable overlaps
    #     with 10 L(N+1) SSTables, so we rewrite 11 SSTables
    #   - Total write amp = sum over levels ~ 10 * num_levels
    #   - For 1TB database with 64MB L0: ~5 levels, ~50x write amp

    level_size_ratio: int = 10
    l0_size_bytes: int = 64 * 1024 * 1024  # 64 MB
    levels: dict[int, list[SSTable]] = field(default_factory=dict)
    total_bytes_written: int = 0
    total_bytes_compacted: int = 0

    def estimate_write_amplification(self, db_size_bytes: int) -> float:
        # Estimate total write amplification for leveled compaction
        import math
        if db_size_bytes <= self.l0_size_bytes:
            return 1.0
        num_levels = math.ceil(
            math.log(db_size_bytes / self.l0_size_bytes)
            / math.log(self.level_size_ratio)
        )
        # Each level contributes ~level_size_ratio to write amp
        return float(self.level_size_ratio * num_levels)

    def pick_compaction(self, level: int) -> list[SSTable]:
        # Select SSTables for compaction from the given level
        if level not in self.levels or not self.levels[level]:
            return []
        # Pick the SSTable with the smallest key range
        # to minimize overlap with the next level
        source = min(self.levels[level], key=lambda s: s.min_key)
        targets = [
            sst for sst in self.levels.get(level + 1, [])
            if sst.min_key <= source.max_key and sst.max_key >= source.min_key
        ]
        return [source] + targets

    def merge_sstables(
        self, tables: list[SSTable], target_level: int
    ) -> list[SSTable]:
        # Simulate merging multiple SSTables into the target level
        total_entries = sum(t.num_entries for t in tables)
        total_size = sum(t.size_bytes for t in tables)
        self.total_bytes_compacted += total_size

        # In practice, output is split into multiple SSTables
        # of a target size (e.g., 64MB each)
        target_sst_size = 64 * 1024 * 1024
        num_output = max(1, total_size // target_sst_size)
        entries_per_sst = total_entries // num_output

        return [
            SSTable(
                level=target_level,
                size_bytes=total_size // num_output,
                min_key=f"key_{i * entries_per_sst:010d}",
                max_key=f"key_{(i + 1) * entries_per_sst - 1:010d}",
                num_entries=entries_per_sst,
            )
            for i in range(num_output)
        ]
```

## B+ Tree vs LSM-Tree: When to Use Each

| Characteristic | B+ Tree | LSM-Tree |
|---|---|---|
| **Write pattern** | Random I/O (in-place update) | Sequential I/O (append + compact) |
| **Read amplification** | **Low** (1 seek per level) | Higher (check multiple levels) |
| **Write amplification** | Medium (~2-3x with WAL) | High (~10-50x with leveled compaction) |
| **Space amplification** | **Low** (~1x, data stored once) | Higher (1.1x leveled, 2-3x size-tiered) |
| **Best for** | Read-heavy OLTP (PostgreSQL, MySQL) | Write-heavy (Cassandra, RocksDB, LevelDB) |
| **Predictable latency** | Yes (consistent tree depth) | No (compaction causes spikes) |

A **common mistake** is choosing an LSM-tree database because "writes are faster" without considering the compaction overhead. In a mixed read/write workload, compaction can consume 50%+ of disk I/O bandwidth, causing read latency spikes. **Best practice**: use B+ trees for OLTP workloads where read latency matters; use LSM-trees for write-dominated workloads (logging, time-series, message queues) where you can tolerate periodic compaction pauses.

## Advanced Optimizations

### Fractional Cascading in B+ Trees

Modern B+ tree implementations use **prefix compression** in internal nodes: since adjacent keys often share prefixes (e.g., "user_1001", "user_1002"), storing only the differing suffix reduces node size and increases the branching factor. PostgreSQL's nbtree uses this technique to fit more keys per page.

### Bloom Filters in LSM-Trees

Because reading from an LSM-tree requires checking multiple levels, a **Bloom filter** per SSTable allows skipping SSTables that definitely don't contain the target key. With 10 bits per key, the false positive rate drops to ~1%, meaning most unnecessary disk reads are avoided. However, Bloom filters don't help with range queries -- this is a fundamental limitation.

```python
# Bloom filter for SSTable-level key filtering
import hashlib
import math
from typing import Sequence


class BloomFilter:
    # Space-efficient probabilistic data structure for set membership testing.
    # Used in LSM-trees to skip SSTables during point lookups.

    def __init__(self, expected_items: int, fp_rate: float = 0.01) -> None:
        # Calculate optimal size and hash count
        self.size = self._optimal_size(expected_items, fp_rate)
        self.hash_count = self._optimal_hash_count(self.size, expected_items)
        self.bit_array = bytearray(self.size // 8 + 1)

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        # m = -(n * ln(p)) / (ln(2))^2
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        # k = (m / n) * ln(2)
        return max(1, int((m / n) * math.log(2)))

    def _hashes(self, key: str) -> list[int]:
        # Double hashing technique: h(i) = h1 + i * h2
        h = hashlib.md5(key.encode()).hexdigest()
        h1 = int(h[:16], 16)
        h2 = int(h[16:], 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, key: str) -> None:
        for pos in self._hashes(key):
            self.bit_array[pos // 8] |= 1 << (pos % 8)

    def might_contain(self, key: str) -> bool:
        # Returns True if key MIGHT be present, False if DEFINITELY absent
        return all(
            self.bit_array[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(key)
        )

    @property
    def memory_bytes(self) -> int:
        return len(self.bit_array)
```

## Summary and Key Takeaways

- **B+ trees** store data in fixed-size pages with all values in leaf nodes linked sequentially; this structure provides O(log_B n) point lookups and efficient range scans because the leaf-level linked list avoids repeated tree traversals
- **Page splits** are the primary cost of B+ tree writes -- when a leaf or internal node overflows, the split propagates upward and may reach the root, creating a new tree level; sequential key patterns exacerbate this by always hitting the rightmost leaf
- **LSM-trees** convert random writes to sequential I/O by buffering in a MemTable and flushing to immutable SSTables, achieving 10-100x higher write throughput than B+ trees on spinning disks
- **Write amplification** is the hidden cost of LSM-trees: leveled compaction rewrites data approximately 10x per level, meaning a 1TB database may write 50TB to disk over its lifetime; size-tiered compaction reduces write amplification but increases space amplification
- **Best practice**: choose B+ trees (PostgreSQL, MySQL InnoDB) for read-heavy OLTP workloads; choose LSM-trees (RocksDB, Cassandra, ScyllaDB) for write-heavy or append-only workloads where you can tolerate compaction-induced latency spikes and higher space usage
"""
    ),

    # --- 2. Write-Ahead Logging (WAL) ---
    (
        "databases/write-ahead-logging",
        "Explain write-ahead logging in detail, covering the WAL protocol, crash recovery algorithms, the ARIES recovery protocol with its three phases, group commit optimization for throughput, checkpoint strategies, and log sequence numbers. Provide a complete Python WAL implementation with log writing, crash recovery, and checkpoint support.",
        r"""# Write-Ahead Logging (WAL): How Databases Survive Crashes

## Why WAL Is Non-Negotiable

Every durable database must solve a fundamental problem: **how do you guarantee that committed transactions survive a crash, while also keeping writes fast?** Writing directly to data pages on every commit is too slow (random I/O to scattered pages), but keeping changes only in memory means losing data on crash. Write-ahead logging solves this by writing a sequential log of changes **before** modifying any data pages. Because the log is append-only and sequential, it is dramatically faster than scattered page writes.

The WAL protocol guarantees two properties:
1. **Durability**: If a transaction commits, its changes survive any single failure
2. **Atomicity**: If a crash occurs mid-transaction, all partial changes are rolled back

The key insight is that sequential writes to a log file are 100-1000x faster than random writes to data pages, because disk seeks (HDD) and write amplification (SSD) dominate I/O cost. Therefore, we can **defer** the expensive data page writes and perform them lazily in the background, while relying on the WAL for crash recovery.

## The WAL Protocol in Detail

### Log Sequence Numbers (LSN)

Every WAL record is assigned a monotonically increasing **Log Sequence Number (LSN)**. The LSN serves as a global clock for the database -- it creates a total ordering of all changes. Each data page also stores the LSN of the most recent WAL record that modified it (the **page LSN**). During recovery, we compare page LSNs to WAL record LSNs to determine which changes need to be replayed.

### Write Rules

The protocol enforces two invariants:

1. **WAL Rule**: Before a modified page is written to disk, all WAL records for that page must be flushed to the log. This ensures we can always redo the changes if the page write fails.

2. **Commit Rule**: Before a transaction is reported as committed, all its WAL records (including the COMMIT record) must be flushed to stable storage. This ensures durability.

### Checkpoint Algorithms

Checkpoints limit the amount of WAL that must be replayed during recovery. Without checkpoints, recovery would need to replay the entire log from the beginning.

**Fuzzy Checkpoints** (used by PostgreSQL and InnoDB): Write a CHECKPOINT_START record, flush all dirty pages in the background, then write a CHECKPOINT_END record. During this process, normal operations continue. The trade-off is that recovery must start from CHECKPOINT_START, not CHECKPOINT_END, because pages flushed during the checkpoint window may be inconsistent.

**Sharp Checkpoints**: Quiesce all write activity, flush all dirty pages, then write a single CHECKPOINT record. Simpler recovery but causes a pause. Used mainly during shutdown.

## The ARIES Recovery Protocol

ARIES (Algorithm for Recovery and Isolation Exploiting Semantics) is the gold standard for WAL-based recovery, used by DB2, SQL Server, and (in modified form) PostgreSQL and MySQL InnoDB. It uses three phases:

### Phase 1: Analysis

Scan the WAL **forward** from the last checkpoint to determine:
- Which transactions were active at the time of crash (the **loser** transactions)
- Which data pages might be dirty (the **dirty page table**)
- The **redo LSN**: the earliest LSN from which redo must begin

### Phase 2: Redo

Scan the WAL **forward** from the redo LSN and re-apply all changes -- even for transactions that will be rolled back. This restores the database to its exact state at the moment of crash. A common mistake is thinking redo only applies to committed transactions; in fact, ARIES redoes everything and then uses the undo phase to clean up losers.

**Conditional redo**: A WAL record is only re-applied if the page LSN on disk is less than the record's LSN. This makes redo idempotent -- you can replay the log multiple times safely.

### Phase 3: Undo

Scan the WAL **backward** and undo all changes from loser transactions by writing **Compensation Log Records (CLRs)**. CLRs are themselves WAL records, which means if we crash during recovery, the next recovery can skip already-undone work. This is the key innovation of ARIES -- **recovery is itself recoverable**.

## Python WAL Implementation

```python
# Write-ahead log implementation with crash recovery and checkpoints
from __future__ import annotations

import dataclasses
import json
import os
import struct
import threading
import time
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional


class RecordType(Enum):
    UPDATE = auto()
    COMMIT = auto()
    ABORT = auto()
    CHECKPOINT_START = auto()
    CHECKPOINT_END = auto()
    CLR = auto()  # Compensation Log Record


@dataclasses.dataclass(frozen=True)
class WALRecord:
    # A single record in the write-ahead log
    lsn: int
    txn_id: int
    record_type: RecordType
    page_id: Optional[int] = None
    before_image: Optional[bytes] = None  # for undo
    after_image: Optional[bytes] = None   # for redo
    prev_lsn: int = 0  # previous LSN for this transaction (undo chain)
    undo_next_lsn: int = 0  # for CLRs: next record to undo

    def serialize(self) -> bytes:
        # Serialize to a length-prefixed binary format
        data = json.dumps({
            "lsn": self.lsn,
            "txn_id": self.txn_id,
            "type": self.record_type.name,
            "page_id": self.page_id,
            "before": self.before_image.hex() if self.before_image else None,
            "after": self.after_image.hex() if self.after_image else None,
            "prev_lsn": self.prev_lsn,
            "undo_next_lsn": self.undo_next_lsn,
        }).encode("utf-8")
        return struct.pack("!I", len(data)) + data

    @classmethod
    def deserialize(cls, data: bytes) -> WALRecord:
        obj = json.loads(data.decode("utf-8"))
        return cls(
            lsn=obj["lsn"],
            txn_id=obj["txn_id"],
            record_type=RecordType[obj["type"]],
            page_id=obj.get("page_id"),
            before_image=bytes.fromhex(obj["before"]) if obj.get("before") else None,
            after_image=bytes.fromhex(obj["after"]) if obj.get("after") else None,
            prev_lsn=obj.get("prev_lsn", 0),
            undo_next_lsn=obj.get("undo_next_lsn", 0),
        )


class WriteAheadLog:
    # Append-only WAL with group commit, checkpointing, and ARIES-style recovery.
    #
    # Group commit optimization: instead of fsyncing after every transaction,
    # we batch multiple commits and fsync once. This amortizes the cost of
    # the fsync (which takes ~1-10ms) across many transactions, boosting
    # throughput from ~100 TPS to ~10,000 TPS.

    def __init__(self, log_path: Path, group_commit_interval_ms: float = 10.0) -> None:
        self.log_path = log_path
        self.group_commit_interval = group_commit_interval_ms / 1000.0
        self._lock = threading.Lock()
        self._next_lsn = 1
        self._txn_last_lsn: dict[int, int] = {}  # txn_id -> last LSN
        self._log_buffer: list[WALRecord] = []
        self._flushed_lsn = 0
        self._log_file = open(log_path, "ab")

        # Group commit state
        self._pending_commits: list[threading.Event] = []
        self._commit_thread = threading.Thread(
            target=self._group_commit_loop, daemon=True
        )
        self._running = True
        self._commit_thread.start()

    def _group_commit_loop(self) -> None:
        # Background thread that flushes buffered WAL records periodically.
        # This is the group commit optimization: by waiting a few milliseconds,
        # multiple transactions can share a single fsync call.
        while self._running:
            time.sleep(self.group_commit_interval)
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        with self._lock:
            if not self._log_buffer:
                return
            records = self._log_buffer[:]
            events = self._pending_commits[:]
            self._log_buffer.clear()
            self._pending_commits.clear()

        # Write all buffered records and fsync once
        for record in records:
            self._log_file.write(record.serialize())
        self._log_file.flush()
        os.fsync(self._log_file.fileno())

        self._flushed_lsn = records[-1].lsn

        # Wake up all transactions waiting for their commit to be durable
        for event in events:
            event.set()

    def append(
        self,
        txn_id: int,
        record_type: RecordType,
        page_id: Optional[int] = None,
        before_image: Optional[bytes] = None,
        after_image: Optional[bytes] = None,
        undo_next_lsn: int = 0,
    ) -> int:
        with self._lock:
            lsn = self._next_lsn
            self._next_lsn += 1
            prev_lsn = self._txn_last_lsn.get(txn_id, 0)
            self._txn_last_lsn[txn_id] = lsn

            record = WALRecord(
                lsn=lsn,
                txn_id=txn_id,
                record_type=record_type,
                page_id=page_id,
                before_image=before_image,
                after_image=after_image,
                prev_lsn=prev_lsn,
                undo_next_lsn=undo_next_lsn,
            )
            self._log_buffer.append(record)

            if record_type == RecordType.COMMIT:
                event = threading.Event()
                self._pending_commits.append(event)

        # For commits, wait until the group commit flushes our record
        if record_type == RecordType.COMMIT:
            event.wait(timeout=5.0)

        return lsn

    def close(self) -> None:
        self._running = False
        self._flush_buffer()
        self._log_file.close()
```

### ARIES-Style Crash Recovery

```python
# ARIES recovery: analysis, redo, undo phases
from __future__ import annotations

from pathlib import Path
from typing import Any


class ARIESRecovery:
    # Implements the three-phase ARIES recovery algorithm.
    #
    # The beauty of ARIES is that recovery is idempotent and itself
    # crash-safe. If we crash during recovery, re-running recovery
    # produces the same result because:
    # 1. Redo is conditional (checks page LSN before applying)
    # 2. Undo writes CLRs so completed undo work is not repeated

    def __init__(
        self,
        log_path: Path,
        page_store: dict[int, tuple[int, bytes]],  # page_id -> (page_lsn, data)
    ) -> None:
        self.log_path = log_path
        self.page_store = page_store
        self.records: list[WALRecord] = []

    def load_log(self) -> None:
        # Read all WAL records from the log file
        with open(self.log_path, "rb") as f:
            data = f.read()
        offset = 0
        while offset < len(data):
            if offset + 4 > len(data):
                break
            length = struct.unpack("!I", data[offset:offset + 4])[0]
            offset += 4
            record_data = data[offset:offset + length]
            self.records.append(WALRecord.deserialize(record_data))
            offset += length

    def recover(self) -> dict[str, Any]:
        # Run the full three-phase ARIES recovery
        self.load_log()

        # Phase 1: Analysis
        active_txns, dirty_pages, redo_lsn = self._analysis_phase()

        # Phase 2: Redo
        self._redo_phase(redo_lsn, dirty_pages)

        # Phase 3: Undo
        self._undo_phase(active_txns)

        return {
            "records_processed": len(self.records),
            "transactions_undone": len(active_txns),
            "pages_redone": len(dirty_pages),
        }

    def _analysis_phase(
        self,
    ) -> tuple[dict[int, int], dict[int, int], int]:
        # Scan forward from last checkpoint to build transaction
        # table and dirty page table
        active_txns: dict[int, int] = {}   # txn_id -> last_lsn
        dirty_pages: dict[int, int] = {}   # page_id -> first_dirty_lsn
        redo_lsn = self.records[0].lsn if self.records else 0

        for record in self.records:
            if record.record_type == RecordType.CHECKPOINT_END:
                redo_lsn = record.lsn
                continue

            active_txns[record.txn_id] = record.lsn

            if record.record_type in (RecordType.UPDATE, RecordType.CLR):
                if record.page_id is not None and record.page_id not in dirty_pages:
                    dirty_pages[record.page_id] = record.lsn

            if record.record_type in (RecordType.COMMIT, RecordType.ABORT):
                active_txns.pop(record.txn_id, None)

        return active_txns, dirty_pages, redo_lsn

    def _redo_phase(
        self, redo_lsn: int, dirty_pages: dict[int, int]
    ) -> None:
        # Scan forward and conditionally redo all operations
        for record in self.records:
            if record.lsn < redo_lsn:
                continue
            if record.record_type not in (RecordType.UPDATE, RecordType.CLR):
                continue
            if record.page_id is None or record.after_image is None:
                continue
            # Conditional redo: only apply if page LSN < record LSN
            page_lsn, _ = self.page_store.get(record.page_id, (0, b""))
            if page_lsn < record.lsn:
                self.page_store[record.page_id] = (
                    record.lsn, record.after_image
                )

    def _undo_phase(self, active_txns: dict[int, int]) -> None:
        # Scan backward and undo all loser transactions
        # by applying before-images in reverse order
        for record in reversed(self.records):
            if record.txn_id not in active_txns:
                continue
            if record.record_type == RecordType.UPDATE:
                if record.page_id is not None and record.before_image is not None:
                    self.page_store[record.page_id] = (
                        record.lsn, record.before_image
                    )
            if record.lsn <= min(active_txns.values()):
                break
```

## Group Commit: The Throughput Multiplier

The single most impactful optimization for transaction throughput is **group commit**. Without it, each transaction requires its own fsync, limiting throughput to ~100 TPS on SSDs (1/fsync_latency). With group commit, we buffer commits for a short window (typically 1-10ms) and flush them all with a single fsync, achieving **10,000+ TPS**.

The trade-off is **latency vs throughput**: each transaction's commit latency increases by the group commit interval, but overall throughput increases by orders of magnitude. PostgreSQL implements this with `wal_writer_delay` (default 200ms) and `commit_delay` parameters.

```python
# Benchmarking group commit vs individual commit throughput
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class GroupCommitBenchmark:
    # Simulates the throughput difference between individual and group commit
    fsync_latency_ms: float = 2.0   # typical SSD fsync latency
    group_interval_ms: float = 10.0  # group commit window

    def individual_commit_tps(self, num_txns: int) -> float:
        # Each transaction pays the full fsync cost
        total_time_ms = num_txns * self.fsync_latency_ms
        return num_txns / (total_time_ms / 1000.0)

    def group_commit_tps(self, num_txns: int, concurrency: int = 50) -> float:
        # Transactions within a group window share a single fsync
        num_groups = max(1, num_txns // concurrency)
        # Each group pays one fsync cost + the group interval
        total_time_ms = num_groups * (self.fsync_latency_ms + self.group_interval_ms)
        return num_txns / (total_time_ms / 1000.0)

    def report(self, num_txns: int = 10000) -> dict[str, float]:
        individual = self.individual_commit_tps(num_txns)
        group = self.group_commit_tps(num_txns)
        return {
            "individual_tps": round(individual, 1),
            "group_commit_tps": round(group, 1),
            "speedup": round(group / individual, 1),
        }
```

## Summary and Key Takeaways

- **WAL guarantees durability and atomicity** by writing changes to a sequential log before modifying data pages; sequential I/O is 100-1000x faster than random page writes, so this adds minimal overhead
- **Log Sequence Numbers (LSNs)** provide a total ordering of all database changes; each data page stores its page LSN, enabling conditional redo during recovery where already-applied changes are safely skipped
- **ARIES recovery** uses three phases -- analysis (identify losers and dirty pages), redo (restore crash-time state by replaying all logged changes), undo (roll back uncommitted transactions using before-images) -- and writes CLRs during undo so recovery is itself crash-safe
- **Group commit** is the most important throughput optimization: batching multiple fsync calls into one amortizes the 1-10ms fsync cost across many transactions, boosting throughput from ~100 TPS to 10,000+ TPS at the cost of slightly increased commit latency
- **Best practice**: tune the checkpoint interval to balance recovery time against I/O overhead -- frequent checkpoints mean shorter recovery but more background I/O; PostgreSQL defaults to 5 minutes (`checkpoint_timeout`) which is a reasonable starting point for most workloads
"""
    ),

    # --- 3. Query Optimizer Internals ---
    (
        "databases/query-optimizer-internals",
        "Explain the internals of database query optimizers including cost-based optimization, join ordering algorithms, index selection heuristics, selectivity estimation and histogram statistics, cardinality estimation errors, and plan caching. Build a Python query plan generator that models cost estimation, join ordering, and index selection for a simplified SQL engine.",
        r"""# Query Optimizer Internals: How Databases Choose Execution Plans

## Why Query Optimization Is Hard

The query optimizer is arguably the most complex component in any relational database. Its job sounds simple: given a SQL query, find the fastest way to execute it. However, the search space grows **factorially** with the number of tables -- a 10-table join has 10! = 3,628,800 possible orderings, each with multiple join algorithm choices (nested loop, hash, merge) and index options. Finding the true optimal plan is NP-hard, so optimizers use heuristics, dynamic programming, and cost models to find a "good enough" plan quickly.

A **common mistake** among developers is assuming the optimizer always makes the right choice. In practice, cardinality estimation errors cascade through the plan, causing the optimizer to choose hash joins when nested loops would be faster, or full table scans when an index exists. Understanding how the optimizer works helps you write queries that help (rather than confuse) the optimizer, and diagnose performance problems when the chosen plan is suboptimal.

## Cost-Based Optimization Architecture

### The Optimizer Pipeline

A SQL query passes through several stages before execution:

1. **Parsing**: SQL text to abstract syntax tree (AST)
2. **Semantic analysis**: Resolve table/column names, check types
3. **Logical optimization**: Apply heuristic rewrites (predicate pushdown, constant folding, subquery flattening)
4. **Physical optimization**: Choose join algorithms, access methods, and join ordering based on cost estimation
5. **Plan caching**: Store the optimized plan for reuse with different parameter values

### Cost Model Components

The cost model estimates execution time using three I/O-based metrics:

- **Sequential I/O cost**: Reading consecutive pages (cheap, ~0.1ms per page)
- **Random I/O cost**: Seeking to arbitrary pages (expensive, ~1-4ms per page on SSD)
- **CPU cost**: Per-tuple processing (comparisons, hashing, projections)

PostgreSQL's cost formula for a sequential scan is:
`cost = seq_page_cost * num_pages + cpu_tuple_cost * num_rows`

For an index scan:
`cost = random_page_cost * index_pages + cpu_index_tuple_cost * index_tuples + random_page_cost * heap_pages_fetched`

The critical insight is that **random I/O is 4-40x more expensive than sequential I/O**, which is why the optimizer often prefers a sequential scan over an index scan for queries that touch more than ~5-20% of the table.

### Selectivity Estimation and Histograms

The optimizer needs to estimate how many rows each operation produces (its **cardinality**). This drives every downstream cost calculation. Databases maintain **column statistics** including:

- **n_distinct**: Number of distinct values
- **Most Common Values (MCV)**: Top-N values and their frequencies
- **Histogram**: Equal-depth histogram of value distribution (excluding MCVs)
- **Correlation**: How well the physical row order matches the column's logical order (important for index scan cost)

For a predicate like `WHERE age > 30`, the optimizer uses the histogram to estimate selectivity. If 60% of the histogram buckets have values > 30, the estimated selectivity is 0.60.

**Pitfall**: The optimizer assumes predicates are independent. For `WHERE city = 'NYC' AND income > 100000`, it multiplies selectivities: `sel(city) * sel(income)`. But in reality, NYC residents have higher incomes, so the true selectivity is much lower than the estimate. This correlation blindness is the **single largest source of bad plans** in production databases.

## Python Query Plan Generator

```python
# Cost-based query optimizer with join ordering and index selection
from __future__ import annotations

import dataclasses
import itertools
import math
from enum import Enum, auto
from typing import Optional


class JoinAlgorithm(Enum):
    NESTED_LOOP = auto()
    HASH_JOIN = auto()
    MERGE_JOIN = auto()


class ScanType(Enum):
    SEQUENTIAL = auto()
    INDEX = auto()
    INDEX_ONLY = auto()


@dataclasses.dataclass
class ColumnStats:
    # Statistics for a single column, used for selectivity estimation
    n_distinct: int
    min_value: float
    max_value: float
    null_fraction: float = 0.0
    correlation: float = 0.0  # physical-logical order correlation
    histogram_bounds: list[float] = dataclasses.field(default_factory=list)
    most_common_vals: list[tuple[str, float]] = dataclasses.field(
        default_factory=list
    )


@dataclasses.dataclass
class TableStats:
    # Table-level statistics for cost estimation
    name: str
    num_rows: int
    num_pages: int
    row_width_bytes: int
    columns: dict[str, ColumnStats] = dataclasses.field(default_factory=dict)
    indexes: list[IndexInfo] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class IndexInfo:
    name: str
    table: str
    columns: list[str]
    is_unique: bool = False
    num_pages: int = 0
    # B-tree height determines number of random reads for a lookup
    tree_height: int = 3


@dataclasses.dataclass
class CostFactors:
    # I/O cost model parameters (PostgreSQL defaults)
    seq_page_cost: float = 1.0
    random_page_cost: float = 4.0
    cpu_tuple_cost: float = 0.01
    cpu_index_tuple_cost: float = 0.005
    cpu_operator_cost: float = 0.0025
    # Hash join and sort memory
    work_mem_pages: int = 256  # 2MB / 8KB pages


@dataclasses.dataclass
class PlanNode:
    # A node in the query execution plan tree
    operation: str
    estimated_rows: float
    estimated_cost: float
    table: Optional[str] = None
    join_algorithm: Optional[JoinAlgorithm] = None
    scan_type: Optional[ScanType] = None
    index_name: Optional[str] = None
    children: list[PlanNode] = dataclasses.field(default_factory=list)
    predicates: list[str] = dataclasses.field(default_factory=list)

    def explain(self, indent: int = 0) -> str:
        # Generate EXPLAIN-style output
        prefix = "  " * indent
        parts = [f"{prefix}{self.operation}"]
        if self.table:
            parts[0] += f" on {self.table}"
        if self.index_name:
            parts[0] += f" using {self.index_name}"
        parts[0] += f"  (cost={self.estimated_cost:.2f} rows={self.estimated_rows:.0f})"
        for pred in self.predicates:
            parts.append(f"{prefix}  Filter: {pred}")
        for child in self.children:
            parts.append(child.explain(indent + 1))
        return "\n".join(parts)


class QueryOptimizer:
    # Cost-based query optimizer using dynamic programming for join ordering
    # and cost estimation for access method selection.
    #
    # The optimizer explores the space of possible plans bottom-up:
    # 1. Enumerate single-table access plans (seq scan vs index scan)
    # 2. Build two-table join plans from single-table plans
    # 3. Extend to three-table joins, etc.
    # This is the System R dynamic programming approach.

    def __init__(self, cost_factors: Optional[CostFactors] = None) -> None:
        self.costs = cost_factors or CostFactors()
        self.tables: dict[str, TableStats] = {}

    def register_table(self, stats: TableStats) -> None:
        self.tables[stats.name] = stats

    def estimate_selectivity(
        self, table: str, column: str, operator: str, value: float
    ) -> float:
        # Estimate the fraction of rows matching a predicate
        stats = self.tables[table].columns.get(column)
        if stats is None:
            # No statistics -- use default selectivity
            return 0.33 if operator == "=" else 0.5

        if operator == "=":
            # Check most common values first
            for val, freq in stats.most_common_vals:
                if str(val) == str(value):
                    return freq
            # Otherwise assume uniform distribution among non-MCV values
            mcv_freq = sum(f for _, f in stats.most_common_vals)
            return (1.0 - mcv_freq) / max(1, stats.n_distinct)

        if operator in ("<", "<="):
            # Use histogram bounds for range predicates
            if stats.histogram_bounds:
                below = sum(
                    1 for b in stats.histogram_bounds if b <= value
                )
                return below / len(stats.histogram_bounds)
            # Fallback: linear interpolation
            data_range = stats.max_value - stats.min_value
            if data_range == 0:
                return 0.5
            return (value - stats.min_value) / data_range

        if operator in (">", ">="):
            return 1.0 - self.estimate_selectivity(
                table, column, "<=", value
            )

        return 0.33  # default

    def _scan_cost(self, table: str, selectivity: float) -> tuple[PlanNode, float]:
        # Choose between sequential scan and index scan
        stats = self.tables[table]
        est_rows = stats.num_rows * selectivity

        # Sequential scan cost
        seq_cost = (
            self.costs.seq_page_cost * stats.num_pages
            + self.costs.cpu_tuple_cost * stats.num_rows
        )
        best_plan = PlanNode(
            operation="Seq Scan",
            estimated_rows=est_rows,
            estimated_cost=seq_cost,
            table=table,
            scan_type=ScanType.SEQUENTIAL,
        )
        best_cost = seq_cost

        # Check each index
        for idx in stats.indexes:
            # Estimate pages fetched via index
            index_tuples = stats.num_rows * selectivity
            # Heap pages fetched depends on correlation
            col_stats = stats.columns.get(idx.columns[0])
            correlation = col_stats.correlation if col_stats else 0.0

            # High correlation means sequential access pattern
            # Low correlation means random access
            heap_pages = est_rows * (1 - abs(correlation)) + (
                stats.num_pages * selectivity * abs(correlation)
            )
            heap_pages = min(heap_pages, stats.num_pages)

            idx_cost = (
                self.costs.random_page_cost * idx.tree_height
                + self.costs.cpu_index_tuple_cost * index_tuples
                + self.costs.random_page_cost * heap_pages * (1 - abs(correlation))
                + self.costs.seq_page_cost * heap_pages * abs(correlation)
                + self.costs.cpu_tuple_cost * est_rows
            )

            if idx_cost < best_cost:
                best_cost = idx_cost
                best_plan = PlanNode(
                    operation="Index Scan",
                    estimated_rows=est_rows,
                    estimated_cost=idx_cost,
                    table=table,
                    scan_type=ScanType.INDEX,
                    index_name=idx.name,
                )

        return best_plan, best_cost

    def _join_cost(
        self,
        left: PlanNode,
        right: PlanNode,
        algorithm: JoinAlgorithm,
    ) -> float:
        # Estimate cost for different join algorithms
        if algorithm == JoinAlgorithm.NESTED_LOOP:
            # For each row in left, scan all rows in right
            return (
                left.estimated_cost
                + left.estimated_rows * right.estimated_cost
            )

        if algorithm == JoinAlgorithm.HASH_JOIN:
            # Build hash table on smaller side, probe with larger
            build_cost = left.estimated_cost + self.costs.cpu_tuple_cost * left.estimated_rows
            probe_cost = right.estimated_cost + self.costs.cpu_tuple_cost * right.estimated_rows
            return build_cost + probe_cost

        if algorithm == JoinAlgorithm.MERGE_JOIN:
            # Both sides must be sorted -- add sort cost if not from index
            sort_cost_left = (
                left.estimated_rows * math.log2(max(1, left.estimated_rows))
                * self.costs.cpu_operator_cost
            )
            sort_cost_right = (
                right.estimated_rows * math.log2(max(1, right.estimated_rows))
                * self.costs.cpu_operator_cost
            )
            merge_cost = self.costs.cpu_tuple_cost * (
                left.estimated_rows + right.estimated_rows
            )
            return (
                left.estimated_cost + right.estimated_cost
                + sort_cost_left + sort_cost_right + merge_cost
            )

        return float("inf")

    def optimize_join_order(
        self,
        table_names: list[str],
        predicates: dict[str, float],  # "table.col op val" -> selectivity
    ) -> PlanNode:
        # Dynamic programming join ordering (System R algorithm).
        # For N tables, we build optimal plans bottom-up:
        # 1. Best single-table plans
        # 2. Best two-table plans (from pairs of single-table plans)
        # 3. Best N-table plan

        # Step 1: single-table access plans
        single_plans: dict[frozenset[str], PlanNode] = {}
        for t in table_names:
            sel = predicates.get(t, 1.0)
            plan, _ = self._scan_cost(t, sel)
            single_plans[frozenset([t])] = plan

        # Step 2: build up join plans using DP
        dp: dict[frozenset[str], PlanNode] = dict(single_plans)

        for size in range(2, len(table_names) + 1):
            for combo in itertools.combinations(table_names, size):
                combo_set = frozenset(combo)
                best_plan: Optional[PlanNode] = None
                best_cost = float("inf")

                # Try all ways to split into two non-empty subsets
                for i in range(1, size):
                    for left_tables in itertools.combinations(combo, i):
                        left_set = frozenset(left_tables)
                        right_set = combo_set - left_set
                        if left_set not in dp or right_set not in dp:
                            continue

                        left_plan = dp[left_set]
                        right_plan = dp[right_set]

                        # Try each join algorithm
                        for algo in JoinAlgorithm:
                            cost = self._join_cost(left_plan, right_plan, algo)
                            if cost < best_cost:
                                best_cost = cost
                                est_rows = (
                                    left_plan.estimated_rows
                                    * right_plan.estimated_rows
                                    * 0.1  # default join selectivity
                                )
                                best_plan = PlanNode(
                                    operation=f"{algo.name} Join",
                                    estimated_rows=est_rows,
                                    estimated_cost=best_cost,
                                    join_algorithm=algo,
                                    children=[left_plan, right_plan],
                                )

                if best_plan is not None:
                    dp[combo_set] = best_plan

        return dp[frozenset(table_names)]
```

## Index Selection Heuristics

### When the Optimizer Skips an Index

Understanding why the optimizer ignores your carefully-created index is a critical debugging skill. Common reasons:

1. **Low selectivity**: If the predicate matches >5-20% of rows, a sequential scan is cheaper because it avoids random I/O
2. **No covering index**: If the query needs columns not in the index, each index hit requires a heap fetch (random I/O)
3. **Stale statistics**: `ANALYZE` hasn't run recently, so the optimizer's cardinality estimates are wrong
4. **Type mismatch**: `WHERE id = '42'` when `id` is integer -- the implicit cast prevents index use
5. **Function wrapping**: `WHERE LOWER(name) = 'john'` cannot use a plain B-tree index on `name`

```python
# Index advisor: suggest indexes based on query workload
from collections import Counter
from typing import NamedTuple


class QueryPattern(NamedTuple):
    table: str
    columns: tuple[str, ...]
    operation: str  # "equality", "range", "sort", "join"
    frequency: int


class IndexAdvisor:
    # Analyzes query workload patterns and recommends indexes.
    #
    # The key insight is that index creation is itself a trade-off:
    # each index speeds up reads but slows down writes (because
    # every INSERT/UPDATE/DELETE must also update the index).
    # Therefore, we should only create indexes that benefit
    # frequently-executed queries.

    def __init__(self, max_indexes_per_table: int = 5) -> None:
        self.max_indexes = max_indexes_per_table
        self.patterns: list[QueryPattern] = []

    def add_pattern(self, pattern: QueryPattern) -> None:
        self.patterns.append(pattern)

    def recommend(self) -> list[dict[str, Any]]:
        # Group patterns by table and find beneficial indexes
        table_patterns: dict[str, list[QueryPattern]] = {}
        for p in self.patterns:
            table_patterns.setdefault(p.table, []).append(p)

        recommendations = []
        for table, patterns in table_patterns.items():
            # Score each column combination by frequency * selectivity benefit
            col_scores: Counter[tuple[str, ...]] = Counter()
            for p in patterns:
                # Equality predicates benefit most from indexes
                weight = {"equality": 3, "range": 2, "join": 2, "sort": 1}
                col_scores[p.columns] += p.frequency * weight.get(p.operation, 1)

            # Take top-N column combinations
            for cols, score in col_scores.most_common(self.max_indexes):
                recommendations.append({
                    "table": table,
                    "columns": list(cols),
                    "score": score,
                    "create_sql": (
                        f"CREATE INDEX idx_{table}_{'_'.join(cols)} "
                        f"ON {table} ({', '.join(cols)})"
                    ),
                })

        return recommendations
```

## Cardinality Estimation: The Achilles' Heel

The optimizer's Achilles' heel is **cardinality estimation**. When the estimated row count is wrong by even 10x, the optimizer may choose a catastrophically bad plan. The most common causes:

- **Correlated predicates**: `city = 'NYC' AND salary > 100000` -- the optimizer multiplies independent selectivities, but NYC salaries are higher
- **Skewed distributions**: A uniform-distribution assumption fails for Zipf-distributed data (usernames, product IDs)
- **Join cardinality**: Estimating the output size of a multi-table join compounds errors multiplicatively

```python
# Plan analysis tool: compare estimated vs actual cardinality
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlanAnalysis:
    # Detects cardinality estimation errors by comparing EXPLAIN vs EXPLAIN ANALYZE
    node_type: str
    estimated_rows: float
    actual_rows: Optional[float] = None
    children: list[PlanAnalysis] = field(default_factory=list)

    @property
    def estimation_error(self) -> Optional[float]:
        # Ratio of actual/estimated -- values far from 1.0 indicate bad estimates
        if self.actual_rows is None or self.estimated_rows == 0:
            return None
        return self.actual_rows / self.estimated_rows

    @property
    def is_severely_off(self) -> bool:
        # More than 10x error in either direction is a red flag
        err = self.estimation_error
        return err is not None and (err > 10.0 or err < 0.1)

    def find_bad_estimates(self) -> list[PlanAnalysis]:
        # Recursively find all nodes with severe cardinality errors
        bad: list[PlanAnalysis] = []
        if self.is_severely_off:
            bad.append(self)
        for child in self.children:
            bad.extend(child.find_bad_estimates())
        return bad

    def suggest_fix(self) -> str:
        if not self.is_severely_off:
            return "Estimates are within acceptable range"
        err = self.estimation_error
        if err and err > 10.0:
            return (
                f"{self.node_type}: actual rows {err:.1f}x higher than estimated. "
                f"Run ANALYZE on the table or create extended statistics "
                f"for correlated columns."
            )
        return (
            f"{self.node_type}: actual rows {err:.1f}x lower than estimated. "
            f"Check for stale statistics or highly selective predicates "
            f"not captured by histogram bounds."
        )
```

**Best practice**: Use `EXPLAIN ANALYZE` (PostgreSQL) or `EXPLAIN FORMAT=TREE` (MySQL) to compare estimated vs actual row counts. A discrepancy of >10x indicates a statistics problem. Run `ANALYZE` on the table, or consider creating extended statistics (PostgreSQL 10+) for correlated columns.

## Summary and Key Takeaways

- **Cost-based optimizers** model execution cost using I/O and CPU metrics; random I/O costs 4-40x more than sequential I/O, which is why the optimizer often prefers sequential scans over index scans for low-selectivity predicates
- **Join ordering** uses dynamic programming (System R algorithm) to explore the exponential space of join permutations; for N tables, the search space is O(2^N) with DP compared to O(N!) with brute force, making plans up to ~15 tables feasible
- **Selectivity estimation** relies on column statistics (histograms, MCVs, n_distinct); the optimizer assumes predicate independence, which fails for correlated columns and is the single largest source of suboptimal plans
- **Index selection** depends on selectivity, correlation, and covering -- an index is only beneficial when the predicate filters enough rows that the random I/O cost of index lookups is less than the sequential I/O cost of a full scan
- **Best practice**: always compare estimated vs actual row counts with `EXPLAIN ANALYZE`; when estimates diverge by more than 10x, update statistics with `ANALYZE` or create multi-column statistics to capture correlations
"""
    ),

    # --- 4. MVCC (Multi-Version Concurrency Control) ---
    (
        "databases/mvcc-implementation",
        "Explain multi-version concurrency control in depth, covering snapshot isolation, version chain management, transaction visibility rules, garbage collection of old versions, write-write conflict detection, and how PostgreSQL and MySQL InnoDB implement MVCC differently. Provide a complete Python MVCC implementation with snapshot reads, version chains, and conflict detection.",
        r"""# MVCC: How Databases Let Readers and Writers Coexist

## The Fundamental Problem MVCC Solves

Traditional lock-based concurrency has a devastating limitation: **readers block writers and writers block readers**. A long-running analytics query holds shared locks that prevent any writes to those rows, and a write transaction holds exclusive locks that block all reads. In a mixed OLTP/analytics workload, this creates a deadlock of business requirements -- you can't run reports without slowing down transactions.

MVCC eliminates this conflict by maintaining **multiple versions of each row**. Readers see a consistent snapshot of the database at a point in time, without acquiring any locks. Writers create new versions rather than modifying existing ones. Because readers never block writers and writers never block readers, MVCC enables dramatically higher concurrency than lock-based schemes.

However, MVCC introduces its own trade-offs: **storage overhead** (multiple versions consume disk space), **garbage collection complexity** (old versions must be reclaimed), and **write-write conflicts** (two transactions writing the same row must still be serialized). Understanding these trade-offs is essential for tuning MVCC-based databases.

## Snapshot Isolation

### How Snapshots Work

When a transaction begins (or, in PostgreSQL's case, when it executes its first statement in READ COMMITTED mode), it captures a **snapshot** of the database. The snapshot records:

1. **The current transaction ID (xid)**: All changes by transactions with higher xids are invisible
2. **The set of active (in-progress) transaction IDs**: Changes by these transactions are invisible, even if their xids are lower
3. **The minimum active xid (xmin horizon)**: All transactions below this have definitely committed or aborted

A row version is **visible** to a snapshot if and only if:
- The creating transaction committed before the snapshot was taken
- The creating transaction is not in the snapshot's active transaction set
- The row has not been deleted (or the deleting transaction is not yet visible)

### Write-Write Conflict Detection

Snapshot isolation prevents most anomalies but must still handle **write-write conflicts**. When two transactions try to update the same row, the second writer detects the conflict and must either wait (PostgreSQL) or fail immediately (some systems). The rule is simple: **first writer wins**.

A **common mistake** is confusing snapshot isolation with serializable isolation. Snapshot isolation allows the **write skew** anomaly: two transactions read overlapping data, make disjoint writes based on what they read, and both commit -- but the combined result is inconsistent. For example, two doctors both check that at least one doctor is on call, each removes themselves, and now no one is on call.

## PostgreSQL vs MySQL MVCC Comparison

| Aspect | PostgreSQL | MySQL InnoDB |
|---|---|---|
| **Version storage** | In-place (heap tuple) | Undo log (rollback segment) |
| **Old versions** | Stored in main table (dead tuples) | Stored in undo tablespace |
| **Garbage collection** | VACUUM process | Purge thread |
| **Visibility check** | xmin/xmax in tuple header | Read view + undo chain |
| **Update mechanism** | Insert new tuple + mark old as dead | Modify in-place + write undo record |
| **Index impact** | Every version has its own index entry | Index points to latest version |
| **Bloat risk** | **High** (VACUUM must run regularly) | Lower (undo space is reclaimed) |

### PostgreSQL's Approach: Heap-Based MVCC

PostgreSQL stores all row versions directly in the table heap. Each tuple has a header with:
- **xmin**: Transaction ID that created this version
- **xmax**: Transaction ID that deleted/updated this version (0 if live)
- **ctid**: Physical location of the next version in the update chain
- **infomask bits**: Flags indicating committed/aborted status

When a row is updated, PostgreSQL inserts an entirely new tuple and sets the old tuple's xmax to the updating transaction's ID. This means **every update creates a dead tuple** that must be cleaned up by VACUUM. This is the source of the notorious "table bloat" problem.

### MySQL InnoDB's Approach: Undo-Log MVCC

InnoDB takes the opposite approach: it modifies the row in-place and writes the old version to an **undo log** (rollback segment). To read an older version, the system follows the undo chain backward until it finds a version visible to the snapshot.

This design has better write performance (only one tuple per row in the main table) but worse read performance for long-running transactions (which may need to traverse a long undo chain). The trade-off favors OLTP workloads with short transactions.

## Python MVCC Implementation

```python
# Multi-version concurrency control with snapshot isolation
from __future__ import annotations

import dataclasses
import threading
from enum import Enum, auto
from typing import Any, Optional


class TxnStatus(Enum):
    ACTIVE = auto()
    COMMITTED = auto()
    ABORTED = auto()


@dataclasses.dataclass
class RowVersion:
    # A single version of a row in the MVCC store
    key: str
    value: Any
    created_by: int       # transaction ID that created this version
    deleted_by: int = 0   # transaction ID that deleted this version (0 = live)
    prev_version: Optional[RowVersion] = None  # pointer to older version

    @property
    def is_deleted(self) -> bool:
        return self.deleted_by != 0


@dataclasses.dataclass
class Snapshot:
    # A consistent point-in-time view of the database.
    #
    # Visibility rules:
    # 1. Created by a committed txn with xid < snapshot_xid: VISIBLE
    # 2. Created by a txn in active_txns set: INVISIBLE (even if xid < snapshot_xid)
    # 3. Created by a txn with xid >= snapshot_xid: INVISIBLE
    # 4. Deleted by a committed txn with xid < snapshot_xid: INVISIBLE (row is gone)
    snapshot_xid: int
    active_txns: frozenset[int]

    def is_visible(
        self,
        version: RowVersion,
        txn_status: dict[int, TxnStatus],
        own_txn_id: int,
    ) -> bool:
        # Check whether this row version is visible to this snapshot
        creator = version.created_by

        # Own changes are always visible
        if creator == own_txn_id:
            # Unless we also deleted it in the same transaction
            if version.deleted_by == own_txn_id:
                return False
            return True

        # Creator must have committed
        if txn_status.get(creator) != TxnStatus.COMMITTED:
            return False

        # Creator must not be in the active set at snapshot time
        if creator in self.active_txns:
            return False

        # Creator must have started before snapshot
        if creator >= self.snapshot_xid:
            return False

        # Check if the row was deleted by a visible transaction
        if version.deleted_by != 0:
            deleter = version.deleted_by
            if deleter == own_txn_id:
                return False
            if (
                txn_status.get(deleter) == TxnStatus.COMMITTED
                and deleter not in self.active_txns
                and deleter < self.snapshot_xid
            ):
                return False  # deletion is visible, so row is gone

        return True


class MVCCStore:
    # MVCC key-value store with snapshot isolation, version chains,
    # write-write conflict detection, and garbage collection.
    #
    # Architecture:
    # - Each key maps to a linked list of RowVersion objects (newest first)
    # - Reads traverse the chain to find the first visible version
    # - Writes create new versions at the head of the chain
    # - GC removes versions that are invisible to ALL active snapshots

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_xid = 1
        self._versions: dict[str, RowVersion] = {}  # key -> newest version
        self._txn_status: dict[int, TxnStatus] = {}
        self._active_txns: set[int] = set()
        self._txn_write_sets: dict[int, set[str]] = {}

    def begin_transaction(self) -> Transaction:
        with self._lock:
            xid = self._next_xid
            self._next_xid += 1
            self._txn_status[xid] = TxnStatus.ACTIVE
            self._active_txns.add(xid)
            self._txn_write_sets[xid] = set()

            snapshot = Snapshot(
                snapshot_xid=xid,
                active_txns=frozenset(self._active_txns - {xid}),
            )
        return Transaction(store=self, xid=xid, snapshot=snapshot)

    def _read(self, key: str, txn: Transaction) -> Optional[Any]:
        # Walk the version chain to find the first visible version
        version = self._versions.get(key)
        while version is not None:
            if txn.snapshot.is_visible(version, self._txn_status, txn.xid):
                return version.value
            version = version.prev_version
        return None

    def _write(self, key: str, value: Any, txn: Transaction) -> None:
        with self._lock:
            # Write-write conflict detection: first writer wins
            current = self._versions.get(key)
            if current is not None and current.created_by != txn.xid:
                creator_status = self._txn_status.get(current.created_by)
                if creator_status == TxnStatus.ACTIVE:
                    raise ConflictError(
                        f"Write-write conflict on key '{key}': "
                        f"txn {current.created_by} is also writing"
                    )

            # Create new version at the head of the chain
            new_version = RowVersion(
                key=key,
                value=value,
                created_by=txn.xid,
                prev_version=current,
            )
            # Mark old version as deleted by this transaction
            if current is not None and current.created_by != txn.xid:
                current.deleted_by = txn.xid

            self._versions[key] = new_version
            self._txn_write_sets[txn.xid].add(key)

    def _commit(self, xid: int) -> None:
        with self._lock:
            self._txn_status[xid] = TxnStatus.COMMITTED
            self._active_txns.discard(xid)

    def _abort(self, xid: int) -> None:
        with self._lock:
            self._txn_status[xid] = TxnStatus.ABORTED
            self._active_txns.discard(xid)
            # Roll back: remove versions created by this transaction
            for key in self._txn_write_sets.get(xid, set()):
                version = self._versions.get(key)
                if version is not None and version.created_by == xid:
                    # Restore previous version
                    if version.prev_version is not None:
                        version.prev_version.deleted_by = 0
                        self._versions[key] = version.prev_version
                    else:
                        del self._versions[key]

    def garbage_collect(self) -> int:
        # Remove versions invisible to all active transactions.
        # This is the MVCC equivalent of PostgreSQL's VACUUM.
        #
        # The key insight: a version can be removed if no active
        # or future transaction could ever need to see it.
        with self._lock:
            if self._active_txns:
                oldest_active = min(self._active_txns)
            else:
                oldest_active = self._next_xid
            removed = 0

            for key in list(self._versions.keys()):
                version = self._versions[key]
                prev = version
                while prev.prev_version is not None:
                    old = prev.prev_version
                    # Safe to remove if the old version's deleter committed
                    # before the oldest active transaction
                    if (
                        old.deleted_by != 0
                        and self._txn_status.get(old.deleted_by) == TxnStatus.COMMITTED
                        and old.deleted_by < oldest_active
                    ):
                        prev.prev_version = old.prev_version
                        removed += 1
                    else:
                        prev = old

            return removed


class ConflictError(Exception):
    pass


class Transaction:
    # Transaction handle providing read/write/commit/abort operations

    def __init__(self, store: MVCCStore, xid: int, snapshot: Snapshot) -> None:
        self.store = store
        self.xid = xid
        self.snapshot = snapshot
        self._committed = False
        self._aborted = False

    def read(self, key: str) -> Optional[Any]:
        if self._committed or self._aborted:
            raise RuntimeError("Transaction already ended")
        return self.store._read(key, self)

    def write(self, key: str, value: Any) -> None:
        if self._committed or self._aborted:
            raise RuntimeError("Transaction already ended")
        self.store._write(key, value, self)

    def commit(self) -> None:
        if self._committed or self._aborted:
            raise RuntimeError("Transaction already ended")
        self.store._commit(self.xid)
        self._committed = True

    def abort(self) -> None:
        if self._committed or self._aborted:
            raise RuntimeError("Transaction already ended")
        self.store._abort(self.xid)
        self._aborted = True

    def __enter__(self) -> Transaction:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._committed and not self._aborted:
            if exc_type is not None:
                self.abort()
            else:
                self.commit()
```

## Garbage Collection: The Hidden Cost

### PostgreSQL's VACUUM Problem

PostgreSQL's heap-based MVCC means dead tuples accumulate in the main table. Without regular VACUUM, tables grow unboundedly -- this is called **table bloat**. The autovacuum daemon runs automatically, but it can fall behind under heavy write loads, causing:

1. **Increased disk usage**: Dead tuples waste space
2. **Slower sequential scans**: Must read and skip dead tuples
3. **Transaction ID wraparound**: PostgreSQL uses 32-bit transaction IDs; without VACUUM freezing old tuples, the database will shut down to prevent data corruption after ~2 billion transactions

**Best practice**: Monitor `pg_stat_user_tables.n_dead_tup` and ensure autovacuum is keeping up. For high-write tables, tune `autovacuum_vacuum_scale_factor` down from the default 0.2 (20% dead tuples triggers VACUUM) to 0.01-0.05.

### InnoDB's Purge Thread

InnoDB's undo-based MVCC avoids table bloat but has its own pitfall: **long-running transactions prevent purge**. If a transaction keeps its read view open for hours, all undo records created since that transaction started cannot be purged, causing the undo tablespace to grow. This is why **long-running queries on InnoDB can indirectly cause disk space issues** -- the undo log grows while waiting for the old read view to close.

```python
# MVCC health monitor: track version chain depth and GC pressure
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MVCCHealthMetrics:
    # Monitors MVCC health indicators to detect GC/vacuum problems
    # before they cause performance degradation.
    total_versions: int = 0
    live_versions: int = 0
    dead_versions: int = 0
    max_chain_depth: int = 0
    oldest_active_txn_age_seconds: float = 0.0

    @property
    def bloat_ratio(self) -> float:
        # Ratio of dead to live versions; >0.2 indicates vacuum lag
        if self.live_versions == 0:
            return 0.0
        return self.dead_versions / self.live_versions

    @property
    def needs_vacuum(self) -> bool:
        # Heuristic: vacuum when dead versions exceed 20% of live
        return self.bloat_ratio > 0.2

    @property
    def has_long_running_txn(self) -> bool:
        # Transactions older than 5 minutes block GC
        return self.oldest_active_txn_age_seconds > 300.0

    def diagnose(self) -> list[str]:
        issues: list[str] = []
        if self.needs_vacuum:
            issues.append(
                f"High dead tuple ratio ({self.bloat_ratio:.1%}). "
                f"VACUUM is falling behind -- consider tuning "
                f"autovacuum_vacuum_scale_factor."
            )
        if self.has_long_running_txn:
            issues.append(
                f"Long-running transaction detected "
                f"({self.oldest_active_txn_age_seconds:.0f}s). "
                f"This prevents GC of old versions and may cause "
                f"table bloat (PostgreSQL) or undo log growth (InnoDB)."
            )
        if self.max_chain_depth > 10:
            issues.append(
                f"Deep version chain ({self.max_chain_depth} versions). "
                f"Reads must traverse {self.max_chain_depth} versions "
                f"to find the visible one, degrading read latency."
            )
        return issues if issues else ["MVCC health is good"]
```

## Write Skew and Serializable Isolation

```python
# Demonstrating the write skew anomaly under snapshot isolation
def demonstrate_write_skew(store: MVCCStore) -> None:
    # Setup: two doctors on call
    setup = store.begin_transaction()
    setup.write("doctor_alice_oncall", True)
    setup.write("doctor_bob_oncall", True)
    setup.commit()

    # Both doctors check the invariant and decide to go off call
    txn_alice = store.begin_transaction()
    txn_bob = store.begin_transaction()

    # Alice reads: both on call, safe to leave
    alice_on = txn_alice.read("doctor_alice_oncall")
    bob_on_alice_view = txn_alice.read("doctor_bob_oncall")
    # bob_on_alice_view is True, so Alice thinks it's safe

    # Bob reads: both on call, safe to leave
    bob_on = txn_bob.read("doctor_bob_oncall")
    alice_on_bob_view = txn_bob.read("doctor_alice_oncall")
    # alice_on_bob_view is True, so Bob thinks it's safe

    # Both go off call -- violating the invariant!
    txn_alice.write("doctor_alice_oncall", False)
    txn_bob.write("doctor_bob_oncall", False)

    # Both commit successfully under snapshot isolation
    txn_alice.commit()
    txn_bob.commit()
    # Result: NO doctor is on call -- write skew anomaly
    # To prevent this, use SERIALIZABLE isolation level,
    # which adds predicate locking or serializable snapshot isolation (SSI)
```

## Summary and Key Takeaways

- **MVCC eliminates reader-writer blocking** by maintaining multiple row versions; readers see a consistent snapshot without acquiring locks, enabling dramatically higher concurrency than lock-based schemes
- **Snapshot visibility** depends on transaction IDs and commit status: a version is visible if its creator committed before the snapshot was taken and is not in the snapshot's active transaction set; this simple rule enables lock-free consistent reads
- **PostgreSQL stores all versions in the heap** (requiring VACUUM to reclaim dead tuples), while **InnoDB stores old versions in undo logs** (requiring purge threads); the PostgreSQL approach risks table bloat, while the InnoDB approach risks undo log growth from long-running transactions
- **Write-write conflicts** are detected using the "first writer wins" rule: if two transactions modify the same row, the second must wait or abort; however, **write skew** (disjoint writes based on overlapping reads) is allowed under snapshot isolation and requires SERIALIZABLE isolation to prevent
- **Best practice**: monitor dead tuple counts in PostgreSQL (`n_dead_tup`) and undo history length in MySQL (`SHOW ENGINE INNODB STATUS`); tune autovacuum aggressively for high-write tables and avoid long-running transactions that pin old snapshots
"""
    ),

    # --- 5. Connection Pooling and Query Execution ---
    (
        "databases/connection-pooling-query-execution",
        "Explain database connection pooling and query execution internals, including the connection lifecycle, prepared statement benefits and pitfalls, PgBouncer transaction vs session pooling modes, connection pool sizing formulas, the anatomy of query execution from client to server and back, and a complete Python connection pool implementation with health checks, prepared statement caching, and adaptive sizing.",
        r"""# Connection Pooling and Query Execution: From Client to Server and Back

## Why Connection Pooling Is Critical

Creating a database connection is **shockingly expensive**. A PostgreSQL connection fork costs 1-5ms of CPU time (the server forks a new process), allocates 5-10MB of memory per connection, and requires a TLS handshake (another 1-5ms for encrypted connections). If your web application creates a new connection per request at 1000 RPS, you'd need 1000 concurrent connections consuming 10GB of RAM -- and PostgreSQL starts thrashing with its process-per-connection model at around 200-500 connections.

Connection pooling solves this by maintaining a **pool of pre-established connections** that are reused across requests. Instead of connect-query-disconnect per request, the pattern becomes borrow-query-return, eliminating the connection overhead entirely. However, pooling introduces its own complexities: **pool sizing**, **connection health checking**, **statement caching invalidation**, and the critical choice between **session pooling** and **transaction pooling**.

## The Connection Lifecycle

### What Happens When You Connect

A database connection goes through several stages:

1. **TCP handshake**: 3-way handshake (~0.5ms on localhost, 1-50ms over network)
2. **TLS negotiation**: Certificate exchange and cipher negotiation (~2-10ms)
3. **Authentication**: Password verification, LDAP lookup, or certificate check (~1-5ms)
4. **Backend startup**: PostgreSQL forks a new backend process, initializes memory (~1-5ms); MySQL creates a new thread (~0.2ms)
5. **Session configuration**: SET statements for timezone, search_path, encoding (~0.1ms)

Total: **5-70ms** per connection establishment. At scale, this is the difference between a responsive application and one that collapses under load.

### Prepared Statements: Benefits and Pitfalls

Prepared statements provide two key advantages:

1. **Parsing overhead elimination**: The SQL is parsed and planned once, then executed many times with different parameters. For a query executed 10,000 times, this saves 9,999 parse cycles.

2. **SQL injection prevention**: Parameters are bound separately from the SQL text, making injection impossible -- not just difficult, but structurally impossible.

**Pitfall**: Prepared statements interact badly with transaction-mode connection pooling. Because prepared statements are bound to a specific backend process, they become invalid when the connection is returned to the pool and handed to a different client. PgBouncer in transaction mode must either disable prepared statements or use protocol-level statement rewriting (added in PgBouncer 1.21).

A **common mistake** is using prepared statements for queries with highly variable parameters. The optimizer creates a **generic plan** after 5 executions (PostgreSQL), which may be worse than a custom plan for specific parameter values. For example, `SELECT * FROM orders WHERE status = $1` might use an index scan for `status = 'pending'` (rare) but a sequential scan for `status = 'completed'` (common). The generic plan cannot adapt.

## PgBouncer Pooling Modes

### Session Pooling

The client gets a dedicated backend connection for the entire session. **Best for**: applications that use session-level state (temporary tables, advisory locks, prepared statements, `SET` commands).

**Trade-off**: Limited concurrency savings -- if your application holds connections while waiting for user input or doing non-DB work, those connections are wasted.

### Transaction Pooling

The client gets a backend connection only during a transaction. Between transactions, the connection returns to the pool. **Best for**: web applications where each request is a single transaction.

**Trade-off**: Session-level features (prepared statements, temp tables, `SET` commands, `LISTEN/NOTIFY`) break because consecutive transactions may use different backend connections. This is the most impactful limitation in practice.

### Statement Pooling

The most aggressive mode: connections are returned after each statement. **Rarely used** because it breaks multi-statement transactions entirely.

## Pool Sizing: The Science

The optimal pool size is **not** "as many as possible." In fact, **a pool that's too large performs worse than a pool that's too small** because of CPU context switching, lock contention, and cache thrashing.

The formula from the PostgreSQL wiki:
```
optimal_pool_size = (core_count * 2) + effective_spindle_count
```

For SSDs (no spindles), this simplifies to approximately `core_count * 2`. A 4-core server should have a pool of ~8-10 connections, not 100. If you need to handle 1000 concurrent requests with 10 connections, the requests simply **queue** at the pool -- and this queuing actually improves throughput by reducing contention.

However, this formula assumes all queries are CPU- or I/O-bound. If queries spend significant time waiting on external services (HTTP calls, distributed locks), the pool can be larger because connections spend time idle waiting.

## Python Connection Pool Implementation

```python
# Production connection pool with health checks, adaptive sizing, and metrics
from __future__ import annotations

import dataclasses
import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional, Protocol

logger = logging.getLogger(__name__)


class DBConnection(Protocol):
    # Protocol for database connection objects
    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any: ...
    def close(self) -> None: ...
    def ping(self) -> bool: ...
    @property
    def is_closed(self) -> bool: ...


@dataclasses.dataclass
class PoolConfig:
    # Connection pool configuration
    min_size: int = 2
    max_size: int = 10
    max_idle_time_seconds: float = 300.0   # close idle connections after 5 min
    max_lifetime_seconds: float = 3600.0   # close connections after 1 hour
    health_check_interval: float = 30.0    # validate idle connections every 30s
    acquire_timeout: float = 5.0           # wait up to 5s for a connection
    validation_query: str = "SELECT 1"
    adaptive_sizing: bool = True           # auto-adjust pool size based on demand


@dataclasses.dataclass
class PooledConnection:
    # Wrapper tracking connection metadata for pool management
    connection: Any  # actual DB connection
    created_at: float = dataclasses.field(default_factory=time.time)
    last_used_at: float = dataclasses.field(default_factory=time.time)
    last_validated_at: float = dataclasses.field(default_factory=time.time)
    times_used: int = 0
    in_use: bool = False

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at


class ConnectionPool:
    # Thread-safe connection pool with health checking, eviction, and
    # adaptive sizing based on demand patterns.
    #
    # Design decisions:
    # - LIFO (stack) ordering: most recently used connections are reused first,
    #   allowing least recently used connections to idle out and be closed.
    #   This naturally converges to the optimal pool size.
    # - Background health checker: validates idle connections periodically
    #   to detect broken connections before they cause query failures.
    # - Max lifetime: prevents stale connections from accumulating state
    #   (memory leaks, cached plans for dropped tables, etc.)

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        config: Optional[PoolConfig] = None,
    ) -> None:
        self.factory = connection_factory
        self.config = config or PoolConfig()
        self._pool: queue.LifoQueue[PooledConnection] = queue.LifoQueue(
            maxsize=self.config.max_size
        )
        self._all_connections: list[PooledConnection] = []
        self._lock = threading.Lock()
        self._total_created = 0
        self._total_acquired = 0
        self._total_timeouts = 0

        # Pre-fill minimum connections
        for _ in range(self.config.min_size):
            conn = self._create_connection()
            self._pool.put(conn)

        # Start health checker thread
        self._running = True
        self._health_thread = threading.Thread(
            target=self._health_check_loop, daemon=True
        )
        self._health_thread.start()

    def _create_connection(self) -> PooledConnection:
        raw_conn = self.factory()
        pooled = PooledConnection(connection=raw_conn)
        with self._lock:
            self._all_connections.append(pooled)
            self._total_created += 1
        return pooled

    def _validate_connection(self, conn: PooledConnection) -> bool:
        # Check if a connection is still alive and usable
        try:
            if hasattr(conn.connection, "ping"):
                return conn.connection.ping()
            conn.connection.execute(self.config.validation_query)
            conn.last_validated_at = time.time()
            return True
        except Exception:
            return False

    def _should_evict(self, conn: PooledConnection) -> bool:
        # Determine if a connection should be removed from the pool
        if conn.age_seconds > self.config.max_lifetime_seconds:
            return True  # exceeded max lifetime
        if conn.idle_seconds > self.config.max_idle_time_seconds:
            # Only evict if we're above min_size
            with self._lock:
                active_count = sum(
                    1 for c in self._all_connections
                    if not getattr(c.connection, "is_closed", False)
                )
            return active_count > self.config.min_size
        return False

    def acquire(self) -> PooledConnection:
        # Get a connection from the pool, creating new ones if needed.
        # Raises TimeoutError if no connection is available within the timeout.
        start = time.time()
        self._total_acquired += 1

        while True:
            elapsed = time.time() - start
            remaining = self.config.acquire_timeout - elapsed
            if remaining <= 0:
                self._total_timeouts += 1
                raise TimeoutError(
                    f"Could not acquire connection within "
                    f"{self.config.acquire_timeout}s "
                    f"(pool size: {self.size}, in use: {self.in_use_count})"
                )

            try:
                conn = self._pool.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                # Pool empty -- try to create a new connection
                with self._lock:
                    if len(self._all_connections) < self.config.max_size:
                        conn = self._create_connection()
                        conn.in_use = True
                        conn.last_used_at = time.time()
                        conn.times_used += 1
                        return conn
                continue

            # Validate the connection before returning it
            if self._should_evict(conn):
                self._destroy_connection(conn)
                continue

            if not self._validate_connection(conn):
                self._destroy_connection(conn)
                continue

            conn.in_use = True
            conn.last_used_at = time.time()
            conn.times_used += 1
            return conn

    def release(self, conn: PooledConnection) -> None:
        # Return a connection to the pool
        conn.in_use = False
        conn.last_used_at = time.time()

        if self._should_evict(conn):
            self._destroy_connection(conn)
            return

        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            # Pool is full -- destroy excess connection
            self._destroy_connection(conn)

    def _destroy_connection(self, conn: PooledConnection) -> None:
        try:
            conn.connection.close()
        except Exception:
            pass
        with self._lock:
            if conn in self._all_connections:
                self._all_connections.remove(conn)

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        # Context manager for safe connection acquisition and release
        conn = self.acquire()
        try:
            yield conn.connection
        except Exception:
            # Connection might be in a bad state after an error
            # Reset it before returning to pool
            try:
                conn.connection.execute("ROLLBACK")
            except Exception:
                self._destroy_connection(conn)
                raise
            raise
        finally:
            if conn.in_use:
                self.release(conn)

    def _health_check_loop(self) -> None:
        # Background thread that validates idle connections
        while self._running:
            time.sleep(self.config.health_check_interval)
            self._run_health_checks()

    def _run_health_checks(self) -> None:
        # Validate all idle connections and evict dead ones
        checked = 0
        evicted = 0
        temp_connections: list[PooledConnection] = []

        # Drain the pool for checking
        while True:
            try:
                conn = self._pool.get_nowait()
                temp_connections.append(conn)
            except queue.Empty:
                break

        for conn in temp_connections:
            checked += 1
            if self._should_evict(conn) or not self._validate_connection(conn):
                self._destroy_connection(conn)
                evicted += 1
            else:
                try:
                    self._pool.put_nowait(conn)
                except queue.Full:
                    self._destroy_connection(conn)
                    evicted += 1

        if evicted > 0:
            logger.info(
                "Health check: validated=%d evicted=%d pool_size=%d",
                checked, evicted, self.size,
            )

        # Ensure minimum connections
        while self.size < self.config.min_size:
            try:
                conn = self._create_connection()
                self._pool.put_nowait(conn)
            except Exception:
                break

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._all_connections)

    @property
    def in_use_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._all_connections if c.in_use)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_size": self.size,
            "in_use": self.in_use_count,
            "idle": self.size - self.in_use_count,
            "total_created": self._total_created,
            "total_acquired": self._total_acquired,
            "total_timeouts": self._total_timeouts,
        }

    def close(self) -> None:
        # Shut down the pool and close all connections
        self._running = False
        with self._lock:
            for conn in self._all_connections:
                try:
                    conn.connection.close()
                except Exception:
                    pass
            self._all_connections.clear()
```

### Prepared Statement Cache

```python
# Prepared statement cache with connection affinity tracking
from __future__ import annotations

import hashlib
from typing import Any


class PreparedStatementCache:
    # Caches prepared statements per connection to avoid repeated parsing.
    #
    # The trade-off: prepared statements save parse time but consume
    # server memory. PostgreSQL allocates ~2KB per prepared statement
    # per connection. With 1000 distinct queries and 50 connections,
    # that's 100MB of server memory just for cached plans.
    #
    # Best practice: only prepare frequently-executed queries.
    # One-off ad-hoc queries should use simple query protocol.

    def __init__(self, max_statements: int = 256) -> None:
        self.max_statements = max_statements
        # connection_id -> {query_hash -> statement_name}
        self._cache: dict[int, dict[str, str]] = {}
        self._counter = 0

    def _query_hash(self, sql: str) -> str:
        return hashlib.sha256(sql.encode()).hexdigest()[:16]

    def get_or_prepare(
        self,
        connection: Any,
        connection_id: int,
        sql: str,
    ) -> str:
        # Returns the prepared statement name, preparing it if needed
        qhash = self._query_hash(sql)

        if connection_id not in self._cache:
            self._cache[connection_id] = {}

        conn_cache = self._cache[connection_id]

        if qhash in conn_cache:
            return conn_cache[qhash]

        # Evict oldest if cache is full (LRU would be better, simplified here)
        if len(conn_cache) >= self.max_statements:
            oldest_key = next(iter(conn_cache))
            oldest_name = conn_cache.pop(oldest_key)
            try:
                connection.execute(f"DEALLOCATE {oldest_name}")
            except Exception:
                pass

        # Prepare the statement
        self._counter += 1
        stmt_name = f"_ps_{self._counter}"
        connection.execute(f"PREPARE {stmt_name} AS {sql}")
        conn_cache[qhash] = stmt_name
        return stmt_name

    def invalidate_connection(self, connection_id: int) -> None:
        # Called when a connection is returned to the pool in
        # transaction pooling mode. All prepared statements are
        # invalid because the next client may get a different backend.
        self._cache.pop(connection_id, None)
```

## Query Execution: End-to-End Anatomy

When your application calls `cursor.execute("SELECT ...")`, here is what happens:

1. **Client library** serializes the query into the PostgreSQL wire protocol (or MySQL protocol)
2. **Network**: TCP packet sent to the server (or PgBouncer proxy)
3. **PgBouncer** (if present): routes the query to an appropriate backend connection
4. **PostgreSQL backend**: parses SQL, optimizes, executes
5. **Storage engine**: reads pages from buffer cache (shared_buffers) or disk
6. **Result streaming**: rows are sent back as they're produced (cursor-based) or buffered (default)
7. **Client library**: deserializes wire format to Python objects

```python
# Query execution timer with server-side cursor support
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator


class QueryExecutor:
    # Wraps a connection pool with query timing, server-side cursors,
    # and automatic retry for transient failures.
    #
    # Best practice: use server-side cursors for result sets larger
    # than ~10,000 rows to avoid loading everything into Python memory.

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool
        self._query_times: list[float] = []

    @contextmanager
    def timed_query(self) -> Generator[dict[str, float], None, None]:
        # Context manager that tracks query execution time
        metrics: dict[str, float] = {}
        start = time.perf_counter()
        yield metrics
        elapsed = time.perf_counter() - start
        metrics["elapsed_ms"] = elapsed * 1000
        self._query_times.append(elapsed)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        # Execute a query and return all rows
        with self.pool.connection() as conn:
            with self.timed_query() as metrics:
                result = conn.execute(sql, params)
            return result

    def execute_streaming(
        self, sql: str, params: tuple[Any, ...] = (), batch_size: int = 2000
    ) -> Iterator[list[Any]]:
        # Stream large result sets using server-side cursors.
        # Instead of loading all rows into memory, yields batches
        # of batch_size rows. This prevents OOM for million-row queries.
        with self.pool.connection() as conn:
            cursor = conn.execute(sql, params)
            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break
                yield batch

    @property
    def avg_query_time_ms(self) -> float:
        if not self._query_times:
            return 0.0
        return (sum(self._query_times) / len(self._query_times)) * 1000

    @property
    def p99_query_time_ms(self) -> float:
        if not self._query_times:
            return 0.0
        sorted_times = sorted(self._query_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)] * 1000
```

**Best practice**: Use server-side cursors (`cursor.itersize = 2000` in psycopg2) for large result sets to avoid loading millions of rows into Python memory. The default behavior fetches all rows before returning, which can cause OOM errors for large queries.

## Summary and Key Takeaways

- **Connection creation costs 5-70ms** (TCP + TLS + auth + backend startup), so pooling is essential for any application handling more than a few requests per second; the pool amortizes this cost to near-zero by reusing pre-established connections
- **Optimal pool size is small** -- the formula `(cores * 2) + spindles` means a 4-core server needs only ~8 connections; larger pools cause context switching, lock contention, and cache thrashing that reduce rather than increase throughput
- **PgBouncer transaction pooling** returns connections between transactions for maximum reuse, but breaks session-level features (prepared statements, temp tables, SET commands); session pooling preserves these features at the cost of lower concurrency
- **Prepared statements** eliminate parse overhead and prevent SQL injection, but consume server memory (~2KB each per connection) and interact poorly with transaction pooling; only prepare frequently-executed queries
- **Best practice**: implement LIFO connection reuse (most recently used first) so that least recently used connections naturally idle out, converging the pool to its optimal size; combine with background health checks and max lifetime eviction to prevent stale connection issues
"""
    ),
]
