"""Thinking-trace pairs: error recovery patterns."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How do I implement checkpoint and restart for long-running data processing jobs? I have a pipeline that processes millions of records and I cannot afford to start over from scratch when it fails halfway through.''',
        r'''<think>
Checkpoint/restart for a pipeline processing millions of records. My first thought is to save progress to a JSON file every N records. But wait -- what if the process crashes WHILE writing the checkpoint file? You end up with a corrupted half-written checkpoint and lose your progress anyway. So checkpoint writes themselves must be atomic.

I considered using a database for checkpoint storage since databases handle atomicity natively. But actually, for a batch job that might run on a bare worker with no database, a file-based approach is more portable. The trick is write-then-rename: write the new checkpoint to a temp file, fsync it, then atomically rename it over the old checkpoint. On most filesystems, rename is atomic, so you either get the old checkpoint or the new one -- never a corrupted one.

How often to checkpoint? Every record is safe but slow (fsync per record kills throughput). Every 10,000 records is fast but you lose up to 10,000 records of work on crash. Hmm, the right answer is a hybrid: checkpoint every N records OR every M seconds, whichever comes first. That bounds both the I/O overhead and the maximum re-work on crash.

There is another subtlety I almost missed: idempotent processing. When resuming from a checkpoint, the last batch before the crash might have partially completed. If processing has side effects (sending emails, charging credit cards), re-processing those records could cause duplicates. Therefore, either each record needs a unique processing ID for deduplication, or the checkpoint must track which records within the last batch were fully committed.
</think>

Checkpoint/restart requires atomic state persistence and idempotent processing. Here is a production-ready pattern:

```python
import json
import os
import time
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator, Any, Optional, Callable


@dataclass
class Checkpoint:
    """Represents the saved state of a processing job."""
    job_id: str
    last_processed_offset: int = 0
    records_processed: int = 0
    records_failed: int = 0
    started_at: float = 0.0
    last_checkpoint_at: float = 0.0
    custom_state: dict = field(default_factory=dict)
    completed: bool = False


class CheckpointManager:
    """Manages checkpoint persistence with atomic writes."""

    def __init__(self, checkpoint_dir: str, job_id: str):
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._job_id = job_id
        self._checkpoint_path = self._dir / f"{job_id}.checkpoint.json"
        self._temp_path = self._dir / f"{job_id}.checkpoint.tmp"

    def save(self, checkpoint: Checkpoint):
        """Atomically save checkpoint using write-rename pattern."""
        checkpoint.last_checkpoint_at = time.time()
        data = json.dumps(asdict(checkpoint), indent=2)

        # Write to temp file first
        with open(self._temp_path, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk

        # Atomic rename (on POSIX) or replace (on Windows)
        shutil.move(str(self._temp_path), str(self._checkpoint_path))

    def load(self) -> Optional[Checkpoint]:
        """Load the last checkpoint, if one exists."""
        if not self._checkpoint_path.exists():
            return None

        try:
            with open(self._checkpoint_path) as f:
                data = json.load(f)
            return Checkpoint(**data)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            print(f"WARNING: Corrupt checkpoint file, starting fresh: {exc}")
            return None

    def clear(self):
        """Remove checkpoint after successful completion."""
        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()
        if self._temp_path.exists():
            self._temp_path.unlink()


class CheckpointedPipeline:
    """Process records with automatic checkpointing and resume."""

    def __init__(self, job_id: str, checkpoint_dir: str = "./checkpoints",
                 checkpoint_every_n: int = 1000,
                 checkpoint_every_secs: float = 30.0):
        self._mgr = CheckpointManager(checkpoint_dir, job_id)
        self._job_id = job_id
        self._checkpoint_n = checkpoint_every_n
        self._checkpoint_secs = checkpoint_every_secs
        self._last_checkpoint_time = time.time()
        self._checkpoint = Checkpoint(job_id=job_id)
        self._error_handler: Optional[Callable] = None

    def on_error(self, handler: Callable):
        """Set a callback for per-record errors."""
        self._error_handler = handler
        return self

    def run(self, records: Iterator[Any],
            processor: Callable[[Any, int], Any],
            total_records: int = None):
        """Process records with checkpointing.

        Args:
            records: Iterator of records to process
            processor: Function(record, offset) -> result
            total_records: Optional total count for progress reporting
        """
        # Try to resume from checkpoint
        saved = self._mgr.load()
        if saved and not saved.completed:
            self._checkpoint = saved
            skip_count = saved.last_processed_offset
            print(f"Resuming from checkpoint: offset={skip_count}, "
                  f"processed={saved.records_processed}")
        else:
            skip_count = 0
            self._checkpoint.started_at = time.time()

        since_last_checkpoint = 0

        for offset, record in enumerate(records):
            # Skip already-processed records
            if offset < skip_count:
                continue

            try:
                processor(record, offset)
                self._checkpoint.records_processed += 1
            except Exception as exc:
                self._checkpoint.records_failed += 1
                if self._error_handler:
                    self._error_handler(record, offset, exc)
                else:
                    print(f"ERROR at offset {offset}: {exc}")

            self._checkpoint.last_processed_offset = offset + 1
            since_last_checkpoint += 1

            # Checkpoint based on count or time
            should_checkpoint = (
                since_last_checkpoint >= self._checkpoint_n or
                time.time() - self._last_checkpoint_time >= self._checkpoint_secs
            )

            if should_checkpoint:
                self._mgr.save(self._checkpoint)
                self._last_checkpoint_time = time.time()
                since_last_checkpoint = 0

                if total_records:
                    pct = (self._checkpoint.records_processed / total_records) * 100
                    print(f"Progress: {pct:.1f}% "
                          f"({self._checkpoint.records_processed}/{total_records})")

        # Final checkpoint -- mark complete
        self._checkpoint.completed = True
        self._mgr.save(self._checkpoint)
        elapsed = time.time() - self._checkpoint.started_at

        print(f"Job {self._job_id} complete: "
              f"{self._checkpoint.records_processed} processed, "
              f"{self._checkpoint.records_failed} failed, "
              f"{elapsed:.1f}s elapsed")

        return self._checkpoint


# ============================================================
# USAGE EXAMPLE
# ============================================================

def process_record(record: dict, offset: int):
    """Simulate processing -- must be idempotent for restart safety."""
    # Your actual processing logic here
    if record.get("amount", 0) < 0:
        raise ValueError(f"Negative amount: {record['amount']}")
    # Process the record...


def handle_error(record, offset, exc):
    """Log failed records for later retry or manual review."""
    with open("failed_records.jsonl", "a") as f:
        f.write(json.dumps({
            "offset": offset,
            "record": record,
            "error": str(exc),
        }) + "\n")


# Create and run the pipeline
pipeline = CheckpointedPipeline(
    job_id="daily-import-2025-01-15",
    checkpoint_every_n=5000,
    checkpoint_every_secs=60.0,
)
pipeline.on_error(handle_error)

records = [{"id": i, "amount": i * 10} for i in range(100_000)]
pipeline.run(iter(records), process_record, total_records=len(records))

# If the process crashes at record 50,000 and restarts:
# "Resuming from checkpoint: offset=50000, processed=49995"
# It skips the first 50,000 records and continues from where it left off.
```

**Critical design points:**

1. **Atomic writes**: write to temp file, fsync, then rename -- a crash mid-write leaves the old checkpoint intact
2. **Idempotent processing**: the processor must be safe to call twice on the same record (in case of crash right after processing but before checkpoint)
3. **Two checkpoint triggers**: count-based (every N records) AND time-based (every N seconds) -- handles both fast and slow records
4. **Failed record logging**: errors on individual records do not stop the pipeline -- they are logged for later review
5. **Completion marker**: the `completed` flag prevents re-processing on restart after a successful run''',
    ),
    (
        "thinking/error-handling",
        r'''What is the write-ahead log (WAL) pattern and how do I implement it in my application for crash recovery? I want to make sure I never lose data even if the process crashes mid-operation.''',
        r'''<think>
Write-ahead logging for application-level crash recovery. The user probably knows WAL from database internals (PostgreSQL, SQLite), but how does this translate to application code?

My initial thought is: just append JSON records to a log file before doing the actual operation. But wait -- appending to a file without fsync gives no durability guarantee. The OS might buffer the write and lose it on crash. So I need fsync after each WAL entry. But fsync is expensive... could I batch multiple entries before fsyncing? Actually yes, but that changes the durability semantics: you might lose the last N entries instead of zero. For critical operations (financial transactions), every entry needs its own fsync. For less critical workloads, batched fsync with a configurable flush interval is a reasonable trade-off.

I considered using a binary format for the log (like Protocol Buffers) for performance. Hmm, but binary formats make manual debugging and recovery harder. If the WAL itself gets corrupted, you want to be able to read it with a text editor. JSON lines (one JSON object per line) is a good balance -- human readable, easy to parse, and each line is self-contained so corruption in one entry does not affect others.

Recovery replay logic has a subtle requirement: operations must be idempotent. If the process crashed after writing to the WAL but before (or during) applying the change, replay will re-apply it. If the operation is "set balance to 100" that is idempotent, but "add 50 to balance" is not. Therefore the WAL should record the intended final state, not the delta.

Log compaction is also critical -- without it, the WAL grows forever. After confirmed changes, old entries should be truncated. I need to track a "confirmed through" watermark and compact entries below it.
</think>

Write-ahead logging ensures durability by recording intent before action. Here is an application-level implementation:

```python
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


class EntryStatus(Enum):
    PENDING = "pending"       # Written to log, not yet applied
    APPLIED = "applied"       # Successfully applied to data store
    FAILED = "failed"         # Application failed (needs manual review)


@dataclass
class WALEntry:
    sequence: int
    operation: str            # e.g., "insert", "update", "delete"
    key: str                  # Primary identifier
    data: dict                # The change payload
    status: EntryStatus
    timestamp: float
    error: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "seq": self.sequence,
            "op": self.operation,
            "key": self.key,
            "data": self.data,
            "status": self.status.value,
            "ts": self.timestamp,
            "error": self.error,
        })

    @classmethod
    def from_json(cls, line: str) -> "WALEntry":
        d = json.loads(line)
        return cls(
            sequence=d["seq"],
            operation=d["op"],
            key=d["key"],
            data=d["data"],
            status=EntryStatus(d["status"]),
            timestamp=d["ts"],
            error=d.get("error", ""),
        )


class WriteAheadLog:
    """Application-level write-ahead log for crash recovery."""

    def __init__(self, log_dir: str, max_entries_before_compact: int = 10000):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._dir / "wal.log"
        self._compact_path = self._dir / "wal.compact.log"
        self._max_entries = max_entries_before_compact
        self._sequence = 0
        self._pending_count = 0
        self._file = None
        self._load_sequence()

    def _load_sequence(self):
        """Find the highest sequence number in the existing log."""
        if not self._log_path.exists():
            return
        with open(self._log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = WALEntry.from_json(line)
                    self._sequence = max(self._sequence, entry.sequence)
                    if entry.status == EntryStatus.PENDING:
                        self._pending_count += 1
                except (json.JSONDecodeError, KeyError):
                    continue

    def _get_file(self):
        if self._file is None:
            self._file = open(self._log_path, "a")
        return self._file

    def append(self, operation: str, key: str, data: dict) -> WALEntry:
        """Write an entry to the log BEFORE applying the operation.

        This is the critical step: the log entry must be durable
        (fsynced) before we attempt the actual operation.
        """
        self._sequence += 1
        entry = WALEntry(
            sequence=self._sequence,
            operation=operation,
            key=key,
            data=data,
            status=EntryStatus.PENDING,
            timestamp=time.time(),
        )

        f = self._get_file()
        f.write(entry.to_json() + "\n")
        f.flush()
        os.fsync(f.fileno())  # CRITICAL: ensure log is on disk

        self._pending_count += 1
        return entry

    def mark_applied(self, entry: WALEntry):
        """Mark an entry as successfully applied."""
        entry.status = EntryStatus.APPLIED
        f = self._get_file()
        f.write(entry.to_json() + "\n")
        f.flush()
        os.fsync(f.fileno())
        self._pending_count -= 1

        if self._sequence > self._max_entries:
            self.compact()

    def mark_failed(self, entry: WALEntry, error: str):
        """Mark an entry as failed."""
        entry.status = EntryStatus.FAILED
        entry.error = error
        f = self._get_file()
        f.write(entry.to_json() + "\n")
        f.flush()
        os.fsync(f.fileno())
        self._pending_count -= 1

    def get_pending_entries(self) -> list[WALEntry]:
        """Get all entries that were logged but never confirmed.

        These are the entries that need to be replayed on recovery.
        """
        if not self._log_path.exists():
            return []

        # Track latest status for each sequence number
        entries_by_seq: dict[int, WALEntry] = {}
        with open(self._log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = WALEntry.from_json(line)
                    entries_by_seq[entry.sequence] = entry
                except (json.JSONDecodeError, KeyError):
                    continue

        return [
            e for e in sorted(entries_by_seq.values(), key=lambda x: x.sequence)
            if e.status == EntryStatus.PENDING
        ]

    def compact(self):
        """Remove fully applied entries from the log.

        Keeps only PENDING and recent APPLIED entries.
        """
        if self._file:
            self._file.close()
            self._file = None

        entries_by_seq: dict[int, WALEntry] = {}
        if self._log_path.exists():
            with open(self._log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = WALEntry.from_json(line)
                        entries_by_seq[entry.sequence] = entry
                    except (json.JSONDecodeError, KeyError):
                        continue

        # Keep only pending and failed entries
        keep = [
            e for e in sorted(entries_by_seq.values(), key=lambda x: x.sequence)
            if e.status in (EntryStatus.PENDING, EntryStatus.FAILED)
        ]

        # Write compacted log atomically
        with open(self._compact_path, "w") as f:
            for entry in keep:
                f.write(entry.to_json() + "\n")
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        if self._log_path.exists():
            self._log_path.unlink()
        self._compact_path.rename(self._log_path)

        print(f"WAL compacted: {len(entries_by_seq)} -> {len(keep)} entries")

    def close(self):
        if self._file:
            self._file.close()
            self._file = None


# ============================================================
# WAL-PROTECTED DATA STORE
# ============================================================

class DurableStore:
    """Key-value store with WAL-based crash recovery."""

    def __init__(self, data_dir: str):
        self._wal = WriteAheadLog(data_dir)
        self._data: dict[str, Any] = {}
        self._data_path = Path(data_dir) / "data.json"
        self._load_data()
        self._recover()

    def _load_data(self):
        if self._data_path.exists():
            with open(self._data_path) as f:
                self._data = json.load(f)

    def _save_data(self):
        tmp = str(self._data_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(self._data_path))

    def _recover(self):
        """Replay pending WAL entries on startup."""
        pending = self._wal.get_pending_entries()
        if not pending:
            return

        print(f"Recovering {len(pending)} pending operations...")
        for entry in pending:
            try:
                self._apply(entry)
                self._wal.mark_applied(entry)
                print(f"  Recovered: {entry.operation} {entry.key}")
            except Exception as exc:
                self._wal.mark_failed(entry, str(exc))
                print(f"  Recovery failed: {entry.operation} {entry.key}: {exc}")

        self._save_data()

    def _apply(self, entry: WALEntry):
        """Apply a WAL entry to the in-memory data. Must be idempotent."""
        if entry.operation == "set":
            self._data[entry.key] = entry.data
        elif entry.operation == "delete":
            self._data.pop(entry.key, None)
        elif entry.operation == "update":
            if entry.key in self._data:
                self._data[entry.key].update(entry.data)
        else:
            raise ValueError(f"Unknown operation: {entry.operation}")

    def set(self, key: str, value: dict):
        # Step 1: Write intent to WAL (durable)
        entry = self._wal.append("set", key, value)

        # Step 2: Apply to data store
        try:
            self._apply(entry)
            self._save_data()
            self._wal.mark_applied(entry)
        except Exception as exc:
            self._wal.mark_failed(entry, str(exc))
            raise

    def get(self, key: str) -> Optional[dict]:
        return self._data.get(key)

    def delete(self, key: str):
        entry = self._wal.append("delete", key, {})
        try:
            self._apply(entry)
            self._save_data()
            self._wal.mark_applied(entry)
        except Exception as exc:
            self._wal.mark_failed(entry, str(exc))
            raise

    def close(self):
        self._wal.close()


# Usage:
store = DurableStore("./mydata")
store.set("user:42", {"name": "Alice", "balance": 100})
# If process crashes after WAL write but before data save,
# on restart _recover() replays the "set" operation.
```

**The WAL guarantee:**

1. **Before** modifying data, write the change to the log and fsync
2. If the process crashes **after WAL write but before data write**, recovery replays the log
3. If the process crashes **before WAL write**, the operation never happened (safe)
4. If the process crashes **after both writes**, the applied-marker catches up on next run
5. Operations must be **idempotent** because they might be replayed during recovery''',
    ),
    (
        "thinking/error-handling",
        r'''What is the "crash-only software" design philosophy? How do I design my application so that crashes are just normal restarts rather than catastrophic failures?''',
        r'''<think>
Crash-only software -- from the 2003 Candea and Fox paper. The radical idea: there should be NO clean shutdown path at all. The only way to stop the software is to crash it, and the only way to start is to recover from a crash. Therefore crash recovery IS the normal startup path.

My first reaction is "that sounds extreme -- surely clean shutdown is better?" But actually, the insight is that having two code paths (clean shutdown and crash recovery) means the crash recovery path is rarely tested. When a real crash happens, the untested recovery code often fails. By making crash recovery the ONLY path, it gets exercised on every restart and therefore is well-tested.

I considered whether this applies to all applications. Hmm, it works well for stateful services (databases, queues, workers) but what about stateless HTTP servers? Actually, even "stateless" servers have state -- open connections, in-flight requests, connection pool handles. A crash-only design forces you to handle those correctly.

Wait, there is a practical concern: some resources NEED graceful cleanup. File locks, for instance -- if you crash while holding a lock, the lock file persists and blocks the next startup. The crash-only answer is: do not use file locks. Use lock files with heartbeats (stale detection) or lease-based locks that auto-expire. Similarly, do not rely on in-memory state that cannot be rebuilt from persistent storage.

The practical implications cascade through the whole architecture:
- All operations must be idempotent (since recovery might re-execute partial operations)
- State is either durable (survives crashes) or reconstructable from durable state
- No long-lived in-memory caches without a warm-up-from-disk fallback
- Startup always runs the recovery routine, which is a no-op if there is nothing to recover
</think>

Crash-only software treats every startup as crash recovery. This eliminates an entire class of bugs where clean shutdown logic diverges from crash recovery. Here is how to design for it:

```python
import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Optional


# ============================================================
# PRINCIPLE 1: ALL STATE IS RECOVERABLE
# ============================================================

class RecoverableState:
    """State that survives crashes by persisting every mutation.

    Instead of holding state in memory and periodically saving,
    every write goes to disk immediately. Memory is just a cache.
    """

    def __init__(self, state_file: str):
        self._path = Path(state_file)
        self._cache: dict[str, Any] = {}
        self._recover()

    def _recover(self):
        """Called on every startup -- no distinction from crash recovery."""
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._cache = json.load(f)
                print(f"State recovered: {len(self._cache)} entries")
            except json.JSONDecodeError:
                print("State file corrupt, starting fresh")
                self._cache = {}
        else:
            print("No state file, starting fresh")
            self._cache = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def set(self, key: str, value: Any):
        self._cache[key] = value
        self._persist()

    def delete(self, key: str):
        self._cache.pop(key, None)
        self._persist()

    def _persist(self):
        tmp = str(self._path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._cache, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(self._path))


# ============================================================
# PRINCIPLE 2: IDEMPOTENT OPERATIONS
# ============================================================

class IdempotentTaskQueue:
    """Task processing where replaying a task is always safe.

    Each task has a unique ID. Before processing, we check if
    the result already exists. This makes crash-restart safe.
    """

    def __init__(self, results_dir: str):
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _result_path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.result.json"

    def is_completed(self, task_id: str) -> bool:
        return self._result_path(task_id).exists()

    def get_result(self, task_id: str) -> Optional[dict]:
        path = self._result_path(task_id)
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def save_result(self, task_id: str, result: dict):
        """Atomically save the result so it survives crashes."""
        path = self._result_path(task_id)
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(result, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))

    def process(self, task_id: str, task_data: dict,
                processor) -> dict:
        """Process a task idempotently."""
        # Check if already done (crash-restart safety)
        existing = self.get_result(task_id)
        if existing is not None:
            print(f"Task {task_id} already completed, skipping")
            return existing

        # Process and save atomically
        result = processor(task_data)
        self.save_result(task_id, result)
        return result


# ============================================================
# PRINCIPLE 3: LEASES INSTEAD OF LOCKS
# ============================================================

class LeaseManager:
    """Time-bounded leases instead of permanent locks.

    Regular locks are dangerous in crash-only software because
    a crash while holding a lock means the lock is never released.
    Leases auto-expire, so a crashed process does not block others.
    """

    def __init__(self, lease_dir: str):
        self._dir = Path(lease_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def acquire(self, resource: str, holder: str,
                ttl_seconds: int = 30) -> bool:
        """Try to acquire a lease. Returns True if successful."""
        lease_path = self._dir / f"{resource}.lease"

        # Check existing lease
        if lease_path.exists():
            try:
                with open(lease_path) as f:
                    lease = json.load(f)
                if lease["expires_at"] > time.time():
                    # Lease is still valid, someone else has it
                    return False
                # Lease expired, we can take it
            except (json.JSONDecodeError, KeyError):
                pass  # Corrupt lease file, safe to overwrite

        # Write our lease
        lease = {
            "holder": holder,
            "acquired_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
        }
        tmp = str(lease_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(lease, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(lease_path))
        return True

    def renew(self, resource: str, holder: str,
              ttl_seconds: int = 30) -> bool:
        """Renew a lease. Only works if we still hold it."""
        lease_path = self._dir / f"{resource}.lease"
        if not lease_path.exists():
            return False

        with open(lease_path) as f:
            lease = json.load(f)

        if lease["holder"] != holder:
            return False
        if lease["expires_at"] < time.time():
            return False  # Already expired

        lease["expires_at"] = time.time() + ttl_seconds
        tmp = str(lease_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(lease, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(lease_path))
        return True

    def release(self, resource: str, holder: str):
        """Release a lease. Optional -- it would expire anyway."""
        lease_path = self._dir / f"{resource}.lease"
        if lease_path.exists():
            try:
                with open(lease_path) as f:
                    lease = json.load(f)
                if lease["holder"] == holder:
                    lease_path.unlink()
            except (json.JSONDecodeError, KeyError):
                lease_path.unlink()


# ============================================================
# PRINCIPLE 4: CRASH-ONLY SERVICE SKELETON
# ============================================================

class CrashOnlyService:
    """A service designed to be crash-safe.

    Key properties:
    - Startup IS recovery (no separate init vs recover paths)
    - Shutdown IS crash (no graceful shutdown that differs from crash)
    - All state survives crashes
    - All operations are idempotent
    """

    def __init__(self, data_dir: str, instance_id: str):
        self.state = RecoverableState(f"{data_dir}/state.json")
        self.tasks = IdempotentTaskQueue(f"{data_dir}/results")
        self.leases = LeaseManager(f"{data_dir}/leases")
        self._instance_id = instance_id
        self._running = True

        # Recover incomplete work from last run
        self._recover_incomplete_work()

    def _recover_incomplete_work(self):
        """Find and resume any work left incomplete by a previous crash."""
        pending = self.state.get("pending_tasks", [])
        if pending:
            print(f"Found {len(pending)} incomplete tasks from previous run")
            for task_id in pending:
                task_data = self.state.get(f"task_data:{task_id}")
                if task_data and not self.tasks.is_completed(task_id):
                    print(f"  Resuming task {task_id}")
                    self._process_task(task_id, task_data)

    def submit_task(self, task_id: str, task_data: dict):
        """Submit a task for processing.

        State is saved BEFORE processing so a crash
        during processing leads to automatic retry on restart.
        """
        # Record intent (survives crash)
        pending = self.state.get("pending_tasks", [])
        if task_id not in pending:
            pending.append(task_id)
            self.state.set("pending_tasks", pending)
        self.state.set(f"task_data:{task_id}", task_data)

        # Process (idempotent, safe to replay)
        self._process_task(task_id, task_data)

        # Clean up pending list
        pending = [t for t in pending if t != task_id]
        self.state.set("pending_tasks", pending)
        self.state.delete(f"task_data:{task_id}")

    def _process_task(self, task_id: str, task_data: dict):
        """Process a single task with lease-based locking."""
        if not self.leases.acquire(f"task:{task_id}", self._instance_id):
            print(f"  Task {task_id} locked by another instance, skipping")
            return

        try:
            self.tasks.process(task_id, task_data, self._do_work)
        finally:
            self.leases.release(f"task:{task_id}", self._instance_id)

    def _do_work(self, task_data: dict) -> dict:
        """The actual work. Must be idempotent."""
        return {"status": "done", "processed_at": time.time()}
```

**Crash-only design principles:**

1. **No separate shutdown path**: startup always runs recovery, so there is no code path that only runs during "clean" shutdown
2. **Leases, not locks**: locks held by crashed processes are never released; leases expire automatically
3. **Idempotent everything**: if a task might be processed twice (crash during processing), the result must be the same
4. **Persistent intent**: record what you are about to do BEFORE doing it, so a crash triggers automatic retry
5. **No in-memory-only state**: anything important lives on disk or can be reconstructed from disk''',
    ),
    (
        "thinking/error-handling",
        r'''How do I build self-healing capabilities into my services? I want the application to detect problems and fix itself without human intervention when possible.''',
        r'''<think>
Self-healing systems -- the user wants automated detection AND remediation. My first thought is health checks, but basic health checks only report up/down. A self-healing system needs to detect DEGRADED states (slow queries, connection pool exhaustion, memory leaks) before they become outages.

Could I just restart the whole service when degradation is detected? That is the Kubernetes approach (liveness probes). But wait, restarting is a sledgehammer -- it drops all in-flight requests and takes time to warm up. I considered it as a last resort, but the first line of defense should be surgical remediation: reset the specific subsystem that is degraded.

For example, if the database connection pool has stale connections (common after a network blip), I should detect it via failed health-check queries and then drain and recreate just the pool -- not restart the whole service. Similarly, if a worker thread appears deadlocked (no progress for N seconds), I should terminate and replace that specific thread.

Hmm, but automated remediation can be dangerous. What if the detection logic has a false positive? You could be repeatedly restarting a healthy connection pool, causing the very instability you are trying to prevent. Therefore, I need safeguards: rate-limit remediation actions (at most once per N minutes per subsystem), require multiple consecutive health check failures before acting, and log every remediation action for review.

Actually, the pattern I want is: detect -> verify -> remediate -> verify again -> alert if remediation failed. The second verification step is critical -- if the self-healing action did not fix the problem, escalate to human operators rather than retrying in a loop.
</think>

Self-healing systems detect degradation and apply automatic remediation. Here are the key patterns:

```python
import time
import threading
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any


logger = logging.getLogger("self-healing")


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    last_check: float
    consecutive_failures: int = 0
    metadata: dict = field(default_factory=dict)


# ============================================================
# SELF-HEALING MANAGER
# ============================================================

class SelfHealingManager:
    """Runs health checks and triggers automatic remediation."""

    def __init__(self, check_interval: float = 10.0):
        self._checks: dict[str, dict] = {}
        self._check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_check(self, name: str,
                        checker: Callable[[], HealthCheck],
                        healer: Callable[[HealthCheck], bool],
                        max_failures_before_heal: int = 3,
                        max_heal_attempts: int = 3,
                        cooldown_seconds: float = 60.0):
        """Register a health check with its automatic remedy.

        Args:
            checker: Function that returns current health status
            healer: Function that attempts to fix the problem.
                    Returns True if fix was applied.
            max_failures_before_heal: Consecutive failures before
                                      attempting to heal
            max_heal_attempts: Maximum auto-heal attempts before
                               escalating to humans
            cooldown_seconds: Minimum time between heal attempts
        """
        self._checks[name] = {
            "checker": checker,
            "healer": healer,
            "max_failures": max_failures_before_heal,
            "max_heals": max_heal_attempts,
            "cooldown": cooldown_seconds,
            "heal_attempts": 0,
            "last_heal_time": 0.0,
            "consecutive_failures": 0,
            "status": HealthStatus.HEALTHY,
        }

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_loop(self):
        while self._running:
            for name, config in self._checks.items():
                try:
                    self._evaluate(name, config)
                except Exception as exc:
                    logger.error(f"Health check '{name}' crashed: {exc}")
            time.sleep(self._check_interval)

    def _evaluate(self, name: str, config: dict):
        check_result = config["checker"]()
        config["status"] = check_result.status

        if check_result.status == HealthStatus.HEALTHY:
            # Reset failure counters on healthy check
            config["consecutive_failures"] = 0
            config["heal_attempts"] = 0
            return

        # Track consecutive failures
        config["consecutive_failures"] += 1
        logger.warning(
            f"Health check '{name}' {check_result.status.value}: "
            f"{check_result.message} "
            f"(failure {config['consecutive_failures']}/"
            f"{config['max_failures']})"
        )

        # Should we attempt to heal?
        should_heal = (
            config["consecutive_failures"] >= config["max_failures"]
            and config["heal_attempts"] < config["max_heals"]
            and time.time() - config["last_heal_time"] >= config["cooldown"]
        )

        if should_heal:
            config["heal_attempts"] += 1
            config["last_heal_time"] = time.time()
            logger.info(
                f"Attempting self-heal for '{name}' "
                f"(attempt {config['heal_attempts']}/{config['max_heals']})"
            )
            try:
                success = config["healer"](check_result)
                if success:
                    logger.info(f"Self-heal for '{name}' succeeded")
                    config["consecutive_failures"] = 0
                else:
                    logger.warning(f"Self-heal for '{name}' reported failure")
            except Exception as exc:
                logger.error(f"Self-heal for '{name}' raised exception: {exc}")

        elif config["heal_attempts"] >= config["max_heals"]:
            logger.critical(
                f"'{name}' exhausted all {config['max_heals']} "
                f"heal attempts -- NEEDS HUMAN INTERVENTION"
            )

    def get_status(self) -> dict:
        return {
            name: {
                "status": config["status"].value,
                "consecutive_failures": config["consecutive_failures"],
                "heal_attempts": config["heal_attempts"],
            }
            for name, config in self._checks.items()
        }


# ============================================================
# PRACTICAL HEALERS
# ============================================================

class DatabasePoolHealer:
    """Detect and recover from database connection pool exhaustion."""

    def __init__(self, pool):
        self._pool = pool

    def check(self) -> HealthCheck:
        try:
            # Test a connection from the pool
            conn = self._pool.getconn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            self._pool.putconn(conn)

            # Check pool utilization
            used = self._pool.used_connections
            total = self._pool.max_connections
            utilization = used / max(total, 1)

            if utilization > 0.9:
                return HealthCheck(
                    name="database_pool",
                    status=HealthStatus.DEGRADED,
                    message=f"Pool {utilization:.0%} utilized ({used}/{total})",
                    last_check=time.time(),
                    metadata={"utilization": utilization},
                )

            return HealthCheck(
                name="database_pool",
                status=HealthStatus.HEALTHY,
                message=f"Pool OK ({used}/{total} connections)",
                last_check=time.time(),
            )
        except Exception as exc:
            return HealthCheck(
                name="database_pool",
                status=HealthStatus.UNHEALTHY,
                message=f"Pool check failed: {exc}",
                last_check=time.time(),
            )

    def heal(self, check: HealthCheck) -> bool:
        """Reset the connection pool."""
        try:
            logger.info("Resetting database connection pool...")
            self._pool.closeall()
            # Pool will recreate connections on next request
            time.sleep(1.0)
            # Verify recovery
            conn = self._pool.getconn()
            conn.cursor().execute("SELECT 1")
            self._pool.putconn(conn)
            return True
        except Exception as exc:
            logger.error(f"Pool reset failed: {exc}")
            return False


class CacheConsistencyHealer:
    """Detect and fix cache-database inconsistencies."""

    def __init__(self, cache, db, sample_keys_fn):
        self._cache = cache
        self._db = db
        self._sample_keys_fn = sample_keys_fn

    def check(self) -> HealthCheck:
        """Spot-check a sample of cached values against the database."""
        sample_keys = self._sample_keys_fn(count=10)
        mismatches = 0

        for key in sample_keys:
            cached = self._cache.get(key)
            actual = self._db.get(key)
            if cached is not None and cached != actual:
                mismatches += 1

        if mismatches > 3:
            return HealthCheck(
                name="cache_consistency",
                status=HealthStatus.UNHEALTHY,
                message=f"{mismatches}/10 sampled keys inconsistent",
                last_check=time.time(),
                metadata={"mismatches": mismatches},
            )
        elif mismatches > 0:
            return HealthCheck(
                name="cache_consistency",
                status=HealthStatus.DEGRADED,
                message=f"{mismatches}/10 sampled keys inconsistent",
                last_check=time.time(),
            )

        return HealthCheck(
            name="cache_consistency",
            status=HealthStatus.HEALTHY,
            message="Cache consistent with database",
            last_check=time.time(),
        )

    def heal(self, check: HealthCheck) -> bool:
        """Flush the entire cache and let it repopulate on demand."""
        try:
            logger.info("Flushing inconsistent cache...")
            self._cache.flush_all()
            return True
        except Exception as exc:
            logger.error(f"Cache flush failed: {exc}")
            return False


# ============================================================
# WIRING IT ALL TOGETHER
# ============================================================

# manager = SelfHealingManager(check_interval=15.0)
#
# db_healer = DatabasePoolHealer(db_pool)
# manager.register_check(
#     "database_pool",
#     checker=db_healer.check,
#     healer=db_healer.heal,
#     max_failures_before_heal=3,
#     max_heal_attempts=3,
#     cooldown_seconds=120.0,
# )
#
# cache_healer = CacheConsistencyHealer(redis_cache, db, get_sample_keys)
# manager.register_check(
#     "cache_consistency",
#     checker=cache_healer.check,
#     healer=cache_healer.heal,
#     max_failures_before_heal=2,
#     max_heal_attempts=2,
#     cooldown_seconds=300.0,
# )
#
# manager.start()
```

**Self-healing design rules:**

1. **Bounded retries**: always cap heal attempts -- infinite retries can make things worse (e.g., thundering herd on pool reset)
2. **Cooldown periods**: wait between heal attempts to let transient issues resolve and avoid rapid cycling
3. **Escalation**: after exhausting auto-heal attempts, alert a human -- some problems cannot be fixed automatically
4. **Spot-check, do not full-scan**: health checks must be cheap; sampling a few keys catches most inconsistencies
5. **Heal the least disruptive way**: flush a cache (safe) rather than restart the process (disruptive)''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement graceful shutdown in a service that is processing in-flight requests, running background tasks, and holding connections to external services? I need to shut down cleanly without losing work.''',
        r'''<think>
Graceful shutdown -- this could seem simple (stop accepting work, wait, close connections), but the ordering is everything. You cannot close the database connection before background tasks that use it have finished, and you cannot stop the health check endpoint until the load balancer has deregistered this instance.

My first thought for ordering: just do everything in sequence. But wait, some shutdown steps can run in parallel (e.g., draining the HTTP server and draining the message queue consumer are independent). Sequential shutdown wastes time during deployments, and a slow shutdown means Kubernetes sends SIGKILL after the grace period, losing in-flight work. So I need parallel phases with dependency ordering.

I considered a simple priority-based ordering (phase 1, phase 2, phase 3), but that does not capture real dependencies. What if component A depends on both B and C, but B and C are independent? Priority levels would force B and C into different phases even though they could shut down in parallel. Actually, what I need is a DAG-based shutdown coordinator -- each component declares its dependencies, and the coordinator computes the topological order, running independent shutdowns in parallel.

Hmm, there is another case I almost missed: what happens when shutdown times out? Some tasks will not finish in time. The coordinator needs a hard deadline after which it force-closes everything. But it should also save the state of incomplete work so it can be recovered on the next startup. This ties back into the checkpoint/restart pattern -- incomplete tasks should be checkpointed during shutdown so they resume after redeployment rather than being lost.
</think>

Graceful shutdown requires careful ordering: stop accepting work, drain in-flight tasks, then close resources in reverse dependency order. Here is a complete implementation:

```python
import signal
import time
import threading
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, Future


logger = logging.getLogger("shutdown")


class ShutdownPhase(Enum):
    RUNNING = "running"
    DRAINING = "draining"        # No new work, finishing in-flight
    SAVING_STATE = "saving"      # Persisting incomplete work
    CLOSING_RESOURCES = "closing" # Closing connections
    STOPPED = "stopped"


@dataclass
class ShutdownHook:
    name: str
    callback: Callable
    phase: ShutdownPhase
    priority: int = 0          # Lower number = runs first within phase
    timeout_seconds: float = 10.0


class GracefulShutdownManager:
    """Coordinates orderly shutdown across all service components."""

    def __init__(self, total_timeout: float = 30.0):
        self._total_timeout = total_timeout
        self._phase = ShutdownPhase.RUNNING
        self._hooks: list[ShutdownHook] = []
        self._in_flight: dict[str, Future] = {}
        self._in_flight_lock = threading.Lock()
        self._shutdown_event = threading.Event()

    @property
    def is_shutting_down(self) -> bool:
        return self._phase != ShutdownPhase.RUNNING

    @property
    def current_phase(self) -> ShutdownPhase:
        return self._phase

    def register_hook(self, name: str, callback: Callable,
                       phase: ShutdownPhase,
                       priority: int = 0,
                       timeout: float = 10.0):
        """Register a shutdown hook for a specific phase."""
        self._hooks.append(ShutdownHook(
            name=name,
            callback=callback,
            phase=phase,
            priority=priority,
            timeout_seconds=timeout,
        ))

    def track_request(self, request_id: str, future: Future):
        """Track an in-flight request for drain waiting."""
        if self.is_shutting_down:
            raise RuntimeError("Service is shutting down, not accepting work")
        with self._in_flight_lock:
            self._in_flight[request_id] = future
            future.add_done_callback(
                lambda f: self._remove_request(request_id)
            )

    def _remove_request(self, request_id: str):
        with self._in_flight_lock:
            self._in_flight.pop(request_id, None)

    def install_signal_handlers(self):
        """Install SIGTERM and SIGINT handlers."""
        def handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"Received {sig_name}, starting graceful shutdown")
            # Run shutdown in a separate thread to avoid signal handler issues
            threading.Thread(
                target=self.shutdown, daemon=False
            ).start()

        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def shutdown(self):
        """Execute the shutdown sequence."""
        if self._phase != ShutdownPhase.RUNNING:
            return  # Already shutting down

        deadline = time.time() + self._total_timeout
        logger.info(f"Shutdown started, timeout={self._total_timeout}s")

        # Phase 1: Stop accepting new work
        self._phase = ShutdownPhase.DRAINING
        logger.info("Phase 1: Draining in-flight requests...")
        self._run_hooks(ShutdownPhase.DRAINING, deadline)
        self._drain_in_flight(deadline)

        # Phase 2: Save incomplete state
        if time.time() < deadline:
            self._phase = ShutdownPhase.SAVING_STATE
            logger.info("Phase 2: Saving state...")
            self._run_hooks(ShutdownPhase.SAVING_STATE, deadline)

        # Phase 3: Close resources (reverse dependency order)
        if time.time() < deadline:
            self._phase = ShutdownPhase.CLOSING_RESOURCES
            logger.info("Phase 3: Closing resources...")
            self._run_hooks(ShutdownPhase.CLOSING_RESOURCES, deadline)

        self._phase = ShutdownPhase.STOPPED
        self._shutdown_event.set()
        logger.info("Shutdown complete")

    def _drain_in_flight(self, deadline: float):
        """Wait for all in-flight requests to complete."""
        while time.time() < deadline:
            with self._in_flight_lock:
                count = len(self._in_flight)
            if count == 0:
                logger.info("All in-flight requests drained")
                return
            remaining = deadline - time.time()
            logger.info(f"Waiting for {count} in-flight requests "
                       f"({remaining:.1f}s remaining)")
            time.sleep(min(1.0, remaining))

        with self._in_flight_lock:
            remaining = len(self._in_flight)
        if remaining > 0:
            logger.warning(
                f"Shutdown timeout: {remaining} requests still in flight"
            )

    def _run_hooks(self, phase: ShutdownPhase, deadline: float):
        """Run all hooks registered for this phase."""
        phase_hooks = sorted(
            [h for h in self._hooks if h.phase == phase],
            key=lambda h: h.priority,
        )

        for hook in phase_hooks:
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.warning(f"Skipping hook '{hook.name}': shutdown timeout")
                break

            timeout = min(hook.timeout_seconds, remaining)
            logger.info(f"Running hook '{hook.name}' (timeout={timeout:.1f}s)")

            try:
                # Run hook with timeout using a thread
                result_event = threading.Event()
                error_holder = [None]

                def run_hook():
                    try:
                        hook.callback()
                    except Exception as exc:
                        error_holder[0] = exc
                    finally:
                        result_event.set()

                t = threading.Thread(target=run_hook, daemon=True)
                t.start()

                if result_event.wait(timeout=timeout):
                    if error_holder[0]:
                        logger.error(
                            f"Hook '{hook.name}' failed: {error_holder[0]}"
                        )
                    else:
                        logger.info(f"Hook '{hook.name}' completed")
                else:
                    logger.warning(f"Hook '{hook.name}' timed out")
            except Exception as exc:
                logger.error(f"Hook '{hook.name}' error: {exc}")

    def wait_for_shutdown(self, timeout: float = None):
        """Block until shutdown completes."""
        self._shutdown_event.wait(timeout=timeout)


# ============================================================
# USAGE EXAMPLE
# ============================================================

class MyService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.shutdown_mgr = GracefulShutdownManager(total_timeout=30.0)

        # Register shutdown hooks in the right phases
        self.shutdown_mgr.register_hook(
            "stop_accepting_http",
            self._stop_http_server,
            ShutdownPhase.DRAINING,
            priority=0,
        )
        self.shutdown_mgr.register_hook(
            "stop_consuming_queue",
            self._stop_queue_consumer,
            ShutdownPhase.DRAINING,
            priority=1,
        )
        self.shutdown_mgr.register_hook(
            "save_incomplete_tasks",
            self._save_state,
            ShutdownPhase.SAVING_STATE,
        )
        self.shutdown_mgr.register_hook(
            "close_database",
            self._close_database,
            ShutdownPhase.CLOSING_RESOURCES,
            priority=10,  # Close DB last (other hooks may need it)
        )
        self.shutdown_mgr.register_hook(
            "close_cache",
            self._close_cache,
            ShutdownPhase.CLOSING_RESOURCES,
            priority=0,   # Close cache first
        )

        self.shutdown_mgr.install_signal_handlers()

    def handle_request(self, request_id: str, data: dict):
        """Process a request, tracking it for graceful shutdown."""
        if self.shutdown_mgr.is_shutting_down:
            raise RuntimeError("Service shutting down")

        future = self.executor.submit(self._process, data)
        self.shutdown_mgr.track_request(request_id, future)
        return future

    def _process(self, data):
        time.sleep(1)  # Simulate work
        return {"status": "ok"}

    def _stop_http_server(self):
        logger.info("HTTP server: stop accepting new connections")

    def _stop_queue_consumer(self):
        logger.info("Queue consumer: stopped")

    def _save_state(self):
        logger.info("Saving incomplete task state to disk")

    def _close_database(self):
        logger.info("Database connections closed")

    def _close_cache(self):
        logger.info("Cache connections closed")


# service = MyService()
# service.shutdown_mgr.wait_for_shutdown()
```

**Shutdown sequence matters:**

1. **Stop accepting work first**: close the HTTP listener, stop consuming from queues
2. **Drain in-flight**: wait for active requests to complete (with a deadline)
3. **Save state**: persist any incomplete work so it can be resumed on restart
4. **Close resources in reverse dependency order**: close cache before database (cache flushes might need DB)
5. **Always have a hard deadline**: if draining takes too long, force-stop and accept some loss

**Common mistakes:**

- Closing the database while background tasks are still running against it
- No timeout on drain phase -- a stuck request blocks shutdown forever
- Not handling a second SIGTERM (process manager sends SIGKILL after timeout)
- Saving state after closing resources (cannot save to DB if DB is closed)''',
    ),
]
