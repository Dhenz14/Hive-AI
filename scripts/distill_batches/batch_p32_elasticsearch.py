"""Elasticsearch — indexing, queries, aggregations, and search patterns."""

PAIRS = [
    (
        "databases/elasticsearch-fundamentals",
        "Show Elasticsearch patterns: index design, mapping, full-text search, filtering, and aggregations with Python.",
        '''Elasticsearch indexing and search patterns:

```python
from elasticsearch import AsyncElasticsearch, helpers
from datetime import datetime, timezone
from typing import Optional

# --- Index design with explicit mapping ---

PRODUCT_INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 3,
        "number_of_replicas": 1,
        "analysis": {
            "analyzer": {
                "product_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "asciifolding",      # café → cafe
                        "product_synonyms",
                        "product_stemmer",
                    ],
                },
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "edge_ngram_filter"],
                },
            },
            "filter": {
                "product_synonyms": {
                    "type": "synonym",
                    "synonyms": [
                        "laptop,notebook",
                        "phone,mobile,cell phone",
                        "tv,television",
                    ],
                },
                "product_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
                "edge_ngram_filter": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "name": {
                "type": "text",
                "analyzer": "product_analyzer",
                "fields": {
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                        "search_analyzer": "standard",
                    },
                    "keyword": {"type": "keyword"},  # For sorting/aggs
                },
            },
            "description": {
                "type": "text",
                "analyzer": "product_analyzer",
            },
            "category": {"type": "keyword"},
            "brand": {"type": "keyword"},
            "price": {"type": "float"},
            "rating": {"type": "float"},
            "in_stock": {"type": "boolean"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
            "location": {"type": "geo_point"},
        }
    },
}


class ProductSearch:
    def __init__(self, es: AsyncElasticsearch, index: str = "products"):
        self.es = es
        self.index = index

    async def create_index(self):
        if not await self.es.indices.exists(index=self.index):
            await self.es.indices.create(
                index=self.index, body=PRODUCT_INDEX_SETTINGS
            )

    # --- Full-text search with filters ---
    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock_only: bool = False,
        sort_by: str = "_score",
        page: int = 1,
        size: int = 20,
    ) -> dict:
        must = []
        filter_clauses = []

        # Full-text search across name and description
        if query:
            must.append({
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "description", "tags^2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            })

        # Exact-match filters (don't affect score)
        if category:
            filter_clauses.append({"term": {"category": category}})
        if in_stock_only:
            filter_clauses.append({"term": {"in_stock": True}})
        if min_price is not None or max_price is not None:
            range_filter = {}
            if min_price is not None:
                range_filter["gte"] = min_price
            if max_price is not None:
                range_filter["lte"] = max_price
            filter_clauses.append({"range": {"price": range_filter}})

        body = {
            "query": {
                "bool": {
                    "must": must or [{"match_all": {}}],
                    "filter": filter_clauses,
                }
            },
            "sort": self._build_sort(sort_by),
            "from": (page - 1) * size,
            "size": size,
            "highlight": {
                "fields": {
                    "name": {},
                    "description": {"fragment_size": 150},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            # Faceted search (aggregations for filters)
            "aggs": {
                "categories": {"terms": {"field": "category", "size": 20}},
                "brands": {"terms": {"field": "brand", "size": 20}},
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"to": 25, "key": "under_25"},
                            {"from": 25, "to": 100, "key": "25_to_100"},
                            {"from": 100, "to": 500, "key": "100_to_500"},
                            {"from": 500, "key": "over_500"},
                        ],
                    }
                },
                "avg_rating": {"avg": {"field": "rating"}},
            },
        }

        result = await self.es.search(index=self.index, body=body)
        return self._format_response(result, page, size)

    # --- Autocomplete ---
    async def autocomplete(self, prefix: str, size: int = 5) -> list[str]:
        result = await self.es.search(
            index=self.index,
            body={
                "query": {
                    "match": {
                        "name.autocomplete": {
                            "query": prefix,
                            "operator": "and",
                        }
                    }
                },
                "size": size,
                "_source": ["name"],
            },
        )
        return [hit["_source"]["name"] for hit in result["hits"]["hits"]]

    # --- Bulk indexing ---
    async def bulk_index(self, products: list[dict]):
        actions = [
            {
                "_index": self.index,
                "_id": p["id"],
                "_source": p,
            }
            for p in products
        ]
        success, errors = await helpers.async_bulk(
            self.es, actions, chunk_size=500, raise_on_error=False
        )
        return {"indexed": success, "errors": len(errors)}

    def _build_sort(self, sort_by: str) -> list:
        sorts = {
            "_score": [{"_score": "desc"}],
            "price_asc": [{"price": "asc"}],
            "price_desc": [{"price": "desc"}],
            "rating": [{"rating": "desc"}],
            "newest": [{"created_at": "desc"}],
        }
        return sorts.get(sort_by, sorts["_score"])

    def _format_response(self, result: dict, page: int, size: int) -> dict:
        hits = result["hits"]
        return {
            "total": hits["total"]["value"],
            "page": page,
            "pages": -(-hits["total"]["value"] // size),
            "items": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"],
                    "highlights": hit.get("highlight", {}),
                }
                for hit in hits["hits"]
            ],
            "facets": {
                "categories": [
                    {"key": b["key"], "count": b["doc_count"]}
                    for b in result["aggregations"]["categories"]["buckets"]
                ],
                "brands": [
                    {"key": b["key"], "count": b["doc_count"]}
                    for b in result["aggregations"]["brands"]["buckets"]
                ],
                "price_ranges": [
                    {"key": b["key"], "count": b["doc_count"]}
                    for b in result["aggregations"]["price_ranges"]["buckets"]
                ],
            },
        }
```

Key patterns:
1. **Custom analyzers** — synonyms, stemming, edge n-grams for autocomplete
2. **Multi-field mappings** — text for search, keyword for filtering/sorting
3. **Bool query** — `must` for scoring, `filter` for exact matches (cached)
4. **Aggregations** — faceted search for filter counts alongside results
5. **Bulk indexing** — always use bulk API for efficiency'''
    ),
    (
        "databases/elasticsearch-advanced",
        "Show advanced Elasticsearch patterns: index lifecycle, reindexing strategies, scroll/search_after pagination, and monitoring.",
        '''Advanced Elasticsearch operational patterns:

```python
# --- Index Lifecycle Management (ILM) ---

ILM_POLICY = {
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {
                        "max_size": "50gb",
                        "max_age": "7d",
                        "max_docs": 10_000_000,
                    },
                    "set_priority": {"priority": 100},
                },
            },
            "warm": {
                "min_age": "30d",
                "actions": {
                    "shrink": {"number_of_shards": 1},
                    "forcemerge": {"max_num_segments": 1},
                    "set_priority": {"priority": 50},
                    "allocate": {
                        "require": {"data": "warm"},
                    },
                },
            },
            "cold": {
                "min_age": "90d",
                "actions": {
                    "set_priority": {"priority": 0},
                    "freeze": {},
                    "allocate": {
                        "require": {"data": "cold"},
                    },
                },
            },
            "delete": {
                "min_age": "365d",
                "actions": {"delete": {}},
            },
        }
    }
}

# --- Zero-downtime reindexing ---

async def reindex_with_alias(es, old_index: str, new_index: str,
                              alias: str):
    """Reindex to new mapping without downtime using aliases."""
    # 1. Create new index with updated mapping
    await es.indices.create(index=new_index, body=NEW_MAPPING)

    # 2. Reindex data
    await es.reindex(
        body={
            "source": {"index": old_index},
            "dest": {"index": new_index},
        },
        wait_for_completion=True,
    )

    # 3. Atomic alias swap
    await es.indices.update_aliases(
        body={
            "actions": [
                {"remove": {"index": old_index, "alias": alias}},
                {"add": {"index": new_index, "alias": alias}},
            ]
        }
    )

    # 4. Delete old index after verification
    count_old = (await es.count(index=old_index))["count"]
    count_new = (await es.count(index=new_index))["count"]
    if count_new >= count_old:
        await es.indices.delete(index=old_index)


# --- Efficient deep pagination with search_after ---

async def scroll_all_documents(es, index: str, query: dict,
                                batch_size: int = 1000):
    """Use search_after for efficient deep pagination."""
    results = []
    search_after = None

    while True:
        body = {
            "query": query,
            "size": batch_size,
            "sort": [
                {"created_at": "desc"},
                {"_id": "asc"},  # Tiebreaker
            ],
        }
        if search_after:
            body["search_after"] = search_after

        response = await es.search(index=index, body=body)
        hits = response["hits"]["hits"]

        if not hits:
            break

        for hit in hits:
            yield hit["_source"]

        search_after = hits[-1]["sort"]


# --- Point-in-time (PIT) for consistent pagination ---

async def consistent_scroll(es, index: str, query: dict):
    """PIT ensures consistent results even during index updates."""
    # Open PIT
    pit = await es.open_point_in_time(
        index=index, keep_alive="5m"
    )
    pit_id = pit["id"]

    try:
        search_after = None
        while True:
            body = {
                "query": query,
                "size": 1000,
                "sort": [{"_shard_doc": "asc"}],
                "pit": {"id": pit_id, "keep_alive": "5m"},
            }
            if search_after:
                body["search_after"] = search_after

            response = await es.search(body=body)
            hits = response["hits"]["hits"]

            if not hits:
                break

            for hit in hits:
                yield hit["_source"]

            search_after = hits[-1]["sort"]
            pit_id = response["pit_id"]
    finally:
        await es.close_point_in_time(body={"id": pit_id})


# --- Index template for time-series data ---

INDEX_TEMPLATE = {
    "index_patterns": ["logs-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "index.lifecycle.name": "logs-policy",
            "index.lifecycle.rollover_alias": "logs",
        },
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "level": {"type": "keyword"},
                "service": {"type": "keyword"},
                "message": {"type": "text"},
                "trace_id": {"type": "keyword"},
                "duration_ms": {"type": "float"},
            }
        },
    },
}
```

Operational patterns:
1. **ILM** — hot/warm/cold/delete lifecycle for cost optimization
2. **Aliases** — zero-downtime reindexing and routing
3. **search_after** — efficient deep pagination (avoid scroll for user-facing)
4. **PIT** — consistent snapshots for paginating changing data
5. **Index templates** — automatic mapping for time-series indices'''
    ),
]
"""
