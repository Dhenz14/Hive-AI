PAIRS = [
    ("projects/cache-layer", r'''<think>
A multi-tier cache needs L1 (in-memory) and L2 (Redis/disk) tiers.
Read from L1 first, fall through to L2, then origin.
Writes should propagate to both tiers.
</think>
Build a multi-tier caching system with L1 in-memory cache and L2 persistent cache.''', r'''import time
import threading
import hashlib
import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class CacheEntry:
    """A single cache entry with metadata."""
    key: str
    value: Any
    created_at: float
    expires_at: Optional[float]
    access_count: int = 0
    last_accessed: float = 0.0
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class LRUCache(CacheBackend):
    """In-memory LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000, default_ttl: Optional[float] = None):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._store[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._store.move_to_end(key)
            entry.access_count += 1
            entry.last_accessed = time.time()
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        effective_ttl = ttl or self._default_ttl
        expires_at = time.time() + effective_ttl if effective_ttl else None

        with self._lock:
            if key in self._store:
                del self._store[key]

            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                expires_at=expires_at,
                last_accessed=time.time(),
            )
            self._store[key] = entry

            # Evict oldest if over capacity
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            entry = self._store.get(key)
            if entry and not entry.is_expired:
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }


class MultiTierCache:
    """Multi-tier cache that reads from L1 first, then L2."""

    def __init__(self, l1: CacheBackend, l2: CacheBackend):
        self._l1 = l1
        self._l2 = l2

    def get(self, key: str) -> Optional[Any]:
        # Try L1 first
        value = self._l1.get(key)
        if value is not None:
            return value

        # Try L2
        value = self._l2.get(key)
        if value is not None:
            # Promote to L1
            self._l1.set(key, value)
            return value

        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        # Write to both tiers
        self._l1.set(key, value, ttl)
        self._l2.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        l1_deleted = self._l1.delete(key)
        l2_deleted = self._l2.delete(key)
        return l1_deleted or l2_deleted

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern (if backend supports it)."""
        count = 0
        if hasattr(self._l1, '_store'):
            keys_to_delete = [k for k in self._l1._store if pattern in k]
            for k in keys_to_delete:
                self._l1.delete(k)
                self._l2.delete(k)
                count += 1
        return count

    def clear(self) -> None:
        self._l1.clear()
        self._l2.clear()

    @property
    def stats(self) -> dict:
        return {
            "l1": self._l1.stats if hasattr(self._l1, "stats") else {},
            "l2": self._l2.stats if hasattr(self._l2, "stats") else {},
        }
'''),
    ("projects/cache-layer", r'''Implement TTL management with lazy and active expiration, plus TTL extension on access.''', r'''import time
import threading
import heapq
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class TTLManager:
    """Manages TTL for cache entries with both lazy and active expiration."""

    def __init__(self, cleanup_interval: float = 60.0):
        self._expiry_heap: List[Tuple[float, str]] = []  # (expires_at, key)
        self._key_expiry: Dict[str, float] = {}  # key -> expires_at
        self._lock = threading.Lock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_expire_callbacks: List = []
        self._expired_count = 0

    def set_ttl(self, key: str, ttl: float) -> None:
        """Set TTL for a key."""
        expires_at = time.time() + ttl
        with self._lock:
            self._key_expiry[key] = expires_at
            heapq.heappush(self._expiry_heap, (expires_at, key))

    def get_ttl(self, key: str) -> Optional[float]:
        """Get remaining TTL for a key."""
        with self._lock:
            expires_at = self._key_expiry.get(key)
            if expires_at is None:
                return None
            remaining = expires_at - time.time()
            return max(0, remaining)

    def is_expired(self, key: str) -> bool:
        """Check if a key has expired (lazy check)."""
        with self._lock:
            expires_at = self._key_expiry.get(key)
            if expires_at is None:
                return False
            return time.time() > expires_at

    def extend_ttl(self, key: str, additional_seconds: float) -> bool:
        """Extend the TTL of an existing key."""
        with self._lock:
            current = self._key_expiry.get(key)
            if current is None:
                return False
            new_expiry = max(current, time.time()) + additional_seconds
            self._key_expiry[key] = new_expiry
            heapq.heappush(self._expiry_heap, (new_expiry, key))
            return True

    def touch(self, key: str, ttl: Optional[float] = None) -> bool:
        """Reset TTL to original value or a new value on access."""
        with self._lock:
            if key not in self._key_expiry:
                return False
            if ttl is not None:
                new_expiry = time.time() + ttl
            else:
                # Reset to same duration from now
                current = self._key_expiry[key]
                remaining = current - time.time()
                new_expiry = time.time() + max(remaining, 0)
            self._key_expiry[key] = new_expiry
            heapq.heappush(self._expiry_heap, (new_expiry, key))
            return True

    def remove(self, key: str) -> None:
        """Remove a key from TTL tracking."""
        with self._lock:
            self._key_expiry.pop(key, None)

    def on_expire(self, callback) -> None:
        """Register a callback for when entries expire."""
        self._on_expire_callbacks.append(callback)

    def start_active_cleanup(self) -> None:
        """Start the background cleanup thread."""
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def stop_active_cleanup(self) -> None:
        """Stop the background cleanup thread."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5.0)

    def _cleanup_loop(self) -> None:
        """Periodically clean up expired entries."""
        while self._running:
            expired_keys = self._sweep()
            for key in expired_keys:
                for callback in self._on_expire_callbacks:
                    try:
                        callback(key)
                    except Exception as e:
                        logger.error(f"Expire callback error for key '{key}': {e}")
            time.sleep(self._cleanup_interval)

    def _sweep(self) -> List[str]:
        """Sweep expired entries from the heap. Returns list of expired keys."""
        expired = []
        now = time.time()

        with self._lock:
            while self._expiry_heap:
                expires_at, key = self._expiry_heap[0]

                if expires_at > now:
                    break

                heapq.heappop(self._expiry_heap)

                # Verify this is still the current expiry for this key
                current_expiry = self._key_expiry.get(key)
                if current_expiry is not None and current_expiry <= now:
                    del self._key_expiry[key]
                    expired.append(key)
                    self._expired_count += 1

        return expired

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "tracked_keys": len(self._key_expiry),
                "heap_size": len(self._expiry_heap),
                "total_expired": self._expired_count,
            }


class SlidingWindowTTL:
    """TTL that extends on each access (sliding window expiration)."""

    def __init__(self, ttl_manager: TTLManager, default_ttl: float = 300.0):
        self._manager = ttl_manager
        self._default_ttl = default_ttl
        self._original_ttls: Dict[str, float] = {}

    def set(self, key: str, ttl: Optional[float] = None) -> None:
        """Set a sliding window TTL."""
        effective_ttl = ttl or self._default_ttl
        self._original_ttls[key] = effective_ttl
        self._manager.set_ttl(key, effective_ttl)

    def access(self, key: str) -> bool:
        """Record an access, extending the TTL."""
        original_ttl = self._original_ttls.get(key)
        if original_ttl is None:
            return False
        # Reset TTL from now
        self._manager.set_ttl(key, original_ttl)
        return True

    def remove(self, key: str) -> None:
        self._original_ttls.pop(key, None)
        self._manager.remove(key)
'''),
    ("projects/cache-layer", r'''Implement cache invalidation strategies: tag-based invalidation, dependency tracking, and write-through/write-behind patterns.''', r'''import time
import threading
import logging
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TagBasedInvalidation:
    """Invalidate cache entries by tags (e.g., invalidate all entries tagged 'user:123').

    Each cache entry can be associated with one or more tags.
    When a tag is invalidated, all entries with that tag are removed.
    """

    def __init__(self):
        self._tag_to_keys: Dict[str, Set[str]] = {}
        self._key_to_tags: Dict[str, Set[str]] = {}

    def tag_entry(self, key: str, tags: List[str]) -> None:
        """Associate tags with a cache key."""
        self._key_to_tags[key] = set(tags)
        for tag in tags:
            if tag not in self._tag_to_keys:
                self._tag_to_keys[tag] = set()
            self._tag_to_keys[tag].add(key)

    def invalidate_tag(self, tag: str) -> Set[str]:
        """Invalidate all entries with a given tag. Returns affected keys."""
        affected_keys = self._tag_to_keys.pop(tag, set())
        for key in affected_keys:
            tags = self._key_to_tags.get(key, set())
            tags.discard(tag)
            if not tags:
                self._key_to_tags.pop(key, None)
            # Clean up other tag references
            for other_tag in tags:
                if other_tag in self._tag_to_keys:
                    self._tag_to_keys[other_tag].discard(key)
        return affected_keys

    def remove_key(self, key: str) -> None:
        """Remove all tag associations for a key."""
        tags = self._key_to_tags.pop(key, set())
        for tag in tags:
            if tag in self._tag_to_keys:
                self._tag_to_keys[tag].discard(key)

    def get_tags(self, key: str) -> Set[str]:
        return self._key_to_tags.get(key, set())

    def get_keys_for_tag(self, tag: str) -> Set[str]:
        return self._tag_to_keys.get(tag, set()).copy()


class DependencyTracker:
    """Tracks dependencies between cache entries for cascading invalidation."""

    def __init__(self):
        self._depends_on: Dict[str, Set[str]] = {}  # key -> keys it depends on
        self._dependents: Dict[str, Set[str]] = {}   # key -> keys that depend on it

    def add_dependency(self, key: str, depends_on: str) -> None:
        """Mark that `key` depends on `depends_on`."""
        if key not in self._depends_on:
            self._depends_on[key] = set()
        self._depends_on[key].add(depends_on)

        if depends_on not in self._dependents:
            self._dependents[depends_on] = set()
        self._dependents[depends_on].add(key)

    def get_cascade(self, key: str) -> Set[str]:
        """Get all keys that should be invalidated when `key` changes."""
        to_invalidate = set()
        queue = [key]
        visited = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            dependents = self._dependents.get(current, set())
            to_invalidate.update(dependents)
            queue.extend(dependents)

        return to_invalidate

    def remove_key(self, key: str) -> None:
        """Remove all dependency records for a key."""
        deps = self._depends_on.pop(key, set())
        for dep in deps:
            if dep in self._dependents:
                self._dependents[dep].discard(key)

        dependents = self._dependents.pop(key, set())
        for dep in dependents:
            if dep in self._depends_on:
                self._depends_on[dep].discard(key)


class WriteThroughCache:
    """Cache that writes to both cache and backend synchronously."""

    def __init__(self, cache_backend, data_backend):
        self._cache = cache_backend
        self._data = data_backend
        self._tag_invalidation = TagBasedInvalidation()
        self._dep_tracker = DependencyTracker()

    def get(self, key: str) -> Optional[Any]:
        # Try cache first
        value = self._cache.get(key)
        if value is not None:
            return value

        # Read from data backend
        value = self._data.get(key)
        if value is not None:
            self._cache.set(key, value)
        return value

    def set(self, key: str, value: Any, tags: Optional[List[str]] = None, ttl: Optional[float] = None) -> None:
        """Write to both cache and backend."""
        # Write to backend first
        self._data.set(key, value)
        # Then cache
        self._cache.set(key, value, ttl=ttl)

        if tags:
            self._tag_invalidation.tag_entry(key, tags)

        # Cascade invalidation
        cascade = self._dep_tracker.get_cascade(key)
        for dep_key in cascade:
            self._cache.delete(dep_key)

    def delete(self, key: str) -> None:
        self._data.delete(key)
        self._cache.delete(key)
        cascade = self._dep_tracker.get_cascade(key)
        for dep_key in cascade:
            self._cache.delete(dep_key)
        self._tag_invalidation.remove_key(key)
        self._dep_tracker.remove_key(key)

    def invalidate_tag(self, tag: str) -> int:
        """Invalidate all entries with a tag."""
        affected = self._tag_invalidation.invalidate_tag(tag)
        for key in affected:
            self._cache.delete(key)
        return len(affected)


class WriteBehindCache:
    """Cache that writes to backend asynchronously for better write performance."""

    def __init__(self, cache_backend, data_backend, flush_interval: float = 5.0, batch_size: int = 100):
        self._cache = cache_backend
        self._data = data_backend
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._write_queue: Dict[str, Any] = {}
        self._delete_queue: Set[str] = set()
        self._lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._running = False

    def get(self, key: str) -> Optional[Any]:
        # Check write queue first (it has the most recent value)
        with self._lock:
            if key in self._write_queue:
                return self._write_queue[key]
            if key in self._delete_queue:
                return None
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        self._cache.set(key, value, ttl=ttl)
        with self._lock:
            self._write_queue[key] = value
            self._delete_queue.discard(key)
            if len(self._write_queue) >= self._batch_size:
                self._flush_writes()

    def delete(self, key: str) -> None:
        self._cache.delete(key)
        with self._lock:
            self._write_queue.pop(key, None)
            self._delete_queue.add(key)

    def start(self) -> None:
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        self._running = False
        self._flush_writes()
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self._flush_interval)
            self._flush_writes()

    def _flush_writes(self) -> None:
        with self._lock:
            writes = dict(self._write_queue)
            deletes = set(self._delete_queue)
            self._write_queue.clear()
            self._delete_queue.clear()

        for key, value in writes.items():
            try:
                self._data.set(key, value)
            except Exception as e:
                logger.error(f"Write-behind flush error for key '{key}': {e}")

        for key in deletes:
            try:
                self._data.delete(key)
            except Exception as e:
                logger.error(f"Write-behind delete error for key '{key}': {e}")
'''),
    ("projects/cache-layer", r'''Implement cache serialization supporting multiple formats and a metrics collector for cache operations.''', r'''import json
import pickle
import time
import threading
import hashlib
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class CacheSerializer(ABC):
    """Abstract serializer for cache values."""

    @abstractmethod
    def serialize(self, value: Any) -> bytes:
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        pass


class JSONSerializer(CacheSerializer):
    """JSON-based serializer for cache values."""

    def serialize(self, value: Any) -> bytes:
        return json.dumps(value, default=str).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class PickleSerializer(CacheSerializer):
    """Pickle-based serializer for complex Python objects."""

    def serialize(self, value: Any) -> bytes:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize(self, data: bytes) -> Any:
        return pickle.loads(data)


class MsgpackSerializer(CacheSerializer):
    """MessagePack serializer (requires msgpack package)."""

    def serialize(self, value: Any) -> bytes:
        import msgpack
        return msgpack.packb(value, use_bin_type=True, default=str)

    def deserialize(self, data: bytes) -> Any:
        import msgpack
        return msgpack.unpackb(data, raw=False)


class CompressedSerializer(CacheSerializer):
    """Wraps another serializer with compression."""

    def __init__(self, inner: CacheSerializer, min_size: int = 1024):
        self._inner = inner
        self._min_size = min_size

    def serialize(self, value: Any) -> bytes:
        import zlib
        data = self._inner.serialize(value)
        if len(data) >= self._min_size:
            compressed = zlib.compress(data, level=6)
            return b"\x01" + compressed  # prefix to indicate compression
        return b"\x00" + data

    def deserialize(self, data: bytes) -> Any:
        import zlib
        if data[0:1] == b"\x01":
            data = zlib.decompress(data[1:])
        else:
            data = data[1:]
        return self._inner.deserialize(data)


@dataclass
class OperationMetric:
    """Metrics for a single cache operation type."""
    count: int = 0
    total_time_ms: float = 0.0
    errors: int = 0

    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / self.count if self.count > 0 else 0.0


class CacheMetrics:
    """Collects and reports cache operation metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._operations: Dict[str, OperationMetric] = defaultdict(OperationMetric)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._bytes_read = 0
        self._bytes_written = 0
        self._start_time = time.time()

    def record_hit(self) -> None:
        with self._lock:
            self._hits += 1

    def record_miss(self) -> None:
        with self._lock:
            self._misses += 1

    def record_eviction(self) -> None:
        with self._lock:
            self._evictions += 1

    def record_operation(self, op_name: str, duration_ms: float, size_bytes: int = 0, is_read: bool = True) -> None:
        with self._lock:
            metric = self._operations[op_name]
            metric.count += 1
            metric.total_time_ms += duration_ms
            if is_read:
                self._bytes_read += size_bytes
            else:
                self._bytes_written += size_bytes

    def record_error(self, op_name: str) -> None:
        with self._lock:
            self._operations[op_name].errors += 1

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return (self._hits / total * 100) if total > 0 else 0.0

    def get_report(self) -> dict:
        with self._lock:
            uptime = time.time() - self._start_time
            total_ops = sum(m.count for m in self._operations.values())
            ops_per_second = total_ops / uptime if uptime > 0 else 0

            return {
                "uptime_seconds": f"{uptime:.0f}",
                "total_operations": total_ops,
                "ops_per_second": f"{ops_per_second:.1f}",
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self.hit_rate:.1f}%",
                "evictions": self._evictions,
                "bytes_read": self._bytes_read,
                "bytes_written": self._bytes_written,
                "operations": {
                    name: {
                        "count": m.count,
                        "avg_time_ms": f"{m.avg_time_ms:.2f}",
                        "errors": m.errors,
                    }
                    for name, m in self._operations.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._operations.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._bytes_read = 0
            self._bytes_written = 0
            self._start_time = time.time()


class InstrumentedCache:
    """Wraps a cache backend with automatic metrics collection."""

    def __init__(self, backend, metrics: Optional[CacheMetrics] = None):
        self._backend = backend
        self._metrics = metrics or CacheMetrics()

    def get(self, key: str) -> Optional[Any]:
        start = time.perf_counter()
        try:
            value = self._backend.get(key)
            duration = (time.perf_counter() - start) * 1000
            if value is not None:
                self._metrics.record_hit()
                self._metrics.record_operation("get", duration, is_read=True)
            else:
                self._metrics.record_miss()
                self._metrics.record_operation("get_miss", duration, is_read=True)
            return value
        except Exception:
            self._metrics.record_error("get")
            raise

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        start = time.perf_counter()
        try:
            self._backend.set(key, value, ttl=ttl)
            duration = (time.perf_counter() - start) * 1000
            self._metrics.record_operation("set", duration, is_read=False)
        except Exception:
            self._metrics.record_error("set")
            raise

    def delete(self, key: str) -> bool:
        start = time.perf_counter()
        try:
            result = self._backend.delete(key)
            duration = (time.perf_counter() - start) * 1000
            self._metrics.record_operation("delete", duration)
            return result
        except Exception:
            self._metrics.record_error("delete")
            raise

    @property
    def stats(self) -> dict:
        return self._metrics.get_report()
'''),
    ("projects/cache-layer", r'''<think>
A cache decorator (memoization) is one of the most common uses.
I need a decorator that auto-generates cache keys from function
arguments and supports TTL, cache invalidation, and key prefixing.
</think>
Implement a caching decorator for function memoization with automatic key generation and TTL.''', r'''import functools
import hashlib
import inspect
import json
import time
from typing import Any, Callable, Optional, TypeVar, Union

F = TypeVar("F", bound=Callable)


def _make_cache_key(prefix: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """Generate a deterministic cache key from function arguments."""
    # Get function signature for consistent key ordering
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    # Build key components
    parts = [prefix, func.__module__, func.__qualname__]

    for param_name, value in bound.arguments.items():
        try:
            serialized = json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            serialized = repr(value)
        parts.append(f"{param_name}={serialized}")

    key_string = ":".join(parts)

    # Use hash for long keys
    if len(key_string) > 200:
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"{prefix}:{func.__qualname__}:{key_hash}"

    return key_string


def cached(
    cache_backend=None,
    ttl: Optional[float] = None,
    prefix: str = "cache",
    key_func: Optional[Callable] = None,
    unless: Optional[Callable] = None,
    max_size: int = 1000,
) -> Callable:
    """Decorator to cache function results.

    Args:
        cache_backend: Cache backend to use. If None, uses a simple dict.
        ttl: Time-to-live in seconds.
        prefix: Key prefix for namespacing.
        key_func: Custom function to generate cache keys.
        unless: Callable that returns True to skip caching.
        max_size: Max entries for the default dict cache.
    """
    # Use a simple dict cache if no backend provided
    if cache_backend is None:
        from collections import OrderedDict
        _local_cache = OrderedDict()
        _local_expiry = {}

        class LocalBackend:
            def get(self, key):
                if key in _local_expiry and time.time() > _local_expiry[key]:
                    _local_cache.pop(key, None)
                    _local_expiry.pop(key, None)
                    return None
                return _local_cache.get(key)

            def set(self, key, value, ttl=None):
                _local_cache[key] = value
                if ttl:
                    _local_expiry[key] = time.time() + ttl
                while len(_local_cache) > max_size:
                    oldest_key = next(iter(_local_cache))
                    del _local_cache[oldest_key]
                    _local_expiry.pop(oldest_key, None)

            def delete(self, key):
                _local_cache.pop(key, None)
                _local_expiry.pop(key, None)

        cache_backend = LocalBackend()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check unless condition
            if unless and unless():
                return func(*args, **kwargs)

            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = _make_cache_key(prefix, func, args, kwargs)

            # Try cache
            cached_value = cache_backend.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            if result is not None:
                cache_backend.set(cache_key, result, ttl=ttl)

            return result

        # Attach cache control methods
        def invalidate(*args, **kwargs):
            """Invalidate the cached result for specific arguments."""
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = _make_cache_key(prefix, func, args, kwargs)
            cache_backend.delete(cache_key)

        def invalidate_all():
            """Clear all cached results for this function."""
            if hasattr(cache_backend, "clear"):
                cache_backend.clear()

        wrapper.invalidate = invalidate
        wrapper.invalidate_all = invalidate_all
        wrapper.cache_key = lambda *a, **kw: _make_cache_key(prefix, func, a, kw)

        return wrapper  # type: ignore
    return decorator


def cache_aside(
    cache_backend,
    key: str,
    ttl: Optional[float] = None,
    tags: Optional[list] = None,
) -> Callable:
    """Cache-aside pattern: check cache, compute if miss, store result.

    Usage:
        @cache_aside(redis_cache, key="user:{user_id}", ttl=300)
        def get_user(user_id: int):
            return db.query(User).get(user_id)
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve key template
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            resolved_key = key.format(**bound.arguments)

            # Check cache
            cached_value = cache_backend.get(resolved_key)
            if cached_value is not None:
                return cached_value

            # Compute value
            result = func(*args, **kwargs)

            # Store in cache
            if result is not None:
                cache_backend.set(resolved_key, result, ttl=ttl)

            return result

        return wrapper  # type: ignore
    return decorator


# Usage examples:
# @cached(ttl=300, prefix="users")
# def get_user_profile(user_id: int) -> dict:
#     return db.query(f"SELECT * FROM users WHERE id = {user_id}")
#
# get_user_profile(123)  # Computes and caches
# get_user_profile(123)  # Returns from cache
# get_user_profile.invalidate(123)  # Clear specific cache entry
'''),
]
