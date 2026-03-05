"""Database — Redis patterns, data structures, and Lua scripting."""

PAIRS = [
    (
        "database/redis-data-structures",
        "Show Redis data structure patterns: strings, hashes, sorted sets, streams, and HyperLogLog.",
        '''Redis data structure patterns:

```python
import redis.asyncio as redis
import json
import time
from typing import Optional, Any


# --- Connection ---

pool = redis.ConnectionPool.from_url(
    "redis://localhost:6379/0",
    max_connections=20,
    decode_responses=True,
)
r = redis.Redis(connection_pool=pool)


# --- Rate limiter with sorted sets ---

async def is_rate_limited(user_id: str, max_requests: int = 100,
                          window_seconds: int = 60) -> bool:
    """Sliding window rate limiter using sorted sets."""
    key = f"ratelimit:{user_id}"
    now = time.time()
    window_start = now - window_seconds

    pipe = r.pipeline()
    # Remove old entries
    pipe.zremrangebyscore(key, 0, window_start)
    # Add current request
    pipe.zadd(key, {f"{now}:{id(now)}": now})
    # Count requests in window
    pipe.zcard(key)
    # Set TTL
    pipe.expire(key, window_seconds)

    _, _, count, _ = await pipe.execute()
    return count > max_requests


# --- Leaderboard with sorted sets ---

class Leaderboard:
    def __init__(self, redis_client, name: str):
        self.redis = redis_client
        self.key = f"leaderboard:{name}"

    async def add_score(self, user_id: str, score: float):
        await self.redis.zadd(self.key, {user_id: score})

    async def increment_score(self, user_id: str, amount: float):
        return await self.redis.zincrby(self.key, amount, user_id)

    async def get_rank(self, user_id: str) -> Optional[int]:
        rank = await self.redis.zrevrank(self.key, user_id)
        return rank + 1 if rank is not None else None

    async def get_top(self, n: int = 10) -> list[dict]:
        results = await self.redis.zrevrange(
            self.key, 0, n - 1, withscores=True
        )
        return [
            {"user_id": uid, "score": score, "rank": i + 1}
            for i, (uid, score) in enumerate(results)
        ]

    async def get_around(self, user_id: str, n: int = 5) -> list[dict]:
        """Get users around a specific user's rank."""
        rank = await self.redis.zrevrank(self.key, user_id)
        if rank is None:
            return []
        start = max(0, rank - n)
        end = rank + n
        results = await self.redis.zrevrange(
            self.key, start, end, withscores=True
        )
        return [
            {"user_id": uid, "score": score, "rank": start + i + 1}
            for i, (uid, score) in enumerate(results)
        ]


# --- Session store with hashes ---

class SessionStore:
    def __init__(self, redis_client, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    async def create(self, session_id: str, data: dict) -> None:
        key = f"session:{session_id}"
        await self.redis.hset(key, mapping={
            k: json.dumps(v) for k, v in data.items()
        })
        await self.redis.expire(key, self.ttl)

    async def get(self, session_id: str) -> Optional[dict]:
        key = f"session:{session_id}"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        await self.redis.expire(key, self.ttl)  # Touch TTL
        return {k: json.loads(v) for k, v in data.items()}

    async def update(self, session_id: str, **fields) -> None:
        key = f"session:{session_id}"
        await self.redis.hset(key, mapping={
            k: json.dumps(v) for k, v in fields.items()
        })

    async def delete(self, session_id: str) -> None:
        await self.redis.delete(f"session:{session_id}")


# --- Redis Streams (event log) ---

class EventStream:
    def __init__(self, redis_client, stream_name: str):
        self.redis = redis_client
        self.stream = stream_name

    async def publish(self, event_type: str, data: dict) -> str:
        """Add event to stream, returns event ID."""
        return await self.redis.xadd(self.stream, {
            "type": event_type,
            "data": json.dumps(data),
            "timestamp": str(time.time()),
        }, maxlen=100000)  # Cap stream size

    async def consume(self, group: str, consumer: str,
                      count: int = 10, block_ms: int = 5000):
        """Read from consumer group."""
        try:
            await self.redis.xgroup_create(
                self.stream, group, id="0", mkstream=True
            )
        except redis.ResponseError:
            pass  # Group already exists

        messages = await self.redis.xreadgroup(
            group, consumer,
            {self.stream: ">"},
            count=count,
            block=block_ms,
        )
        return messages

    async def ack(self, group: str, message_id: str):
        await self.redis.xack(self.stream, group, message_id)


# --- HyperLogLog (cardinality estimation) ---

async def track_unique_visitors(page: str, visitor_id: str):
    """Count unique visitors with ~0.81% error using HyperLogLog."""
    key = f"visitors:{page}:{time.strftime('%Y-%m-%d')}"
    await r.pfadd(key, visitor_id)
    await r.expire(key, 86400 * 7)  # Keep for 7 days

async def get_unique_count(page: str, date: str = None) -> int:
    date = date or time.strftime("%Y-%m-%d")
    return await r.pfcount(f"visitors:{page}:{date}")

# Uses only 12KB regardless of number of unique elements!
```

Redis patterns:
1. **Sorted sets** — leaderboards, rate limiters, priority queues
2. **Hashes** — session stores, object caching with field-level access
3. **Streams** — append-only event log with consumer groups
4. **HyperLogLog** — approximate unique counting in 12KB fixed memory
5. **Pipeline** — batch multiple commands to reduce round-trips'''
    ),
    (
        "database/elasticsearch",
        "Show Elasticsearch patterns: indexing, search queries, aggregations, and mapping design.",
        '''Elasticsearch patterns:

```python
from elasticsearch import AsyncElasticsearch
from datetime import datetime


# --- Index mapping ---

PRODUCT_MAPPING = {
    "mappings": {
        "properties": {
            "name": {
                "type": "text",
                "analyzer": "english",
                "fields": {
                    "keyword": {"type": "keyword"},  # For sorting/aggregation
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                    },
                },
            },
            "description": {"type": "text", "analyzer": "english"},
            "category": {"type": "keyword"},
            "brand": {"type": "keyword"},
            "price": {"type": "float"},
            "rating": {"type": "float"},
            "in_stock": {"type": "boolean"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
            "location": {"type": "geo_point"},
        },
    },
    "settings": {
        "number_of_shards": 2,
        "number_of_replicas": 1,
        "analysis": {
            "analyzer": {
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "autocomplete_filter"],
                },
            },
            "filter": {
                "autocomplete_filter": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                },
            },
        },
    },
}


# --- Search service ---

class ProductSearch:
    def __init__(self, es: AsyncElasticsearch, index: str = "products"):
        self.es = es
        self.index = index

    async def search(self, query: str, filters: dict = None,
                     page: int = 1, size: int = 20,
                     sort: str = None) -> dict:
        """Full-text search with filters and facets."""

        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",        # Boost name matches
                                    "description",
                                    "tags^2",
                                    "brand^2",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                            },
                        },
                    ],
                    "filter": self._build_filters(filters or {}),
                },
            },
            "highlight": {
                "fields": {
                    "name": {},
                    "description": {"fragment_size": 150},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            "aggs": {
                "categories": {
                    "terms": {"field": "category", "size": 20},
                },
                "brands": {
                    "terms": {"field": "brand", "size": 20},
                },
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"to": 25},
                            {"from": 25, "to": 50},
                            {"from": 50, "to": 100},
                            {"from": 100, "to": 500},
                            {"from": 500},
                        ],
                    },
                },
                "avg_rating": {"avg": {"field": "rating"}},
                "price_stats": {"stats": {"field": "price"}},
            },
            "from": (page - 1) * size,
            "size": size,
        }

        if sort:
            sort_map = {
                "price_asc": [{"price": "asc"}],
                "price_desc": [{"price": "desc"}],
                "rating": [{"rating": "desc"}],
                "newest": [{"created_at": "desc"}],
                "relevance": ["_score"],
            }
            body["sort"] = sort_map.get(sort, ["_score"])

        result = await self.es.search(index=self.index, body=body)

        return {
            "hits": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"],
                    "highlights": hit.get("highlight", {}),
                }
                for hit in result["hits"]["hits"]
            ],
            "total": result["hits"]["total"]["value"],
            "facets": {
                "categories": [
                    {"name": b["key"], "count": b["doc_count"]}
                    for b in result["aggregations"]["categories"]["buckets"]
                ],
                "brands": [
                    {"name": b["key"], "count": b["doc_count"]}
                    for b in result["aggregations"]["brands"]["buckets"]
                ],
                "price_ranges": result["aggregations"]["price_ranges"]["buckets"],
                "avg_rating": result["aggregations"]["avg_rating"]["value"],
            },
        }

    def _build_filters(self, filters: dict) -> list:
        """Build Elasticsearch filter clauses."""
        clauses = []
        if "category" in filters:
            clauses.append({"term": {"category": filters["category"]}})
        if "brand" in filters:
            clauses.append({"terms": {"brand": filters["brand"]}})
        if "min_price" in filters or "max_price" in filters:
            price_range = {}
            if "min_price" in filters:
                price_range["gte"] = filters["min_price"]
            if "max_price" in filters:
                price_range["lte"] = filters["max_price"]
            clauses.append({"range": {"price": price_range}})
        if "in_stock" in filters:
            clauses.append({"term": {"in_stock": filters["in_stock"]}})
        if "min_rating" in filters:
            clauses.append({"range": {"rating": {"gte": filters["min_rating"]}}})
        return clauses

    async def autocomplete(self, prefix: str, size: int = 10) -> list[str]:
        """Fast autocomplete using edge ngram."""
        result = await self.es.search(
            index=self.index,
            body={
                "query": {
                    "match": {
                        "name.autocomplete": {
                            "query": prefix,
                            "operator": "and",
                        },
                    },
                },
                "_source": ["name"],
                "size": size,
            },
        )
        return [hit["_source"]["name"] for hit in result["hits"]["hits"]]
```

Elasticsearch patterns:
1. **Multi-field mapping** — `text` for search, `keyword` for sort/filter, `autocomplete` for prefix
2. **`multi_match` + boost** — search across fields with relevance weighting
3. **Aggregations** — faceted search with terms, ranges, and stats
4. **Edge ngram** — fast autocomplete without prefix queries
5. **`bool` query** — combine must (scoring), filter (non-scoring), should (boost)'''
    ),
]
