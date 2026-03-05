"""Data structures — LRU cache, trie, bloom filter, and priority queue implementations."""

PAIRS = [
    (
        "algorithms/lru-cache",
        "Show LRU cache implementation: doubly-linked list, O(1) operations, and TTL support.",
        '''LRU Cache implementation:

```python
from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import TypeVar, Generic, Hashable

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


# --- Simple LRU using OrderedDict ---

class LRUCache(Generic[K, V]):
    """Least Recently Used cache with O(1) get/put."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            if key not in self._cache:
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self.capacity:
                    # Remove least recently used (first item)
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def delete(self, key: K) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    def __contains__(self, key: K) -> bool:
        return key in self._cache

    def __repr__(self) -> str:
        return f"LRUCache(capacity={self.capacity}, size={self.size})"


# --- LRU with TTL (time-to-live) ---

class TTLCache(Generic[K, V]):
    """LRU cache with per-item expiration."""

    def __init__(self, capacity: int, default_ttl: float = 300.0):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self._cache: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            if key not in self._cache:
                return None

            value, expires_at = self._cache[key]

            # Check TTL
            if monotonic() > expires_at:
                del self._cache[key]
                return None

            self._cache.move_to_end(key)
            return value

    def put(self, key: K, value: V, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = monotonic() + ttl

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.capacity:
                self._cache.popitem(last=False)

            self._cache[key] = (value, expires_at)

    def _evict_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = monotonic()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for key in expired:
            del self._cache[key]
        return len(expired)


# --- Usage ---

cache = LRUCache[str, dict](capacity=1000)
cache.put("user:1", {"name": "Alice", "email": "alice@example.com"})
user = cache.get("user:1")  # Returns dict, moves to most-recent

ttl_cache = TTLCache[str, str](capacity=500, default_ttl=60.0)
ttl_cache.put("session:abc", "user-1", ttl=3600)  # 1 hour TTL
ttl_cache.put("rate:ip:1.2.3.4", "50", ttl=60)    # 60 second TTL
```

LRU Cache patterns:
1. **`OrderedDict`** — O(1) `move_to_end()` and `popitem(last=False)` for LRU eviction
2. **Thread safety** — `Lock` protects concurrent access from multiple threads
3. **TTL support** — `monotonic()` timestamps for per-item expiration
4. **Generic types** — `LRUCache[str, dict]` for type-safe key/value pairs
5. **Lazy expiration** — check TTL on `get()`, batch cleanup via `_evict_expired()`'''
    ),
    (
        "algorithms/trie",
        "Show Trie (prefix tree) implementation: insert, search, prefix matching, and autocomplete.",
        '''Trie (prefix tree) implementation:

```python
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TrieNode:
    children: dict[str, "TrieNode"] = field(default_factory=dict)
    is_end: bool = False
    value: any = None       # Store associated value
    count: int = 0          # Number of words through this node


class Trie:
    """Prefix tree for efficient string operations."""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str, value: any = None) -> None:
        """Insert word into trie. O(m) where m = word length."""
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.count += 1
        node.is_end = True
        node.value = value

    def search(self, word: str) -> bool:
        """Check if exact word exists. O(m)."""
        node = self._find_node(word)
        return node is not None and node.is_end

    def starts_with(self, prefix: str) -> bool:
        """Check if any word starts with prefix. O(m)."""
        return self._find_node(prefix) is not None

    def get(self, word: str) -> any:
        """Get value associated with word."""
        node = self._find_node(word)
        if node and node.is_end:
            return node.value
        return None

    def count_prefix(self, prefix: str) -> int:
        """Count words that start with prefix."""
        node = self._find_node(prefix)
        return node.count if node else 0

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        """Find all words starting with prefix."""
        node = self._find_node(prefix)
        if not node:
            return []

        results = []
        self._collect_words(node, prefix, results, limit)
        return results

    def delete(self, word: str) -> bool:
        """Delete word from trie."""
        def _delete(node: TrieNode, word: str, depth: int) -> bool:
            if depth == len(word):
                if not node.is_end:
                    return False
                node.is_end = False
                node.value = None
                return len(node.children) == 0

            char = word[depth]
            if char not in node.children:
                return False

            child = node.children[char]
            child.count -= 1
            should_delete = _delete(child, word, depth + 1)

            if should_delete:
                del node.children[char]
                return not node.is_end and len(node.children) == 0

            return False

        return _delete(self.root, word, 0)

    def _find_node(self, prefix: str) -> TrieNode | None:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _collect_words(
        self, node: TrieNode, prefix: str,
        results: list[str], limit: int,
    ) -> None:
        if len(results) >= limit:
            return
        if node.is_end:
            results.append(prefix)
        for char in sorted(node.children):
            self._collect_words(node.children[char], prefix + char, results, limit)


# --- Usage ---

# Autocomplete
trie = Trie()
words = ["apple", "app", "application", "apply", "banana", "band", "bandana"]
for word in words:
    trie.insert(word)

trie.autocomplete("app")    # ["app", "apple", "application", "apply"]
trie.autocomplete("ban")    # ["banana", "band", "bandana"]
trie.count_prefix("app")    # 4
trie.search("apple")        # True
trie.search("appl")         # False (not a complete word)

# Dictionary with values
dict_trie = Trie()
dict_trie.insert("GET", {"method": "GET", "handler": "list_users"})
dict_trie.insert("GET/users", {"method": "GET", "handler": "list_users"})
dict_trie.insert("POST/users", {"method": "POST", "handler": "create_user"})
route = dict_trie.get("GET/users")  # {"method": "GET", "handler": "list_users"}
```

Trie patterns:
1. **O(m) operations** — insert/search/delete proportional to word length, not dictionary size
2. **`autocomplete()`** — DFS from prefix node collects all completions
3. **`count` field** — track prefix frequency for ranking suggestions
4. **Value storage** — associate data with keys (like a prefix-aware dictionary)
5. **Sorted iteration** — `sorted(node.children)` returns completions alphabetically'''
    ),
    (
        "algorithms/bloom-filter",
        "Show Bloom filter implementation: probabilistic membership testing with configurable false positive rate.",
        '''Bloom filter implementation:

```python
import math
import hashlib
from typing import Any


class BloomFilter:
    """Space-efficient probabilistic set membership test.

    - `add()`:  O(k) — always correct
    - `contains()`: O(k) — may return false positive, never false negative
    - Space: much smaller than storing actual elements
    """

    def __init__(self, expected_items: int, false_positive_rate: float = 0.01):
        # Calculate optimal size and hash count
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.num_hashes = self._optimal_hashes(self.size, expected_items)
        self.bit_array = bytearray(math.ceil(self.size / 8))
        self.count = 0

        self._expected = expected_items
        self._fp_rate = false_positive_rate

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """Optimal bit array size: m = -(n * ln(p)) / (ln(2)^2)"""
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        """Optimal hash count: k = (m/n) * ln(2)"""
        return max(1, int((m / n) * math.log(2)))

    def _get_bit_positions(self, item: str) -> list[int]:
        """Generate k bit positions using double hashing."""
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]

    def _set_bit(self, position: int) -> None:
        byte_idx = position // 8
        bit_idx = position % 8
        self.bit_array[byte_idx] |= (1 << bit_idx)

    def _get_bit(self, position: int) -> bool:
        byte_idx = position // 8
        bit_idx = position % 8
        return bool(self.bit_array[byte_idx] & (1 << bit_idx))

    def add(self, item: str) -> None:
        """Add item to the filter."""
        for pos in self._get_bit_positions(item):
            self._set_bit(pos)
        self.count += 1

    def contains(self, item: str) -> bool:
        """Check if item might be in the filter.

        Returns:
            True = item is PROBABLY in the set (may be false positive)
            False = item is DEFINITELY NOT in the set
        """
        return all(self._get_bit(pos) for pos in self._get_bit_positions(item))

    def __contains__(self, item: str) -> bool:
        return self.contains(item)

    @property
    def estimated_fp_rate(self) -> float:
        """Current estimated false positive rate."""
        # (1 - e^(-kn/m))^k
        exponent = -self.num_hashes * self.count / self.size
        return (1 - math.exp(exponent)) ** self.num_hashes

    def __repr__(self) -> str:
        size_kb = len(self.bit_array) / 1024
        return (
            f"BloomFilter(items={self.count}, size={size_kb:.1f}KB, "
            f"hashes={self.num_hashes}, fp_rate={self.estimated_fp_rate:.4f})"
        )


# --- Usage: duplicate URL checker ---

def check_crawled_urls():
    # 1 million URLs with 1% false positive rate
    seen = BloomFilter(expected_items=1_000_000, false_positive_rate=0.01)
    # Size: ~1.2 MB (vs ~50 MB for a set of URLs)

    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page1",  # Duplicate
    ]

    for url in urls:
        if url in seen:
            print(f"Skip (probably seen): {url}")
        else:
            print(f"Crawl: {url}")
            seen.add(url)


# --- Usage: email dedup in batch processing ---

def deduplicate_emails(emails: list[str]) -> list[str]:
    bf = BloomFilter(expected_items=len(emails), false_positive_rate=0.001)
    unique = []

    for email in emails:
        email_lower = email.lower().strip()
        if email_lower not in bf:
            bf.add(email_lower)
            unique.append(email)

    return unique


# --- Counting Bloom Filter (supports deletion) ---

class CountingBloomFilter:
    """Bloom filter variant that supports deletion via counters."""

    def __init__(self, expected_items: int, false_positive_rate: float = 0.01):
        size = BloomFilter._optimal_size(expected_items, false_positive_rate)
        self.num_hashes = BloomFilter._optimal_hashes(size, expected_items)
        self.counters = [0] * size
        self.size = size

    def _positions(self, item: str) -> list[int]:
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]

    def add(self, item: str):
        for pos in self._positions(item):
            self.counters[pos] += 1

    def remove(self, item: str):
        positions = self._positions(item)
        if all(self.counters[pos] > 0 for pos in positions):
            for pos in positions:
                self.counters[pos] -= 1

    def __contains__(self, item: str) -> bool:
        return all(self.counters[pos] > 0 for pos in self._positions(item))
```

Bloom filter patterns:
1. **Optimal sizing** — `m = -(n * ln(p)) / (ln(2)^2)` for target false positive rate
2. **Double hashing** — MD5 + SHA256 generate k independent hash positions
3. **No false negatives** — `False` from `contains()` is always correct
4. **Space efficiency** — 1M items at 1% FP rate ≈ 1.2 MB (vs 50+ MB for a set)
5. **Counting variant** — integer counters instead of bits enable `remove()` support'''
    ),
]
