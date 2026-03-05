"""Redis advanced — Streams, pub/sub patterns, Lua scripting, RediSearch, probabilistic data structures, caching strategies."""

PAIRS = [
    (
        "databases/redis-streams",
        "Show Redis Streams for event processing: XADD, consumer groups, XREADGROUP, acknowledgment, claim/recover, and stream trimming.",
        '''Redis Streams for reliable event processing with consumer groups:

```python
import redis
import json
import time
import signal
import logging
from dataclasses import dataclass, field
from typing import Callable
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for a Redis Stream consumer."""
    stream: str
    group: str
    consumer: str
    batch_size: int = 10
    block_ms: int = 5000         # block for 5s waiting for messages
    max_retries: int = 3
    claim_min_idle_ms: int = 60000  # reclaim after 60s idle
    max_stream_length: int = 100000  # trim stream to this size


class RedisStreamProcessor:
    """Reliable Redis Stream consumer with consumer groups,
    dead-letter handling, and automatic recovery of stuck messages."""

    def __init__(self, redis_url: str, config: StreamConfig):
        self.r = redis.from_url(redis_url, decode_responses=True)
        self.config = config
        self._running = False
        self._ensure_group()

    def _ensure_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self.r.xgroup_create(
                self.config.stream,
                self.config.group,
                id="0",          # start from beginning
                mkstream=True    # create stream if missing
            )
            logger.info(f"Created group '{self.config.group}' "
                        f"on stream '{self.config.stream}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            # Group already exists — that's fine

    def produce(self, events: list[dict], max_len: int | None = None):
        """Publish events to the stream with automatic trimming."""
        pipe = self.r.pipeline()
        for event in events:
            pipe.xadd(
                self.config.stream,
                event,
                maxlen=max_len or self.config.max_stream_length,
                approximate=True  # ~ faster than exact trim
            )
        results = pipe.execute()
        return results  # list of message IDs

    def consume(self, handler: Callable[[str, dict], bool]):
        """Main consumer loop: read new messages + reclaim stuck ones."""
        self._running = True
        signal.signal(signal.SIGTERM, lambda *_: self.stop())

        logger.info(f"Consumer '{self.config.consumer}' starting on "
                     f"'{self.config.stream}/{self.config.group}'")

        while self._running:
            # 1. Reclaim stuck messages from other consumers
            self._claim_pending(handler)

            # 2. Read new messages
            try:
                messages = self.r.xreadgroup(
                    groupname=self.config.group,
                    consumername=self.config.consumer,
                    streams={self.config.stream: ">"},  # ">" = only new
                    count=self.config.batch_size,
                    block=self.config.block_ms,
                )
            except redis.ConnectionError:
                logger.warning("Connection lost, reconnecting...")
                time.sleep(1)
                continue

            if not messages:
                continue

            for stream_name, stream_messages in messages:
                for msg_id, fields in stream_messages:
                    self._process_message(msg_id, fields, handler)

    def _process_message(self, msg_id: str, fields: dict,
                         handler: Callable):
        """Process a single message with retry tracking."""
        try:
            success = handler(msg_id, fields)
            if success:
                self.r.xack(
                    self.config.stream,
                    self.config.group,
                    msg_id
                )
                logger.debug(f"ACK {msg_id}")
            else:
                logger.warning(f"Handler returned False for {msg_id}")
        except Exception as e:
            logger.error(f"Error processing {msg_id}: {e}")
            # Message stays in PEL; will be reclaimed later

    def _claim_pending(self, handler: Callable):
        """Reclaim messages stuck in other consumers' PEL."""
        try:
            # Find pending messages idle > threshold
            pending = self.r.xpending_range(
                self.config.stream,
                self.config.group,
                min="-",
                max="+",
                count=self.config.batch_size,
            )
        except redis.ResponseError:
            return

        stale_ids = []
        for entry in pending:
            idle_ms = entry.get("time_since_delivered", 0)
            delivery_count = entry.get("times_delivered", 0)

            if idle_ms > self.config.claim_min_idle_ms:
                if delivery_count > self.config.max_retries:
                    # Dead letter: too many retries
                    self._dead_letter(entry["message_id"])
                else:
                    stale_ids.append(entry["message_id"])

        if stale_ids:
            # Claim ownership of stale messages
            claimed = self.r.xclaim(
                self.config.stream,
                self.config.group,
                self.config.consumer,
                min_idle_time=self.config.claim_min_idle_ms,
                message_ids=stale_ids,
            )
            for msg_id, fields in claimed:
                logger.info(f"Reclaimed stale message {msg_id}")
                self._process_message(msg_id, fields, handler)

    def _dead_letter(self, msg_id: str):
        """Move permanently failed messages to dead letter stream."""
        # Read the original message
        messages = self.r.xrange(
            self.config.stream, min=msg_id, max=msg_id
        )
        if messages:
            _, fields = messages[0]
            self.r.xadd(
                f"{self.config.stream}:deadletter",
                {**fields, "original_id": msg_id,
                 "failed_at": str(time.time())},
                maxlen=10000,
            )
        # Acknowledge to remove from PEL
        self.r.xack(self.config.stream, self.config.group, msg_id)
        logger.warning(f"Dead-lettered message {msg_id}")

    def stop(self):
        self._running = False

    def stream_info(self) -> dict:
        """Get stream and consumer group metrics."""
        info = self.r.xinfo_stream(self.config.stream)
        groups = self.r.xinfo_groups(self.config.stream)
        return {
            "length": info["length"],
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "groups": [
                {
                    "name": g["name"],
                    "consumers": g["consumers"],
                    "pending": g["pending"],
                    "last_delivered": g["last-delivered-id"],
                }
                for g in groups
            ],
        }


# === Usage ===
config = StreamConfig(
    stream="orders:events",
    group="order-processors",
    consumer="worker-1",
    batch_size=50,
)

processor = RedisStreamProcessor("redis://localhost:6379/0", config)

# Produce events
processor.produce([
    {"event": "order_created", "order_id": "ord_123",
     "amount": "99.99", "user_id": "usr_456"},
    {"event": "payment_received", "order_id": "ord_123",
     "amount": "99.99", "method": "stripe"},
])

# Consume with handler
def handle_order_event(msg_id: str, fields: dict) -> bool:
    event_type = fields.get("event")
    order_id = fields.get("order_id")
    logger.info(f"Processing {event_type} for {order_id}")
    # ... business logic ...
    return True  # return False to skip ACK (retry later)

processor.consume(handle_order_event)
```

Key patterns:
1. **Consumer groups** -- multiple consumers share the workload; each message delivered to exactly one consumer in the group
2. **XCLAIM recovery** -- reclaim messages stuck in another consumer's PEL after idle timeout; prevents message loss on consumer crashes
3. **Dead letter stream** -- after max retries, move to `stream:deadletter` for manual inspection; always ACK to free the PEL
4. **Approximate trimming** -- `MAXLEN ~ N` is faster than exact; Redis may keep slightly more than N entries
5. **Block reads** -- `XREADGROUP ... BLOCK 5000` avoids busy-polling; returns immediately when messages arrive'''
    ),
    (
        "databases/redis-lua-scripting",
        "Show Redis Lua scripting for atomic operations: rate limiting, distributed locks, inventory management, and leaderboard operations.",
        '''Redis Lua scripting for atomic multi-key operations:

```python
import redis
import time
import hashlib
from typing import Optional


class RedisAtomicOps:
    """Atomic Redis operations using server-side Lua scripts.

    Lua scripts execute atomically on Redis — no other command
    runs between script steps. This replaces WATCH/MULTI
    for complex multi-key transactions.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.r = redis.from_url(redis_url, decode_responses=True)
        self._register_scripts()

    def _register_scripts(self):
        """Pre-register Lua scripts for repeated use (cached by SHA)."""

        # === 1. Sliding window rate limiter ===
        # Atomic: check + record + expire in one round trip
        self._rate_limit_script = self.r.register_script("""
            local key = KEYS[1]
            local window_ms = tonumber(ARGV[1])
            local max_requests = tonumber(ARGV[2])
            local now_ms = tonumber(ARGV[3])
            local window_start = now_ms - window_ms

            -- Remove entries outside the window
            redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

            -- Count current requests in window
            local current = redis.call('ZCARD', key)

            if current < max_requests then
                -- Add this request with timestamp as score
                redis.call('ZADD', key, now_ms, now_ms .. ':' .. math.random(1000000))
                redis.call('PEXPIRE', key, window_ms)
                -- Return: allowed=1, remaining, reset_ms
                return {1, max_requests - current - 1, window_ms}
            else
                -- Rate limited: find when oldest entry expires
                local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                local retry_after = 0
                if #oldest > 0 then
                    retry_after = tonumber(oldest[2]) + window_ms - now_ms
                end
                return {0, 0, retry_after}
            end
        """)

        # === 2. Distributed lock with fencing token ===
        self._acquire_lock_script = self.r.register_script("""
            local lock_key = KEYS[1]
            local token_key = KEYS[2]
            local owner = ARGV[1]
            local ttl_ms = tonumber(ARGV[2])

            -- Check if lock is free
            local current_owner = redis.call('GET', lock_key)
            if current_owner == false or current_owner == owner then
                -- Acquire lock
                redis.call('SET', lock_key, owner, 'PX', ttl_ms)
                -- Increment fencing token (monotonic)
                local token = redis.call('INCR', token_key)
                return {1, token}
            end
            return {0, 0}
        """)

        self._release_lock_script = self.r.register_script("""
            local lock_key = KEYS[1]
            local owner = ARGV[1]

            if redis.call('GET', lock_key) == owner then
                redis.call('DEL', lock_key)
                return 1
            end
            return 0
        """)

        # === 3. Atomic inventory reservation ===
        self._reserve_inventory_script = self.r.register_script("""
            local inventory_key = KEYS[1]
            local reservation_key = KEYS[2]
            local order_id = ARGV[1]
            local quantity = tonumber(ARGV[2])
            local ttl_seconds = tonumber(ARGV[3])

            -- Check available stock
            local current = tonumber(redis.call('GET', inventory_key) or '0')
            if current < quantity then
                return {0, current}  -- insufficient stock
            end

            -- Atomically decrement and create reservation
            local remaining = redis.call('DECRBY', inventory_key, quantity)
            redis.call('HSET', reservation_key, order_id,
                       cjson.encode({qty=quantity, time=ARGV[4]}))
            redis.call('EXPIRE', reservation_key, ttl_seconds)

            return {1, remaining}
        """)

        # === 4. Leaderboard with rank change tracking ===
        self._update_leaderboard_script = self.r.register_script("""
            local board_key = KEYS[1]
            local history_key = KEYS[2]
            local member = ARGV[1]
            local score_delta = tonumber(ARGV[2])

            -- Get old score and rank
            local old_score = tonumber(
                redis.call('ZSCORE', board_key, member) or '0'
            )
            local old_rank = redis.call('ZREVRANK', board_key, member)

            -- Update score
            local new_score = redis.call(
                'ZINCRBY', board_key, score_delta, member
            )
            local new_rank = redis.call('ZREVRANK', board_key, member)

            -- Record rank change history
            local rank_change = -1
            if old_rank ~= false then
                rank_change = old_rank - new_rank  -- positive = moved up
            end

            redis.call('LPUSH', history_key,
                cjson.encode({
                    member = member,
                    old_rank = old_rank,
                    new_rank = new_rank,
                    rank_change = rank_change,
                    old_score = old_score,
                    new_score = tonumber(new_score),
                    timestamp = ARGV[3]
                })
            )
            redis.call('LTRIM', history_key, 0, 999)  -- keep last 1000

            return {tonumber(new_score), new_rank, rank_change}
        """)

    # === Public API ===

    def rate_limit(self, key: str, max_requests: int = 100,
                   window_seconds: int = 60) -> dict:
        """Sliding window rate limiter. Returns allow/deny + metadata."""
        now_ms = int(time.time() * 1000)
        result = self._rate_limit_script(
            keys=[f"ratelimit:{key}"],
            args=[window_seconds * 1000, max_requests, now_ms],
        )
        return {
            "allowed": bool(result[0]),
            "remaining": result[1],
            "retry_after_ms": result[2] if not result[0] else 0,
        }

    def acquire_lock(self, resource: str, owner: str,
                     ttl_ms: int = 10000) -> Optional[int]:
        """Acquire distributed lock with fencing token."""
        result = self._acquire_lock_script(
            keys=[f"lock:{resource}", f"lock:token:{resource}"],
            args=[owner, ttl_ms],
        )
        if result[0]:
            return result[1]  # fencing token
        return None

    def release_lock(self, resource: str, owner: str) -> bool:
        """Release lock only if we still own it."""
        return bool(self._release_lock_script(
            keys=[f"lock:{resource}"],
            args=[owner],
        ))

    def reserve_inventory(self, sku: str, order_id: str,
                          quantity: int, hold_seconds: int = 600) -> dict:
        """Atomically reserve inventory for an order."""
        result = self._reserve_inventory_script(
            keys=[f"inventory:{sku}", f"reservations:{sku}"],
            args=[order_id, quantity, hold_seconds, str(time.time())],
        )
        return {
            "reserved": bool(result[0]),
            "remaining_stock": result[1],
        }

    def update_score(self, board: str, member: str,
                     delta: float) -> dict:
        """Update leaderboard score and track rank changes."""
        result = self._update_leaderboard_script(
            keys=[f"leaderboard:{board}", f"leaderboard:{board}:history"],
            args=[member, delta, str(time.time())],
        )
        return {
            "new_score": result[0],
            "new_rank": result[1] + 1,  # 0-indexed -> 1-indexed
            "rank_change": result[2],
        }


# === Usage ===
ops = RedisAtomicOps("redis://localhost:6379/0")

# Rate limiting
for _ in range(5):
    result = ops.rate_limit("user:123:api", max_requests=3, window_seconds=60)
    print(f"Allowed: {result['allowed']}, Remaining: {result['remaining']}")

# Distributed lock
token = ops.acquire_lock("payment:ord_456", owner="worker-1", ttl_ms=5000)
if token:
    print(f"Lock acquired, fencing token: {token}")
    # ... critical section ...
    ops.release_lock("payment:ord_456", owner="worker-1")

# Inventory
print(ops.reserve_inventory("SKU-WIDGET-001", "ord_789", quantity=2))

# Leaderboard
print(ops.update_score("weekly", "player_alice", delta=150))
```

Key patterns:
1. **Atomic execution** -- Lua scripts run atomically on Redis; no race conditions between ZCARD and ZADD in rate limiter
2. **Script caching** -- `register_script()` sends script once via EVALSHA; subsequent calls use the SHA hash (no retransmission)
3. **Fencing tokens** -- monotonically increasing token from INCR prevents stale lock holders from performing writes after lock expiry
4. **cjson in Lua** -- `cjson.encode/decode` handles structured data inside scripts; use for complex reservation records
5. **Owner-checked release** -- always verify lock ownership before DEL; prevents releasing a lock that was already expired and reacquired'''
    ),
    (
        "databases/redis-search-module",
        "Demonstrate RediSearch (Redis Search) for full-text search: index creation, FT.SEARCH queries, aggregations, auto-complete, and vector similarity search.",
        '''RediSearch for full-text and vector similarity search:

```python
import redis
import numpy as np
import json
from redis.commands.search.field import (
    TextField, NumericField, TagField, VectorField
)
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query, NumericFilter
from redis.commands.search.aggregation import AggregateRequest, Asc, Desc
from redis.commands.search import reducers


class ProductSearchEngine:
    """Full-text + vector hybrid search engine using RediSearch."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.r = redis.from_url(redis_url, decode_responses=True)
        self.index_name = "idx:products"
        self.vector_dim = 384  # sentence-transformer embedding size
        self._create_index()

    def _create_index(self):
        """Create a RediSearch index with text, numeric, tag, and vector fields."""
        try:
            self.r.ft(self.index_name).dropindex(delete_documents=False)
        except redis.ResponseError:
            pass  # index doesn't exist yet

        schema = (
            TextField("name", weight=5.0, sortable=True),
            TextField("description", weight=2.0),
            TextField("brand", weight=3.0, sortable=True),
            NumericField("price", sortable=True),
            NumericField("rating", sortable=True),
            NumericField("review_count", sortable=True),
            TagField("categories", separator="|"),
            TagField("tags", separator="|"),
            TagField("availability"),
            VectorField(
                "embedding",
                "HNSW",  # algorithm: HNSW or FLAT
                {
                    "TYPE": "FLOAT32",
                    "DIM": self.vector_dim,
                    "DISTANCE_METRIC": "COSINE",
                    "INITIAL_CAP": 10000,
                    "M": 16,                  # HNSW connections per node
                    "EF_CONSTRUCTION": 200,    # build-time search width
                    "EF_RUNTIME": 10,          # query-time search width
                },
            ),
        )

        definition = IndexDefinition(
            prefix=["product:"],
            index_type=IndexType.HASH,
        )

        self.r.ft(self.index_name).create_index(
            schema, definition=definition
        )

    def index_product(self, product_id: str, data: dict,
                      embedding: list[float]):
        """Index a product with full-text fields and vector embedding."""
        key = f"product:{product_id}"
        self.r.hset(key, mapping={
            "name": data["name"],
            "description": data["description"],
            "brand": data["brand"],
            "price": data["price"],
            "rating": data.get("rating", 0),
            "review_count": data.get("review_count", 0),
            "categories": "|".join(data.get("categories", [])),
            "tags": "|".join(data.get("tags", [])),
            "availability": data.get("availability", "in_stock"),
            "embedding": np.array(
                embedding, dtype=np.float32
            ).tobytes(),
        })

    def text_search(self, query_text: str, filters: dict = None,
                    page: int = 0, page_size: int = 20) -> dict:
        """Full-text BM25 search with filters and faceted results."""
        # Build query string
        parts = [query_text]

        if filters:
            if "category" in filters:
                parts.append(
                    f"@categories:{{{filters['category']}}}"
                )
            if "brand" in filters:
                parts.append(f"@brand:({filters['brand']})")
            if "min_rating" in filters:
                parts.append(
                    f"@rating:[{filters['min_rating']} +inf]"
                )
            if "availability" in filters:
                parts.append(
                    f"@availability:{{{filters['availability']}}}"
                )

        q = (
            Query(" ".join(parts))
            .with_scores()
            .highlight(fields=["name", "description"],
                       tags=["<b>", "</b>"])
            .summarize(fields=["description"], frags=2, len=80)
            .paging(page * page_size, page_size)
            .return_fields("name", "brand", "price", "rating",
                           "categories", "description")
        )

        if filters and "price_max" in filters:
            q.add_filter(
                NumericFilter("price", 0, filters["price_max"])
            )

        results = self.r.ft(self.index_name).search(q)

        return {
            "total": results.total,
            "page": page,
            "results": [
                {
                    "id": doc.id.replace("product:", ""),
                    "name": doc.name,
                    "brand": doc.brand,
                    "price": float(doc.price),
                    "rating": float(doc.rating),
                    "score": doc.score,
                    "description": doc.description,
                }
                for doc in results.docs
            ],
        }

    def vector_search(self, query_embedding: list[float],
                      top_k: int = 10,
                      category_filter: str = None) -> list[dict]:
        """Pure vector similarity search (KNN)."""
        query_vec = np.array(
            query_embedding, dtype=np.float32
        ).tobytes()

        filter_clause = "*"
        if category_filter:
            filter_clause = f"@categories:{{{category_filter}}}"

        q = (
            Query(
                f"({filter_clause})=>"
                f"[KNN {top_k} @embedding $vec AS similarity]"
            )
            .sort_by("similarity")
            .return_fields("name", "brand", "price", "similarity")
            .dialect(2)
        )

        results = self.r.ft(self.index_name).search(
            q, query_params={"vec": query_vec}
        )

        return [
            {
                "id": doc.id.replace("product:", ""),
                "name": doc.name,
                "brand": doc.brand,
                "price": float(doc.price),
                "similarity": float(doc.similarity),
            }
            for doc in results.docs
        ]

    def hybrid_search(self, query_text: str,
                      query_embedding: list[float],
                      top_k: int = 10,
                      text_weight: float = 0.5) -> list[dict]:
        """Hybrid search: combine BM25 text score + vector similarity."""
        query_vec = np.array(
            query_embedding, dtype=np.float32
        ).tobytes()

        # RediSearch hybrid query with vector + text scoring
        q = (
            Query(
                f"({query_text})=>"
                f"[KNN {top_k * 2} @embedding $vec AS vec_score]"
            )
            .with_scores()
            .return_fields("name", "brand", "price", "rating",
                           "vec_score")
            .sort_by("vec_score")
            .dialect(2)
        )

        results = self.r.ft(self.index_name).search(
            q, query_params={"vec": query_vec}
        )

        # Merge BM25 score + vector score with weights
        hybrid_results = []
        for doc in results.docs:
            bm25_score = float(doc.score) if hasattr(doc, "score") else 0
            vec_score = 1.0 - float(doc.vec_score)  # cosine -> similarity
            combined = (
                text_weight * bm25_score +
                (1 - text_weight) * vec_score
            )
            hybrid_results.append({
                "id": doc.id.replace("product:", ""),
                "name": doc.name,
                "brand": doc.brand,
                "price": float(doc.price),
                "bm25_score": round(bm25_score, 4),
                "vector_similarity": round(vec_score, 4),
                "hybrid_score": round(combined, 4),
            })

        hybrid_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return hybrid_results[:top_k]

    def aggregate_facets(self, query_text: str) -> dict:
        """Get faceted aggregations for search results."""
        req = (
            AggregateRequest(query_text)
            .group_by("@brand",
                       reducers.count().alias("count"),
                       reducers.avg("@price").alias("avg_price"))
            .sort_by(Desc("@count"))
            .limit(0, 20)
        )
        brand_facets = self.r.ft(self.index_name).aggregate(req)

        req2 = (
            AggregateRequest(query_text)
            .group_by("@categories",
                       reducers.count().alias("count"))
            .sort_by(Desc("@count"))
            .limit(0, 10)
        )
        cat_facets = self.r.ft(self.index_name).aggregate(req2)

        return {
            "brands": [
                {"brand": r[1], "count": int(r[3]),
                 "avg_price": round(float(r[5]), 2)}
                for r in brand_facets.rows
            ],
            "categories": [
                {"category": r[1], "count": int(r[3])}
                for r in cat_facets.rows
            ],
        }


# === Usage ===
engine = ProductSearchEngine()

# Index products
engine.index_product("widget-001", {
    "name": "Premium Smart Widget Pro",
    "description": "Advanced IoT widget with voice control and automation",
    "brand": "WidgetCo",
    "price": 49.99,
    "rating": 4.5,
    "review_count": 234,
    "categories": ["electronics", "smart-home"],
    "tags": ["iot", "voice-control", "wifi"],
    "availability": "in_stock",
}, embedding=[0.1] * 384)  # placeholder embedding

# Full-text search with filters
results = engine.text_search(
    "smart widget voice control",
    filters={"category": "electronics", "min_rating": 4.0},
)

# Vector similarity search
similar = engine.vector_search(
    query_embedding=[0.1] * 384, top_k=5
)

# Hybrid search
hybrid = engine.hybrid_search(
    "smart home automation", [0.1] * 384, text_weight=0.6
)
```

Key patterns:
1. **HNSW vector index** -- `M=16, EF_CONSTRUCTION=200` balances recall and build speed; tune `EF_RUNTIME` per query for speed/accuracy tradeoff
2. **Hybrid query syntax** -- `(text query)=>[KNN K @field $vec]` combines BM25 text matching with vector KNN in a single query
3. **Field weights** -- `TextField("name", weight=5.0)` boosts name matches 5x over default; critical for ranking relevance
4. **Tag fields for filters** -- `TagField` with pipe separator enables exact-match faceted filtering; much faster than text matching for categories
5. **Aggregation pipeline** -- `AggregateRequest` provides GROUP BY, SORT, REDUCE operations server-side; builds facet counts without fetching all documents'''
    ),
    (
        "databases/redis-probabilistic-structures",
        "Show Redis probabilistic data structures: HyperLogLog for cardinality, Bloom filters for membership, Count-Min Sketch for frequency, and Top-K.",
        '''Redis probabilistic data structures for massive-scale analytics:

```python
import redis
import time
import json
from datetime import datetime, timedelta


class ProbabilisticAnalytics:
    """Redis probabilistic data structures for high-volume analytics.

    These structures trade exact accuracy for massive memory savings:
    - HyperLogLog: ~12KB per counter regardless of cardinality
    - Bloom filter: ~1 byte per element at 1% false positive rate
    - Count-Min Sketch: fixed memory for frequency estimation
    - Top-K: constant memory for heavy hitters
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.r = redis.from_url(redis_url, decode_responses=True)

    # === HyperLogLog: unique count estimation ===

    def track_unique_visitor(self, page: str, visitor_id: str,
                            date: str = None):
        """Track unique visitors per page per day. ~12KB per counter."""
        date = date or datetime.now().strftime("%Y-%m-%d")
        # Each key stores unique visitors for one page on one day
        key = f"hll:visitors:{page}:{date}"
        self.r.pfadd(key, visitor_id)
        self.r.expire(key, 86400 * 90)  # keep 90 days

    def get_unique_count(self, page: str, date: str) -> int:
        """Get estimated unique visitor count (error < 0.81%)."""
        return self.r.pfcount(f"hll:visitors:{page}:{date}")

    def get_unique_count_range(self, page: str, start_date: str,
                               end_date: str) -> int:
        """Merge HLLs across dates for period-level unique count."""
        keys = []
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        while current <= end:
            keys.append(
                f"hll:visitors:{page}:{current.strftime('%Y-%m-%d')}"
            )
            current += timedelta(days=1)

        if not keys:
            return 0

        # PFMERGE creates a merged HLL; PFCOUNT on multiple keys also works
        merge_key = f"hll:visitors:{page}:merged_temp"
        self.r.pfmerge(merge_key, *keys)
        count = self.r.pfcount(merge_key)
        self.r.delete(merge_key)
        return count

    def site_wide_uniques(self, date: str) -> int:
        """Count site-wide unique visitors by merging all page HLLs."""
        keys = list(self.r.scan_iter(
            match=f"hll:visitors:*:{date}", count=100
        ))
        if not keys:
            return 0
        return self.r.pfcount(*keys)

    # === Bloom Filter: membership testing ===

    def setup_bloom_filter(self, name: str, capacity: int = 1_000_000,
                           error_rate: float = 0.01):
        """Create a Bloom filter with specified capacity and error rate."""
        try:
            self.r.execute_command(
                "BF.RESERVE", f"bloom:{name}",
                error_rate, capacity,
                "NONSCALING"  # fixed size, better performance
            )
        except redis.ResponseError as e:
            if "item exists" not in str(e).lower():
                raise

    def bloom_add(self, name: str, item: str) -> bool:
        """Add item to Bloom filter. Returns True if newly added."""
        return bool(
            self.r.execute_command("BF.ADD", f"bloom:{name}", item)
        )

    def bloom_add_batch(self, name: str, items: list[str]) -> list[bool]:
        """Bulk add items to Bloom filter."""
        return [
            bool(x) for x in
            self.r.execute_command(
                "BF.MADD", f"bloom:{name}", *items
            )
        ]

    def bloom_exists(self, name: str, item: str) -> bool:
        """Check if item might exist. False = definitely not present.
        True = probably present (false positive rate = error_rate)."""
        return bool(
            self.r.execute_command("BF.EXISTS", f"bloom:{name}", item)
        )

    def bloom_exists_batch(self, name: str,
                           items: list[str]) -> list[bool]:
        """Bulk membership check."""
        return [
            bool(x) for x in
            self.r.execute_command(
                "BF.MEXISTS", f"bloom:{name}", *items
            )
        ]

    # === Count-Min Sketch: frequency estimation ===

    def setup_cms(self, name: str, width: int = 2000,
                  depth: int = 7):
        """Create Count-Min Sketch. width*depth = memory footprint.
        Error bound = e/width, probability = (1/2)^depth."""
        try:
            self.r.execute_command(
                "CMS.INITBYDIM", f"cms:{name}", width, depth
            )
        except redis.ResponseError as e:
            if "item exists" not in str(e).lower():
                raise

    def cms_increment(self, name: str,
                      items_counts: dict[str, int]):
        """Increment frequency counts for multiple items."""
        args = []
        for item, count in items_counts.items():
            args.extend([item, count])
        self.r.execute_command(
            "CMS.INCRBY", f"cms:{name}", *args
        )

    def cms_query(self, name: str,
                  items: list[str]) -> dict[str, int]:
        """Query estimated frequencies. Always >= true count."""
        counts = self.r.execute_command(
            "CMS.QUERY", f"cms:{name}", *items
        )
        return dict(zip(items, counts))

    # === Top-K: heavy hitters ===

    def setup_topk(self, name: str, k: int = 100,
                   width: int = 2000, depth: int = 7,
                   decay: float = 0.9):
        """Create Top-K structure for finding most frequent items."""
        try:
            self.r.execute_command(
                "TOPK.RESERVE", f"topk:{name}",
                k, width, depth, decay
            )
        except redis.ResponseError as e:
            if "item exists" not in str(e).lower():
                raise

    def topk_add(self, name: str, items: list[str]) -> list:
        """Add items to Top-K. Returns evicted items (or None)."""
        return self.r.execute_command(
            "TOPK.ADD", f"topk:{name}", *items
        )

    def topk_list(self, name: str) -> list[dict]:
        """Get current top-K items with estimated counts."""
        items = self.r.execute_command(
            "TOPK.LIST", f"topk:{name}", "WITHCOUNT"
        )
        results = []
        for i in range(0, len(items), 2):
            results.append({
                "item": items[i],
                "estimated_count": int(items[i + 1])
            })
        return sorted(results, key=lambda x: x["estimated_count"],
                       reverse=True)


# === Usage examples ===
analytics = ProbabilisticAnalytics()

# --- HyperLogLog: unique visitor counting ---
# Track 1M visitors using only ~12KB per page per day
for i in range(1_000_000):
    analytics.track_unique_visitor("/home", f"user_{i}")
print(f"Unique visitors: {analytics.get_unique_count('/home', '2025-12-15')}")
# Result: ~1,000,000 (within 0.81% error)

# Weekly uniques (deduplicated across days)
weekly = analytics.get_unique_count_range(
    "/home", "2025-12-09", "2025-12-15"
)

# --- Bloom filter: "have we seen this before?" ---
analytics.setup_bloom_filter("seen_emails", capacity=10_000_000)
analytics.bloom_add("seen_emails", "user@example.com")
print(analytics.bloom_exists("seen_emails", "user@example.com"))  # True
print(analytics.bloom_exists("seen_emails", "new@example.com"))   # False (certain)

# --- Count-Min Sketch: frequency estimation ---
analytics.setup_cms("page_views")
analytics.cms_increment("page_views", {
    "/home": 500, "/pricing": 200, "/docs": 800
})
print(analytics.cms_query("page_views", ["/home", "/pricing"]))
# {'/home': 500, '/pricing': 200}

# --- Top-K: trending items ---
analytics.setup_topk("trending_products", k=50)
analytics.topk_add("trending_products", ["widget-A", "widget-B", "widget-A"])
print(analytics.topk_list("trending_products"))
```

| Structure | Memory | Accuracy | Use Case |
|---|---|---|---|
| HyperLogLog | ~12KB fixed | 0.81% error | Unique visitor counts, cardinality |
| Bloom Filter | ~1 byte/element | No false negatives | Dedup, "seen before?" checks |
| Count-Min Sketch | width x depth | Over-estimates only | Frequency counting, rate limiting |
| Top-K | Fixed (k items) | Approximate | Trending items, heavy hitters |

Key patterns:
1. **HyperLogLog merge** -- PFMERGE combines multiple HLLs for time-range uniques; still only ~12KB after merging millions of entries
2. **Bloom filter guarantees** -- "definitely not" (no false negatives) is the valuable property; use for dedup, cache-aside existence checks
3. **CMS over-counting** -- Count-Min Sketch only over-estimates, never under-estimates; safe for rate limiting (errs on the side of caution)
4. **Top-K decay** -- decay factor (0.9) gradually reduces old counts, making the list recency-weighted; good for trending/hot items
5. **Memory vs. exact** -- a sorted set tracking 10M unique items uses ~500MB; HyperLogLog uses 12KB for the same cardinality estimate'''
    ),
    (
        "databases/redis-caching-strategies",
        "Show advanced Redis caching strategies: cache-aside, read-through, write-behind, cache stampede prevention, and multi-tier caching with TTL policies.",
        '''Advanced Redis caching patterns with stampede prevention:

```python
import redis
import json
import time
import hashlib
import logging
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    ttl_seconds: int = 300
    stale_ttl_seconds: int = 600     # serve stale for this long
    lock_timeout_ms: int = 5000
    early_refresh_pct: float = 0.8   # refresh at 80% of TTL


class SmartCache:
    """Production Redis cache with stampede prevention,
    stale-while-revalidate, and multi-tier support."""

    def __init__(self, redis_url: str, config: CacheConfig = None):
        self.r = redis.from_url(redis_url, decode_responses=True)
        self.config = config or CacheConfig()
        self._executor = ThreadPoolExecutor(max_workers=4)

    def _cache_key(self, namespace: str, key: str) -> str:
        """Generate consistent cache key."""
        return f"cache:{namespace}:{key}"

    def _lock_key(self, cache_key: str) -> str:
        return f"lock:{cache_key}"

    # === Pattern 1: Cache-aside with stampede prevention ===

    def get_or_compute(self, namespace: str, key: str,
                       compute_fn: Callable[[], Any],
                       ttl: int = None) -> Any:
        """Cache-aside with probabilistic early refresh (XFetch).

        Prevents thundering herd by having random requests refresh
        the cache slightly before TTL expires.
        """
        cache_key = self._cache_key(namespace, key)
        ttl = ttl or self.config.ttl_seconds

        # Try cache first
        pipe = self.r.pipeline()
        pipe.get(cache_key)
        pipe.ttl(cache_key)
        cached_value, remaining_ttl = pipe.execute()

        if cached_value is not None:
            # Probabilistic early refresh (XFetch algorithm)
            # As TTL approaches expiry, probability of refresh increases
            if remaining_ttl > 0:
                elapsed_pct = 1 - (remaining_ttl / ttl)
                if elapsed_pct > self.config.early_refresh_pct:
                    # Exponential probability of refresh
                    import random
                    gap = elapsed_pct - self.config.early_refresh_pct
                    probability = gap / (1 - self.config.early_refresh_pct)
                    if random.random() < probability:
                        # This request refreshes; others use cached value
                        self._background_refresh(
                            cache_key, compute_fn, ttl
                        )

            return json.loads(cached_value)

        # Cache miss: acquire lock to prevent stampede
        return self._fetch_with_lock(cache_key, compute_fn, ttl)

    def _fetch_with_lock(self, cache_key: str,
                         compute_fn: Callable, ttl: int) -> Any:
        """Single-flight cache population with lock."""
        lock_key = self._lock_key(cache_key)

        # Try to acquire computation lock
        acquired = self.r.set(
            lock_key, "1",
            nx=True,  # only if not exists
            px=self.config.lock_timeout_ms
        )

        if acquired:
            try:
                # We won the lock — compute the value
                value = compute_fn()
                # Store with both fresh TTL and stale fallback
                pipe = self.r.pipeline()
                pipe.set(cache_key, json.dumps(value), ex=ttl)
                pipe.set(
                    f"{cache_key}:stale",
                    json.dumps(value),
                    ex=self.config.stale_ttl_seconds
                )
                pipe.execute()
                return value
            finally:
                self.r.delete(lock_key)
        else:
            # Another request is computing; wait briefly then check
            time.sleep(0.1)
            cached = self.r.get(cache_key)
            if cached:
                return json.loads(cached)

            # Still nothing — try stale value
            stale = self.r.get(f"{cache_key}:stale")
            if stale:
                logger.info(f"Serving stale cache for {cache_key}")
                return json.loads(stale)

            # Last resort: compute ourselves (lock expired or failed)
            value = compute_fn()
            self.r.set(cache_key, json.dumps(value), ex=ttl)
            return value

    def _background_refresh(self, cache_key: str,
                            compute_fn: Callable, ttl: int):
        """Refresh cache in background thread."""
        def _refresh():
            try:
                value = compute_fn()
                pipe = self.r.pipeline()
                pipe.set(cache_key, json.dumps(value), ex=ttl)
                pipe.set(
                    f"{cache_key}:stale",
                    json.dumps(value),
                    ex=self.config.stale_ttl_seconds
                )
                pipe.execute()
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")

        self._executor.submit(_refresh)

    # === Pattern 2: Write-behind (write-back) cache ===

    def write_behind(self, namespace: str, key: str, value: Any,
                     ttl: int = None):
        """Write to cache immediately, persist to DB asynchronously.

        Uses a Redis Stream as a write-ahead log for durability.
        """
        cache_key = self._cache_key(namespace, key)
        ttl = ttl or self.config.ttl_seconds

        pipe = self.r.pipeline()
        # Update cache immediately
        pipe.set(cache_key, json.dumps(value), ex=ttl)
        # Append to write-behind stream for async DB persistence
        pipe.xadd("writebehind:queue", {
            "namespace": namespace,
            "key": key,
            "value": json.dumps(value),
            "timestamp": str(time.time()),
        }, maxlen=100000)
        pipe.execute()

    # === Pattern 3: Multi-tier cache (L1 local + L2 Redis) ===

    def cached(self, namespace: str, ttl: int = 300):
        """Decorator for multi-tier caching.

        L1: in-process dict (fastest, per-instance)
        L2: Redis (shared across instances)
        """
        l1_cache: dict[str, tuple[float, Any]] = {}
        l1_ttl = min(ttl, 30)  # L1 max 30 seconds

        def decorator(fn: Callable) -> Callable:
            @wraps(fn)
            def wrapper(*args, **kwargs):
                # Generate cache key from function args
                key_data = json.dumps(
                    {"args": args, "kwargs": kwargs},
                    sort_keys=True, default=str
                )
                key = hashlib.md5(key_data.encode()).hexdigest()

                # L1 check (in-process, no I/O)
                if key in l1_cache:
                    expires_at, value = l1_cache[key]
                    if time.time() < expires_at:
                        return value
                    del l1_cache[key]

                # L2 check (Redis)
                result = self.get_or_compute(
                    namespace, key,
                    lambda: fn(*args, **kwargs),
                    ttl=ttl
                )

                # Populate L1
                l1_cache[key] = (time.time() + l1_ttl, result)

                # Evict old L1 entries periodically
                if len(l1_cache) > 1000:
                    now = time.time()
                    expired = [
                        k for k, (exp, _) in l1_cache.items()
                        if now > exp
                    ]
                    for k in expired:
                        del l1_cache[k]

                return result
            return wrapper
        return decorator

    # === Pattern 4: Cache invalidation ===

    def invalidate(self, namespace: str, key: str):
        """Invalidate cache entry and its stale fallback."""
        cache_key = self._cache_key(namespace, key)
        self.r.delete(cache_key, f"{cache_key}:stale")

    def invalidate_pattern(self, namespace: str, pattern: str):
        """Invalidate all keys matching a pattern in a namespace."""
        full_pattern = self._cache_key(namespace, pattern)
        cursor = 0
        while True:
            cursor, keys = self.r.scan(
                cursor, match=full_pattern, count=100
            )
            if keys:
                self.r.delete(*keys)
            if cursor == 0:
                break

    def invalidate_tags(self, tag: str):
        """Tag-based invalidation: invalidate all keys with a tag."""
        tag_key = f"cache:tag:{tag}"
        members = self.r.smembers(tag_key)
        if members:
            self.r.delete(*members, tag_key)

    def set_with_tags(self, namespace: str, key: str, value: Any,
                      tags: list[str], ttl: int = None):
        """Cache a value with tags for group invalidation."""
        cache_key = self._cache_key(namespace, key)
        ttl = ttl or self.config.ttl_seconds

        pipe = self.r.pipeline()
        pipe.set(cache_key, json.dumps(value), ex=ttl)
        for tag in tags:
            pipe.sadd(f"cache:tag:{tag}", cache_key)
            pipe.expire(f"cache:tag:{tag}", ttl + 60)
        pipe.execute()


# === Usage ===
cache = SmartCache("redis://localhost:6379/0", CacheConfig(ttl_seconds=300))

# Cache-aside with stampede prevention
user = cache.get_or_compute(
    "users", "user_123",
    compute_fn=lambda: {"id": 123, "name": "Alice"},  # DB query
    ttl=300,
)

# Decorator for automatic caching
@cache.cached(namespace="api", ttl=60)
def get_product_details(product_id: str) -> dict:
    # Expensive DB query / API call
    return {"id": product_id, "name": "Widget", "price": 49.99}

product = get_product_details("prod_456")  # cached after first call

# Tag-based invalidation
cache.set_with_tags("products", "prod_456",
                    {"id": "prod_456", "price": 49.99},
                    tags=["catalog", "pricing"])
cache.invalidate_tags("pricing")  # invalidates all pricing-related cache
```

Key patterns:
1. **XFetch early refresh** -- probabilistic refresh before TTL expiry prevents thundering herd; requests near expiry increasingly likely to refresh
2. **Stale-while-revalidate** -- store a `:stale` copy with longer TTL; serve stale data while one request recomputes, rather than all requests hitting the DB
3. **Single-flight lock** -- `SET NX PX` acquires a computation lock; only one request computes on cache miss, others wait or serve stale
4. **Multi-tier L1/L2** -- in-process dict (L1) avoids Redis round-trip for hot keys; 30s L1 TTL limits staleness across instances
5. **Tag-based invalidation** -- tag sets track which cache keys belong to a group; invalidating a tag clears all related keys in one operation'''
    ),
]
