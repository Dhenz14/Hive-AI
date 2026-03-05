"""Search engines — Elasticsearch/OpenSearch patterns, BM25 scoring, faceted search, autocomplete, hybrid search, index management."""

PAIRS = [
    (
        "databases/elasticsearch-index-management",
        "Show Elasticsearch index management: mappings, analyzers, index lifecycle, templates, and reindexing strategies.",
        '''Elasticsearch index management with mappings, analyzers, and lifecycle:

```python
from elasticsearch import Elasticsearch, helpers
from datetime import datetime, timedelta
import json


class ElasticsearchIndexManager:
    """Production Elasticsearch index management with custom analyzers,
    index templates, aliases, and lifecycle policies."""

    def __init__(self, hosts: list[str] = None):
        self.es = Elasticsearch(
            hosts or ["http://localhost:9200"],
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )

    def create_product_index(self, index_name: str = "products-v1"):
        """Create a product index with custom analyzers and mappings."""
        settings = {
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "refresh_interval": "1s",
                "analysis": {
                    "analyzer": {
                        # Custom analyzer for product names
                        "product_name_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",     # cafe -> cafe (accent folding)
                                "product_synonyms",
                                "word_delimiter_graph",
                                "english_stemmer",
                            ],
                        },
                        # Autocomplete analyzer (edge ngrams for prefix matching)
                        "autocomplete_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "autocomplete_filter",
                            ],
                        },
                        # Search-time analyzer for autocomplete (no ngrams)
                        "autocomplete_search": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding"],
                        },
                        # SKU / exact match analyzer
                        "sku_analyzer": {
                            "type": "custom",
                            "tokenizer": "keyword",
                            "filter": ["uppercase"],
                        },
                    },
                    "filter": {
                        "product_synonyms": {
                            "type": "synonym",
                            "synonyms": [
                                "laptop, notebook, portable computer",
                                "phone, mobile, smartphone, cellphone",
                                "tv, television, display, monitor",
                                "headphones, earphones, earbuds",
                            ],
                        },
                        "autocomplete_filter": {
                            "type": "edge_ngram",
                            "min_gram": 2,
                            "max_gram": 15,
                        },
                        "english_stemmer": {
                            "type": "stemmer",
                            "language": "english",
                        },
                    },
                },
            },
            "mappings": {
                "properties": {
                    "product_id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "analyzer": "product_name_analyzer",
                        "fields": {
                            "exact": {"type": "keyword"},
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_analyzer",
                                "search_analyzer": "autocomplete_search",
                            },
                        },
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "product_name_analyzer",
                    },
                    "sku": {
                        "type": "text",
                        "analyzer": "sku_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                        },
                    },
                    "brand": {
                        "type": "keyword",
                        "fields": {
                            "text": {
                                "type": "text",
                                "analyzer": "standard",
                            },
                        },
                    },
                    "categories": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "price": {"type": "float"},
                    "sale_price": {"type": "float"},
                    "rating": {"type": "float"},
                    "review_count": {"type": "integer"},
                    "availability": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    # Nested type for variant attributes
                    "variants": {
                        "type": "nested",
                        "properties": {
                            "color": {"type": "keyword"},
                            "size": {"type": "keyword"},
                            "price": {"type": "float"},
                            "in_stock": {"type": "boolean"},
                        },
                    },
                    # Dense vector for semantic search
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine",
                    },
                },
            },
        }

        self.es.indices.create(index=index_name, body=settings)
        # Create alias pointing to this version
        self.es.indices.put_alias(index=index_name, name="products")
        return index_name

    def setup_index_lifecycle(self):
        """Configure ILM for time-series indexes (logs, events)."""
        # ILM policy: hot -> warm -> cold -> delete
        policy = {
            "policy": {
                "phases": {
                    "hot": {
                        "min_age": "0ms",
                        "actions": {
                            "rollover": {
                                "max_primary_shard_size": "50gb",
                                "max_age": "7d",
                                "max_docs": 100_000_000,
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
                            "allocate": {
                                "require": {"data": "cold"},
                            },
                        },
                    },
                    "delete": {
                        "min_age": "365d",
                        "actions": {"delete": {}},
                    },
                },
            },
        }
        self.es.ilm.put_lifecycle(name="logs-policy", body=policy)

        # Index template for log indexes
        template = {
            "index_patterns": ["logs-*"],
            "template": {
                "settings": {
                    "number_of_shards": 3,
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
                    },
                },
            },
        }
        self.es.indices.put_index_template(
            name="logs-template", body=template
        )

    def zero_downtime_reindex(self, old_index: str,
                              new_index: str,
                              alias: str = "products"):
        """Reindex with zero downtime using aliases."""
        # Step 1: Create new index (with new mappings/settings)
        self.create_product_index(new_index)

        # Step 2: Reindex data
        self.es.reindex(
            body={
                "source": {"index": old_index},
                "dest": {"index": new_index},
            },
            wait_for_completion=True,
            request_timeout=3600,
        )

        # Step 3: Atomically switch alias
        self.es.indices.update_aliases(body={
            "actions": [
                {"remove": {"index": old_index, "alias": alias}},
                {"add": {"index": new_index, "alias": alias}},
            ]
        })

        # Step 4: Delete old index after verification
        new_count = self.es.count(index=new_index)["count"]
        old_count = self.es.count(index=old_index)["count"]
        if new_count >= old_count:
            self.es.indices.delete(index=old_index)
            return {"status": "success", "docs": new_count}
        else:
            return {"status": "count_mismatch",
                    "old": old_count, "new": new_count}

    def bulk_index(self, index: str, documents: list[dict],
                   chunk_size: int = 1000):
        """Efficient bulk indexing with helpers."""
        actions = [
            {
                "_index": index,
                "_id": doc.get("product_id", doc.get("id")),
                "_source": doc,
            }
            for doc in documents
        ]

        success, errors = helpers.bulk(
            self.es, actions,
            chunk_size=chunk_size,
            raise_on_error=False,
            request_timeout=120,
        )
        return {"indexed": success, "errors": len(errors)}


# === Usage ===
mgr = ElasticsearchIndexManager()

# Create index with custom analyzers
mgr.create_product_index("products-v1")

# Set up ILM for logs
mgr.setup_index_lifecycle()

# Zero-downtime reindex
mgr.zero_downtime_reindex("products-v1", "products-v2")
```

Key patterns:
1. **Multi-field mappings** -- `name` indexed as text (search), keyword (sort/aggregate), and autocomplete (prefix); one source field, three query strategies
2. **Custom analyzers** -- synonym expansion + stemming for recall; edge ngrams for type-ahead; keyword analyzer for exact SKU match
3. **ILM lifecycle** -- hot/warm/cold/delete phases manage disk automatically; rollover triggers on size/age/doc count; force-merge on warm for query speed
4. **Zero-downtime reindex** -- create new index, reindex data, atomically swap alias; applications query the alias and never see the swap
5. **Bulk indexing** -- `helpers.bulk()` batches documents into efficient bulk requests; always use chunk_size to control memory; raise_on_error=False for partial failure tolerance'''
    ),
    (
        "databases/elasticsearch-bm25-scoring",
        "Explain Elasticsearch BM25 scoring: relevance tuning, function_score, boosting strategies, and search-time relevance signals.",
        '''Elasticsearch BM25 scoring and relevance tuning:

```python
from elasticsearch import Elasticsearch


class RelevanceEngine:
    """Elasticsearch relevance tuning with BM25, function_score,
    and multi-signal ranking."""

    def __init__(self, es: Elasticsearch):
        self.es = es
        self.index = "products"

    def basic_multi_match(self, query: str) -> dict:
        """Multi-field search with field boosting.

        BM25 scores each field independently; cross_fields
        combines term frequencies across fields.
        """
        return self.es.search(index=self.index, body={
            "query": {
                "multi_match": {
                    "query": query,
                    "type": "cross_fields",  # treat fields as one big field
                    "fields": [
                        "name^5",          # name matches worth 5x
                        "brand^3",         # brand matches worth 3x
                        "description^1",   # description is baseline
                        "tags^2",          # tags worth 2x
                    ],
                    "operator": "and",      # all terms must match somewhere
                    "tie_breaker": 0.3,     # weight for non-best-matching fields
                    "minimum_should_match": "75%",
                },
            },
            "size": 20,
        })

    def function_score_search(self, query: str,
                              user_location: dict = None) -> dict:
        """Combine BM25 with business signals using function_score.

        Final score = BM25 * (rating_boost * recency_boost * popularity)
        """
        functions = [
            # Boost by product rating (logarithmic)
            {
                "field_value_factor": {
                    "field": "rating",
                    "factor": 1.2,
                    "modifier": "log1p",  # log(1 + rating * 1.2)
                    "missing": 3.0,       # default if no rating
                },
                "weight": 2,
            },
            # Boost recently added products (exponential decay)
            {
                "exp": {
                    "created_at": {
                        "origin": "now",
                        "scale": "30d",     # 50% score at 30 days old
                        "offset": "7d",     # full score within 7 days
                        "decay": 0.5,
                    },
                },
                "weight": 1.5,
            },
            # Boost by review count (diminishing returns)
            {
                "field_value_factor": {
                    "field": "review_count",
                    "factor": 1,
                    "modifier": "log2p",  # log2(2 + count)
                    "missing": 0,
                },
                "weight": 1,
            },
            # Boost items on sale
            {
                "filter": {
                    "exists": {"field": "sale_price"},
                },
                "weight": 1.3,
            },
            # Boost in-stock items heavily
            {
                "filter": {
                    "term": {"availability": "in_stock"},
                },
                "weight": 5,
            },
        ]

        # Add geo-distance decay if user location provided
        if user_location:
            functions.append({
                "exp": {
                    "store_location": {
                        "origin": user_location,
                        "scale": "10km",
                        "offset": "1km",
                        "decay": 0.5,
                    },
                },
                "weight": 2,
            })

        return self.es.search(index=self.index, body={
            "query": {
                "function_score": {
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["name^5", "brand^3", "description"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        },
                    },
                    "functions": functions,
                    "score_mode": "multiply",  # multiply all function scores
                    "boost_mode": "multiply",  # multiply with BM25 query score
                    "max_boost": 10,           # cap total boost
                },
            },
            "size": 20,
            "explain": False,  # set True to debug scoring
        })

    def pinning_and_burying(self, query: str,
                            pinned_ids: list[str] = None,
                            buried_ids: list[str] = None) -> dict:
        """Pin specific products to top, bury others to bottom."""
        should_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["name^5", "brand^3", "description"],
                },
            },
        ]

        if pinned_ids:
            should_clauses.append({
                "constant_score": {
                    "filter": {"ids": {"values": pinned_ids}},
                    "boost": 1000,  # force to top
                },
            })

        must_not = []
        if buried_ids:
            # Exclude buried items from main results
            must_not.append({"ids": {"values": buried_ids}})

        return self.es.search(index=self.index, body={
            "query": {
                "bool": {
                    "should": should_clauses,
                    "must_not": must_not,
                    "minimum_should_match": 1,
                },
            },
            "size": 20,
        })

    def explain_score(self, query: str, doc_id: str) -> dict:
        """Debug: explain how a document was scored."""
        return self.es.explain(
            index=self.index,
            id=doc_id,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["name^5", "brand^3", "description"],
                    },
                },
            },
        )

    def rescore_with_phrase(self, query: str) -> dict:
        """Two-phase scoring: BM25 first, then rescore top N with phrases.

        Phase 1: BM25 retrieves top 200 candidates (fast)
        Phase 2: phrase matching rescores candidates (accurate but slow)
        """
        return self.es.search(index=self.index, body={
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "description"],
                    "type": "best_fields",
                },
            },
            "rescore": {
                "window_size": 200,  # rescore top 200
                "query": {
                    "rescore_query": {
                        "match_phrase": {
                            "name": {
                                "query": query,
                                "slop": 2,  # allow 2 words between terms
                            },
                        },
                    },
                    "query_weight": 0.7,
                    "rescore_query_weight": 1.5,
                },
            },
            "size": 20,
        })


# === Usage ===
es = Elasticsearch(["http://localhost:9200"])
engine = RelevanceEngine(es)

# Basic search with field boosting
results = engine.basic_multi_match("wireless noise cancelling headphones")

# Business-signal-boosted search
results = engine.function_score_search(
    "bluetooth speaker",
    user_location={"lat": 40.7128, "lon": -74.0060},
)

# Debug scoring
explanation = engine.explain_score("laptop", "product-123")

# Two-phase scoring for precision
results = engine.rescore_with_phrase("macbook pro 16 inch")
```

| BM25 Parameter | Default | Effect |
|---|---|---|
| k1 | 1.2 | Term frequency saturation (higher = more weight to repeated terms) |
| b | 0.75 | Length normalization (0 = no penalty for long docs, 1 = full penalty) |
| boost | 1.0 | Per-field multiplier (name^5 means 5x weight) |

Key patterns:
1. **Field boosting** -- `name^5` makes name matches 5x more relevant than description; tune based on user click-through data
2. **function_score** -- multiply BM25 with business signals (rating, recency, popularity, stock); `score_mode: multiply` combines functions, `boost_mode: multiply` combines with query
3. **Exponential decay** -- `exp` function for time and distance; items within `offset` get full score, decay to 50% at `scale` distance
4. **Rescore for precision** -- BM25 retrieves fast candidates; `match_phrase` with slop rescores for exact phrase proximity; 2-phase is faster than phrase-first
5. **Explain API** -- `_explain` shows exact BM25 term weights, field boosts, and function scores; essential for debugging why a document ranks high or low'''
    ),
    (
        "databases/elasticsearch-faceted-search",
        "Implement faceted search with Elasticsearch: aggregation-based facets, filter aggregations, hierarchical facets, and real-time facet counts.",
        '''Faceted search implementation with Elasticsearch aggregations:

```python
from elasticsearch import Elasticsearch
from typing import Optional


class FacetedSearchEngine:
    """E-commerce faceted search with dynamic facets,
    selected-filter-aware counts, and hierarchical categories."""

    def __init__(self, es: Elasticsearch, index: str = "products"):
        self.es = es
        self.index = index

    def faceted_search(
        self, query: str = None,
        filters: dict = None,
        page: int = 0,
        page_size: int = 20,
        sort: str = "relevance",
    ) -> dict:
        """Full faceted search with filter-aware aggregation counts.

        The key insight: aggregations for a facet should NOT be
        filtered by that facet's own selection (so the user sees
        all options), but SHOULD be filtered by all other facets.
        This is called "post-filter" pattern.
        """
        filters = filters or {}

        # === Build the main query ===
        must_clauses = []

        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": ["name^5", "brand^3", "description"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                },
            })

        # Non-faceted filters go in main query
        if "price_min" in filters or "price_max" in filters:
            price_range = {}
            if "price_min" in filters:
                price_range["gte"] = filters["price_min"]
            if "price_max" in filters:
                price_range["lte"] = filters["price_max"]
            must_clauses.append({"range": {"price": price_range}})

        if "in_stock" in filters and filters["in_stock"]:
            must_clauses.append(
                {"term": {"availability": "in_stock"}}
            )

        # === Build facet-aware aggregations ===
        # Each facet's aggregation is filtered by ALL OTHER facets
        # but NOT by itself (so users see counts for unselected values)

        aggs = {}

        # Brand facet
        brand_filter = self._build_all_filters_except(filters, "brand")
        aggs["brand_facet"] = {
            "filter": brand_filter,
            "aggs": {
                "brands": {
                    "terms": {
                        "field": "brand",
                        "size": 50,
                        "order": {"_count": "desc"},
                    },
                },
            },
        }

        # Category facet (hierarchical)
        cat_filter = self._build_all_filters_except(filters, "category")
        aggs["category_facet"] = {
            "filter": cat_filter,
            "aggs": {
                "categories": {
                    "terms": {
                        "field": "categories",
                        "size": 100,
                        "order": {"_count": "desc"},
                    },
                },
            },
        }

        # Rating facet (histogram)
        rating_filter = self._build_all_filters_except(filters, "rating")
        aggs["rating_facet"] = {
            "filter": rating_filter,
            "aggs": {
                "ratings": {
                    "histogram": {
                        "field": "rating",
                        "interval": 1,
                        "min_doc_count": 0,
                        "extended_bounds": {"min": 1, "max": 5},
                    },
                },
            },
        }

        # Price range facet
        price_filter = self._build_all_filters_except(filters, "price")
        aggs["price_facet"] = {
            "filter": price_filter,
            "aggs": {
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"key": "Under $25", "to": 25},
                            {"key": "$25 - $50", "from": 25, "to": 50},
                            {"key": "$50 - $100", "from": 50, "to": 100},
                            {"key": "$100 - $250", "from": 100, "to": 250},
                            {"key": "$250+", "from": 250},
                        ],
                    },
                },
                "price_stats": {
                    "stats": {"field": "price"},
                },
            },
        }

        # === Post-filter: apply selected facet filters to results only ===
        # (not to aggregation counts)
        post_filter_clauses = []
        if "brand" in filters:
            brands = filters["brand"] if isinstance(
                filters["brand"], list
            ) else [filters["brand"]]
            post_filter_clauses.append(
                {"terms": {"brand": brands}}
            )
        if "category" in filters:
            post_filter_clauses.append(
                {"term": {"categories": filters["category"]}}
            )
        if "min_rating" in filters:
            post_filter_clauses.append(
                {"range": {"rating": {"gte": filters["min_rating"]}}}
            )

        # === Sort ===
        sort_config = self._build_sort(sort)

        # === Execute search ===
        body = {
            "query": {
                "bool": {"must": must_clauses or [{"match_all": {}}]},
            },
            "aggs": aggs,
            "from": page * page_size,
            "size": page_size,
            "sort": sort_config,
            "highlight": {
                "fields": {
                    "name": {"number_of_fragments": 0},
                    "description": {
                        "fragment_size": 150,
                        "number_of_fragments": 2,
                    },
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
        }

        if post_filter_clauses:
            body["post_filter"] = {
                "bool": {"must": post_filter_clauses},
            }

        response = self.es.search(index=self.index, body=body)

        # === Format response ===
        return {
            "total": response["hits"]["total"]["value"],
            "page": page,
            "page_size": page_size,
            "results": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"],
                    "highlights": hit.get("highlight", {}),
                }
                for hit in response["hits"]["hits"]
            ],
            "facets": {
                "brands": [
                    {"value": b["key"], "count": b["doc_count"]}
                    for b in response["aggregations"]["brand_facet"]
                    ["brands"]["buckets"]
                ],
                "categories": [
                    {"value": c["key"], "count": c["doc_count"]}
                    for c in response["aggregations"]["category_facet"]
                    ["categories"]["buckets"]
                ],
                "ratings": [
                    {"value": int(r["key"]), "count": r["doc_count"]}
                    for r in response["aggregations"]["rating_facet"]
                    ["ratings"]["buckets"]
                ],
                "price_ranges": [
                    {"label": r["key"], "count": r["doc_count"]}
                    for r in response["aggregations"]["price_facet"]
                    ["price_ranges"]["buckets"]
                ],
                "price_stats": response["aggregations"]["price_facet"]
                ["price_stats"],
            },
        }

    def _build_all_filters_except(self, filters: dict,
                                   exclude_facet: str) -> dict:
        """Build bool filter from all active facet selections except one."""
        clauses = []

        if exclude_facet != "brand" and "brand" in filters:
            brands = filters["brand"] if isinstance(
                filters["brand"], list
            ) else [filters["brand"]]
            clauses.append({"terms": {"brand": brands}})

        if exclude_facet != "category" and "category" in filters:
            clauses.append(
                {"term": {"categories": filters["category"]}}
            )

        if exclude_facet != "rating" and "min_rating" in filters:
            clauses.append(
                {"range": {"rating": {"gte": filters["min_rating"]}}}
            )

        if exclude_facet != "price":
            if "price_min" in filters:
                clauses.append(
                    {"range": {"price": {"gte": filters["price_min"]}}}
                )
            if "price_max" in filters:
                clauses.append(
                    {"range": {"price": {"lte": filters["price_max"]}}}
                )

        if clauses:
            return {"bool": {"must": clauses}}
        return {"match_all": {}}

    def _build_sort(self, sort: str) -> list:
        sort_map = {
            "relevance": [{"_score": "desc"}],
            "price_asc": [{"price": "asc"}, {"_score": "desc"}],
            "price_desc": [{"price": "desc"}, {"_score": "desc"}],
            "rating": [{"rating": "desc"}, {"_score": "desc"}],
            "newest": [{"created_at": "desc"}, {"_score": "desc"}],
            "popular": [{"review_count": "desc"}, {"_score": "desc"}],
        }
        return sort_map.get(sort, sort_map["relevance"])


# === Usage ===
es = Elasticsearch(["http://localhost:9200"])
engine = FacetedSearchEngine(es)

# Search with facets
results = engine.faceted_search(
    query="wireless headphones",
    filters={
        "brand": ["Sony", "Bose"],
        "min_rating": 4,
        "price_min": 50,
        "price_max": 300,
        "in_stock": True,
    },
    page=0,
    sort="relevance",
)

print(f"Found {results['total']} products")
print(f"Brand facets: {results['facets']['brands'][:5]}")
print(f"Price stats: {results['facets']['price_stats']}")
```

Key patterns:
1. **Post-filter pattern** -- `post_filter` applies facet selections to results but NOT to aggregation counts; users see all options with accurate counts
2. **Filter-per-facet** -- each facet aggregation is wrapped in a filter with ALL OTHER facet selections; ensures counts reflect cross-facet selections correctly
3. **Hierarchical facets** -- category terms aggregation with `size: 100` handles deep taxonomies; for parent-child, use `composite` aggregation or nested terms
4. **Price stats + ranges** -- return both predefined ranges (for checkboxes) and min/max/avg stats (for slider UI) in a single query
5. **Highlight** -- `number_of_fragments: 0` on name returns the full highlighted field; on description, `fragment_size: 150` returns contextual snippets'''
    ),
    (
        "databases/elasticsearch-autocomplete",
        "Implement search autocomplete with Elasticsearch: completion suggester, search-as-you-type, query suggestions, and popular searches.",
        '''Elasticsearch autocomplete and search suggestions:

```python
from elasticsearch import Elasticsearch
from collections import defaultdict
from datetime import datetime
import hashlib


class AutocompleteEngine:
    """Multi-strategy autocomplete: completion suggester, search-as-you-type,
    and analytics-driven popular queries."""

    def __init__(self, es: Elasticsearch):
        self.es = es

    def create_autocomplete_index(self):
        """Create index optimized for autocomplete scenarios."""
        self.es.indices.create(index="autocomplete", body={
            "settings": {
                "number_of_shards": 1,  # single shard for fast completion
                "analysis": {
                    "analyzer": {
                        "search_as_you_type_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "shingle_filter",
                            ],
                        },
                    },
                    "filter": {
                        "shingle_filter": {
                            "type": "shingle",
                            "min_shingle_size": 2,
                            "max_shingle_size": 3,
                        },
                    },
                },
            },
            "mappings": {
                "properties": {
                    # Strategy 1: Completion Suggester (fastest)
                    "suggest": {
                        "type": "completion",
                        "analyzer": "simple",
                        "preserve_separators": True,
                        "preserve_position_increments": True,
                        "max_input_length": 50,
                    },
                    # Strategy 2: search_as_you_type field
                    "title": {
                        "type": "search_as_you_type",
                        "max_shingle_size": 3,
                    },
                    # Metadata
                    "category": {"type": "keyword"},
                    "popularity": {"type": "integer"},
                    "result_count": {"type": "integer"},
                },
            },
        })

        # Separate index for query analytics
        self.es.indices.create(index="search-queries", body={
            "mappings": {
                "properties": {
                    "query": {"type": "keyword"},
                    "query_text": {
                        "type": "search_as_you_type",
                    },
                    "count": {"type": "integer"},
                    "avg_results": {"type": "float"},
                    "avg_ctr": {"type": "float"},
                    "last_searched": {"type": "date"},
                },
            },
        })

    def index_suggestions(self, suggestions: list[dict]):
        """Index autocomplete suggestions with weighted inputs."""
        actions = []
        for s in suggestions:
            # Generate multiple input forms for flexible matching
            inputs = [s["title"]]
            words = s["title"].lower().split()
            # Add individual words as inputs (match from any word)
            inputs.extend(words)
            # Add 2-word prefixes
            for i in range(len(words) - 1):
                inputs.append(f"{words[i]} {words[i+1]}")

            actions.append({
                "_index": "autocomplete",
                "_id": s.get("id", hashlib.md5(
                    s["title"].encode()
                ).hexdigest()),
                "_source": {
                    "suggest": {
                        "input": inputs,
                        "weight": s.get("popularity", 1),
                    },
                    "title": s["title"],
                    "category": s.get("category"),
                    "popularity": s.get("popularity", 0),
                    "result_count": s.get("result_count", 0),
                },
            })

        from elasticsearch.helpers import bulk
        bulk(self.es, actions)

    def completion_suggest(self, prefix: str,
                           size: int = 7) -> list[dict]:
        """Strategy 1: Completion Suggester (sub-millisecond).

        Uses an in-memory FST (Finite State Transducer) data structure.
        Fastest option but limited to prefix matching.
        """
        response = self.es.search(index="autocomplete", body={
            "suggest": {
                "product-suggest": {
                    "prefix": prefix,
                    "completion": {
                        "field": "suggest",
                        "size": size,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO",
                            "min_length": 3,
                            "prefix_length": 2,
                        },
                    },
                },
            },
            "_source": ["title", "category", "popularity"],
        })

        return [
            {
                "text": option["text"],
                "score": option["_score"],
                "source": option["_source"],
            }
            for option in response["suggest"]["product-suggest"][0]["options"]
        ]

    def search_as_you_type(self, query: str,
                           size: int = 7) -> list[dict]:
        """Strategy 2: search_as_you_type field (flexible, infix matching).

        Matches within words, not just prefixes. Slightly slower
        than completion suggester but more flexible.
        """
        response = self.es.search(index="autocomplete", body={
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "type": "bool_prefix",
                                "fields": [
                                    "title",
                                    "title._2gram",
                                    "title._3gram",
                                ],
                            },
                        },
                        # Boost exact prefix matches
                        {
                            "match_phrase_prefix": {
                                "title": {
                                    "query": query,
                                    "boost": 2,
                                },
                            },
                        },
                    ],
                },
            },
            "sort": [
                {"_score": "desc"},
                {"popularity": "desc"},
            ],
            "size": size,
            "_source": ["title", "category", "popularity"],
        })

        return [
            {
                "text": hit["_source"]["title"],
                "score": hit["_score"],
                "category": hit["_source"].get("category"),
                "popularity": hit["_source"].get("popularity", 0),
            }
            for hit in response["hits"]["hits"]
        ]

    def popular_queries(self, prefix: str,
                        size: int = 5) -> list[dict]:
        """Strategy 3: Analytics-driven suggestions from search history."""
        response = self.es.search(index="search-queries", body={
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": prefix,
                                "type": "bool_prefix",
                                "fields": [
                                    "query_text",
                                    "query_text._2gram",
                                    "query_text._3gram",
                                ],
                            },
                        },
                        {"range": {"avg_results": {"gt": 0}}},
                        {"range": {"count": {"gte": 5}}},
                    ],
                },
            },
            "sort": [
                {"_score": "desc"},
                {"count": "desc"},
            ],
            "size": size,
            "_source": ["query", "count", "avg_results", "avg_ctr"],
        })

        return [
            {
                "query": hit["_source"]["query"],
                "search_count": hit["_source"]["count"],
                "avg_results": hit["_source"]["avg_results"],
            }
            for hit in response["hits"]["hits"]
        ]

    def combined_autocomplete(self, prefix: str) -> dict:
        """Combine all strategies into a single response."""
        return {
            "completions": self.completion_suggest(prefix, size=5),
            "search_suggestions": self.search_as_you_type(prefix, size=5),
            "popular_searches": self.popular_queries(prefix, size=3),
        }

    def record_search(self, query: str, result_count: int,
                      clicks: int = 0):
        """Record search query for analytics-driven suggestions."""
        query_id = hashlib.md5(query.lower().strip().encode()).hexdigest()
        self.es.update(
            index="search-queries",
            id=query_id,
            body={
                "script": {
                    "source": """
                        ctx._source.count += 1;
                        ctx._source.avg_results =
                            (ctx._source.avg_results * (ctx._source.count - 1)
                            + params.results) / ctx._source.count;
                        ctx._source.last_searched = params.now;
                    """,
                    "params": {
                        "results": result_count,
                        "now": datetime.utcnow().isoformat(),
                    },
                },
                "upsert": {
                    "query": query.lower().strip(),
                    "query_text": query.lower().strip(),
                    "count": 1,
                    "avg_results": result_count,
                    "avg_ctr": 0,
                    "last_searched": datetime.utcnow().isoformat(),
                },
            },
        )


# === Usage ===
es = Elasticsearch(["http://localhost:9200"])
ac = AutocompleteEngine(es)
ac.create_autocomplete_index()

# Index suggestions
ac.index_suggestions([
    {"title": "Sony WH-1000XM5 Headphones", "category": "electronics",
     "popularity": 9500},
    {"title": "Sony WF-1000XM5 Earbuds", "category": "electronics",
     "popularity": 8200},
])

# Get combined autocomplete suggestions
results = ac.combined_autocomplete("sony wh")

# Record search for analytics-driven suggestions
ac.record_search("sony headphones", result_count=42, clicks=3)
```

Key patterns:
1. **Completion suggester** -- FST-based, sub-millisecond; best for prefix matching from a curated list; weight by popularity for smart ordering
2. **search_as_you_type** -- auto-generated ngram subfields (`._2gram`, `._3gram`); matches infixes and partial words; more flexible than completion
3. **Multi-input completion** -- index multiple input strings per suggestion (full title + individual words + bigrams); matches "headphones" even when typing "headph"
4. **Analytics-driven suggestions** -- record every search query with result counts; surface popular queries with results as suggestions; avoids suggesting zero-result queries
5. **Combined response** -- return completions + search suggestions + popular queries in one response; front-end can render each group separately'''
    ),
    (
        "databases/elasticsearch-hybrid-search",
        "Implement hybrid search combining keyword (BM25) and vector (kNN) search in Elasticsearch for semantic + keyword retrieval.",
        '''Hybrid keyword + vector search with Elasticsearch:

```python
from elasticsearch import Elasticsearch
import numpy as np
from typing import Optional


class HybridSearchEngine:
    """Combine BM25 keyword search with kNN vector similarity
    for best-of-both-worlds retrieval.

    Keyword search excels at exact matches (SKU, brand names).
    Vector search excels at semantic similarity (synonyms, concepts).
    Hybrid combines both for superior relevance.
    """

    def __init__(self, es: Elasticsearch, index: str = "products"):
        self.es = es
        self.index = index

    def create_hybrid_index(self):
        """Create index supporting both BM25 text and dense vectors."""
        self.es.indices.create(index=self.index, body={
            "settings": {
                "number_of_shards": 3,
                "analysis": {
                    "analyzer": {
                        "product_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "english_stemmer"],
                        },
                    },
                    "filter": {
                        "english_stemmer": {
                            "type": "stemmer",
                            "language": "english",
                        },
                    },
                },
            },
            "mappings": {
                "properties": {
                    "product_id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "analyzer": "product_analyzer",
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "product_analyzer",
                    },
                    "brand": {"type": "keyword"},
                    "price": {"type": "float"},
                    "rating": {"type": "float"},
                    # Dense vector for semantic search
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine",
                        "index_options": {
                            "type": "hnsw",
                            "m": 16,
                            "ef_construction": 100,
                        },
                    },
                },
            },
        })

    def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
        k: int = 20,
        filters: dict = None,
    ) -> dict:
        """Execute hybrid search using RRF (Reciprocal Rank Fusion).

        RRF score = sum(1 / (rank_constant + rank_i)) for each query.
        Merges rankings without requiring score normalization.
        """
        # Build filter for both queries
        filter_clauses = []
        if filters:
            if "brand" in filters:
                filter_clauses.append(
                    {"terms": {"brand": filters["brand"]}}
                )
            if "min_price" in filters:
                filter_clauses.append(
                    {"range": {"price": {"gte": filters["min_price"]}}}
                )
            if "max_price" in filters:
                filter_clauses.append(
                    {"range": {"price": {"lte": filters["max_price"]}}}
                )

        es_filter = (
            {"bool": {"must": filter_clauses}} if filter_clauses
            else {"match_all": {}}
        )

        # === Strategy 1: Elasticsearch 8.x+ native RRF ===
        try:
            response = self.es.search(index=self.index, body={
                "retriever": {
                    "rrf": {
                        "retrievers": [
                            # BM25 keyword retriever
                            {
                                "standard": {
                                    "query": {
                                        "bool": {
                                            "must": {
                                                "multi_match": {
                                                    "query": query_text,
                                                    "fields": [
                                                        "name^3",
                                                        "description",
                                                    ],
                                                },
                                            },
                                            "filter": filter_clauses or [],
                                        },
                                    },
                                },
                            },
                            # kNN vector retriever
                            {
                                "knn": {
                                    "field": "embedding",
                                    "query_vector": query_vector,
                                    "k": k * 2,
                                    "num_candidates": k * 10,
                                    "filter": es_filter,
                                },
                            },
                        ],
                        "rank_window_size": k * 3,
                        "rank_constant": 60,
                    },
                },
                "size": k,
                "_source": [
                    "product_id", "name", "brand",
                    "price", "rating",
                ],
            })
            return self._format_response(response)
        except Exception:
            # Fall back to manual RRF for older ES versions
            return self._manual_rrf_search(
                query_text, query_vector,
                keyword_weight, vector_weight,
                k, filter_clauses,
            )

    def _manual_rrf_search(
        self, query_text: str, query_vector: list[float],
        kw_weight: float, vec_weight: float,
        k: int, filter_clauses: list,
    ) -> dict:
        """Manual RRF for Elasticsearch < 8.9."""
        retrieve_size = k * 3

        # Query 1: BM25 keyword search
        kw_response = self.es.search(index=self.index, body={
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["name^3", "description"],
                        },
                    },
                    "filter": filter_clauses or [],
                },
            },
            "size": retrieve_size,
            "_source": [
                "product_id", "name", "brand", "price", "rating",
            ],
        })

        # Query 2: kNN vector search
        vec_response = self.es.search(index=self.index, body={
            "knn": {
                "field": "embedding",
                "query_vector": query_vector,
                "k": retrieve_size,
                "num_candidates": retrieve_size * 5,
            },
            "size": retrieve_size,
            "_source": [
                "product_id", "name", "brand", "price", "rating",
            ],
        })

        # RRF fusion
        RANK_CONSTANT = 60
        rrf_scores = {}
        doc_sources = {}

        for rank, hit in enumerate(kw_response["hits"]["hits"]):
            doc_id = hit["_id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0)
            rrf_scores[doc_id] += kw_weight / (RANK_CONSTANT + rank + 1)
            doc_sources[doc_id] = hit["_source"]

        for rank, hit in enumerate(vec_response["hits"]["hits"]):
            doc_id = hit["_id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0)
            rrf_scores[doc_id] += vec_weight / (RANK_CONSTANT + rank + 1)
            if doc_id not in doc_sources:
                doc_sources[doc_id] = hit["_source"]

        ranked = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:k]

        return {
            "total": len(rrf_scores),
            "results": [
                {
                    "id": doc_id,
                    "rrf_score": round(score, 6),
                    **doc_sources[doc_id],
                }
                for doc_id, score in ranked
            ],
            "method": "manual_rrf",
        }

    def _format_response(self, response: dict) -> dict:
        return {
            "total": response["hits"]["total"]["value"],
            "results": [
                {
                    "id": hit["_id"],
                    "score": hit.get("_score"),
                    **hit["_source"],
                }
                for hit in response["hits"]["hits"]
            ],
            "method": "native_rrf",
        }

    def semantic_rerank(
        self, query_text: str, query_vector: list[float],
        k: int = 20, rerank_top: int = 100,
    ) -> dict:
        """Two-phase: BM25 retrieval then vector reranking.

        Phase 1: BM25 retrieves top-N candidates (fast, high recall)
        Phase 2: Vector similarity reranks candidates (accurate)
        """
        # Phase 1: BM25 candidate retrieval
        candidates = self.es.search(index=self.index, body={
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["name^3", "description"],
                    "fuzziness": "AUTO",
                },
            },
            "size": rerank_top,
            "_source": [
                "product_id", "name", "brand",
                "price", "rating", "embedding",
            ],
        })

        # Phase 2: Rerank by vector similarity
        query_vec = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)

        reranked = []
        for hit in candidates["hits"]["hits"]:
            doc_vec = np.array(
                hit["_source"].get("embedding", []),
                dtype=np.float32,
            )
            if len(doc_vec) > 0:
                doc_norm = np.linalg.norm(doc_vec)
                cosine_sim = float(
                    np.dot(query_vec, doc_vec) / (query_norm * doc_norm)
                ) if query_norm > 0 and doc_norm > 0 else 0
            else:
                cosine_sim = 0

            bm25_score = hit["_score"] or 0
            combined = 0.4 * min(bm25_score / 20, 1.0) + 0.6 * cosine_sim

            source = {k: v for k, v in hit["_source"].items()
                      if k != "embedding"}
            reranked.append({
                "id": hit["_id"],
                "combined_score": round(combined, 4),
                "bm25_score": round(bm25_score, 4),
                "cosine_similarity": round(cosine_sim, 4),
                **source,
            })

        reranked.sort(key=lambda x: x["combined_score"], reverse=True)
        return {
            "total": len(reranked),
            "results": reranked[:k],
            "method": "semantic_rerank",
        }


# === Usage ===
es = Elasticsearch(["http://localhost:9200"])
engine = HybridSearchEngine(es)

# Hybrid search (best quality)
results = engine.hybrid_search(
    query_text="comfortable noise cancelling headphones for travel",
    query_vector=[0.1] * 384,  # from sentence-transformer
    keyword_weight=0.4,
    vector_weight=0.6,
    k=10,
    filters={"brand": ["Sony", "Bose"], "max_price": 400},
)

# Semantic reranking (two-phase)
results = engine.semantic_rerank(
    query_text="headphones for airplane",
    query_vector=[0.1] * 384,
    k=10, rerank_top=100,
)
```

Key patterns:
1. **RRF (Reciprocal Rank Fusion)** -- merges rankings without score normalization: `1/(k+rank)` per retriever; rank_constant=60 is the standard default
2. **Native vs manual RRF** -- ES 8.9+ has built-in `retriever.rrf`; for older versions, execute two queries and merge client-side
3. **HNSW index options** -- `m=16, ef_construction=100` for dense_vector; higher values improve recall at the cost of index size and build time
4. **Semantic reranking** -- BM25 is recall-oriented (fast, catches keyword matches); vector reranking improves precision on top candidates
5. **Weight tuning** -- start with 0.5/0.5 keyword/vector, then adjust based on query type; exact queries (SKU, brand) need more keyword weight, conceptual queries need more vector weight'''
    ),
]
