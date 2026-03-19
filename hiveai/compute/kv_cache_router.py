"""
hiveai/compute/kv_cache_router.py

KV-Cache Aware Router — routes inference requests to nodes that already
have relevant KV-cache entries, reducing redundant prefill computation.

Inspired by llm-d (Kubernetes-native distributed LLM serving):
  - Track which nodes have computed prefill for which prompt prefixes
  - Route follow-up requests to the same node (cache affinity)
  - Gracefully handle cache eviction and node failures
  - Support multi-turn conversations with cache continuity

This is the efficiency multiplier for cluster inference:
  Without cache routing: every request starts from scratch (full prefill)
  With cache routing: follow-up messages reuse cached KV state (5-10x faster TTFT)

Architecture:
  Request → Router → Cache Index → Best Node → Response
                         ↓
                   Cache Miss → Least-loaded node
                   Cache Hit → Node with cache → Skip prefill

Key insight from llm-d:
  "KV-cache is the new session state" — route by cache affinity,
  not just load, and you get datacenter-quality TTFT on a community mesh.
"""

import hashlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Cache index configuration
CACHE_TTL_SECONDS = 600  # entries expire after 10 min
MAX_CACHE_ENTRIES_PER_NODE = 1000  # prevent memory bloat
PREFIX_HASH_LENGTH = 16  # bytes of prefix hash to store


@dataclass
class CacheEntry:
    """Tracks a KV-cache entry on a specific node."""
    prefix_hash: str  # hash of the prompt prefix
    node_id: str
    token_count: int  # how many tokens are cached
    created_at: float
    last_accessed: float
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() - self.last_accessed > CACHE_TTL_SECONDS

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    node_id: str
    reason: str  # "cache_hit", "cache_partial", "load_balance", "fallback"
    cache_tokens: int = 0  # tokens that can be skipped
    estimated_prefill_savings_ms: float = 0.0


class KVCacheIndex:
    """
    Distributed KV-cache index.

    Tracks which nodes have cached prefill results for which prompts.
    Uses consistent hashing of prompt prefixes to detect cache affinity.
    """

    def __init__(self):
        # prefix_hash → list of CacheEntry
        self._entries: dict[str, list[CacheEntry]] = defaultdict(list)
        # node_id → count of active entries
        self._node_entry_count: dict[str, int] = defaultdict(int)

    def register_cache(
        self,
        node_id: str,
        prompt: str,
        cached_tokens: int,
    ) -> str:
        """Register that a node has cached KV state for a prompt prefix."""
        prefix_hash = self._hash_prefix(prompt, cached_tokens)

        # Evict old entries for this node if at capacity
        if self._node_entry_count[node_id] >= MAX_CACHE_ENTRIES_PER_NODE:
            self._evict_oldest(node_id)

        entry = CacheEntry(
            prefix_hash=prefix_hash,
            node_id=node_id,
            token_count=cached_tokens,
            created_at=time.time(),
            last_accessed=time.time(),
        )

        self._entries[prefix_hash].append(entry)
        self._node_entry_count[node_id] += 1

        return prefix_hash

    def lookup(self, prompt: str, min_tokens: int = 0) -> list[CacheEntry]:
        """
        Find nodes with cached KV state for a prompt.

        Checks progressively shorter prefixes to find partial matches.
        Returns entries sorted by token_count descending (most cached first).
        """
        now = time.time()
        results = []

        # Try exact and progressively shorter prefixes
        prompt_tokens = prompt.split()
        for length in range(len(prompt_tokens), min_tokens - 1, -max(1, len(prompt_tokens) // 10)):
            prefix = " ".join(prompt_tokens[:length])
            prefix_hash = self._hash_prefix(prefix, length)

            if prefix_hash in self._entries:
                entries = self._entries[prefix_hash]
                for entry in entries:
                    if not entry.is_expired and entry.token_count >= min_tokens:
                        entry.last_accessed = now
                        entry.hit_count += 1
                        results.append(entry)

                if results:
                    break  # found matches at this prefix length

        # Sort by token count descending (most cached = best match)
        results.sort(key=lambda e: e.token_count, reverse=True)
        return results

    def evict_node(self, node_id: str) -> int:
        """Remove all cache entries for a node (node went offline)."""
        removed = 0
        for prefix_hash in list(self._entries.keys()):
            before = len(self._entries[prefix_hash])
            self._entries[prefix_hash] = [
                e for e in self._entries[prefix_hash] if e.node_id != node_id
            ]
            removed += before - len(self._entries[prefix_hash])
            if not self._entries[prefix_hash]:
                del self._entries[prefix_hash]

        self._node_entry_count.pop(node_id, None)
        return removed

    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        removed = 0
        for prefix_hash in list(self._entries.keys()):
            before = len(self._entries[prefix_hash])
            self._entries[prefix_hash] = [
                e for e in self._entries[prefix_hash] if not e.is_expired
            ]
            removed += before - len(self._entries[prefix_hash])
            if not self._entries[prefix_hash]:
                del self._entries[prefix_hash]

        # Recalculate node counts
        self._node_entry_count.clear()
        for entries in self._entries.values():
            for e in entries:
                self._node_entry_count[e.node_id] += 1

        return removed

    def get_stats(self) -> dict:
        """Get cache index statistics."""
        all_entries = [e for entries in self._entries.values() for e in entries]
        return {
            "total_entries": len(all_entries),
            "unique_prefixes": len(self._entries),
            "nodes_with_cache": len(self._node_entry_count),
            "expired_entries": sum(1 for e in all_entries if e.is_expired),
            "avg_cached_tokens": (
                sum(e.token_count for e in all_entries) / len(all_entries)
                if all_entries else 0
            ),
            "total_hits": sum(e.hit_count for e in all_entries),
        }

    def _hash_prefix(self, text: str, token_count: int) -> str:
        """Hash a prompt prefix for cache lookup."""
        data = f"{text}:{token_count}".encode()
        return hashlib.sha256(data).hexdigest()[:PREFIX_HASH_LENGTH * 2]

    def _evict_oldest(self, node_id: str) -> None:
        """Evict the oldest entry for a node."""
        oldest_entry = None
        oldest_hash = None

        for prefix_hash, entries in self._entries.items():
            for entry in entries:
                if entry.node_id == node_id:
                    if oldest_entry is None or entry.last_accessed < oldest_entry.last_accessed:
                        oldest_entry = entry
                        oldest_hash = prefix_hash

        if oldest_entry and oldest_hash:
            self._entries[oldest_hash].remove(oldest_entry)
            if not self._entries[oldest_hash]:
                del self._entries[oldest_hash]
            self._node_entry_count[node_id] -= 1


class KVCacheAwareRouter:
    """
    Routes inference requests with KV-cache affinity.

    Combines cache awareness with load balancing:
    1. Check cache index for matching prefix
    2. If hit: route to node with longest cached prefix
    3. If miss: route to least-loaded node
    4. After response: register new cache entry

    This naturally handles multi-turn conversations:
    - Turn 1: cache miss → least loaded node → register cache
    - Turn 2: cache hit on Turn 1's prefix → same node → fast TTFT
    - Turn 3: cache hit on Turn 1+2's prefix → same node → faster TTFT
    """

    def __init__(self):
        self.cache_index = KVCacheIndex()
        self._node_loads: dict[str, float] = {}  # node_id → load (0.0-1.0)

    def update_node_load(self, node_id: str, load: float) -> None:
        """Update a node's current load factor."""
        self._node_loads[node_id] = max(0.0, min(1.0, load))

    def route(
        self,
        prompt: str,
        available_nodes: list[str],
    ) -> RoutingDecision:
        """
        Route an inference request to the best node.

        Args:
            prompt: The full prompt text
            available_nodes: List of healthy node IDs

        Returns:
            RoutingDecision with selected node and reasoning
        """
        if not available_nodes:
            return RoutingDecision(
                node_id="local",
                reason="fallback",
            )

        # 1. Check cache
        cache_hits = self.cache_index.lookup(prompt, min_tokens=10)
        valid_hits = [
            h for h in cache_hits
            if h.node_id in available_nodes
        ]

        if valid_hits:
            best_hit = valid_hits[0]  # already sorted by token_count desc
            node_load = self._node_loads.get(best_hit.node_id, 0.5)

            # Only use cache hit if node isn't overloaded
            if node_load < 0.9:
                # Estimate prefill savings: ~1ms per 100 tokens cached
                savings_ms = best_hit.token_count * 0.01
                return RoutingDecision(
                    node_id=best_hit.node_id,
                    reason="cache_hit",
                    cache_tokens=best_hit.token_count,
                    estimated_prefill_savings_ms=savings_ms,
                )

        # 2. No cache hit (or cached node overloaded) → load balance
        best_node = min(
            available_nodes,
            key=lambda n: self._node_loads.get(n, 0.5),
        )
        return RoutingDecision(
            node_id=best_node,
            reason="load_balance",
        )

    def register_completion(
        self,
        node_id: str,
        prompt: str,
        total_tokens: int,
    ) -> None:
        """Register that a node completed inference (for cache tracking)."""
        self.cache_index.register_cache(node_id, prompt, total_tokens)

    def get_routing_stats(self) -> dict:
        """Get routing statistics."""
        return {
            "cache_index": self.cache_index.get_stats(),
            "tracked_nodes": len(self._node_loads),
            "avg_load": (
                sum(self._node_loads.values()) / len(self._node_loads)
                if self._node_loads else 0
            ),
        }
