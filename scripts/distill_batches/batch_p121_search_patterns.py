"""Search — Elasticsearch, Algolia patterns, and search UI."""

PAIRS = [
    (
        "patterns/search-backend",
        "Show search backend patterns: indexing, querying, faceting, autocomplete, and relevance tuning.",
        '''Search backend patterns (Elasticsearch):

```python
from elasticsearch import AsyncElasticsearch
from typing import Any


# --- Index configuration ---

PRODUCT_INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "analysis": {
            "analyzer": {
                "product_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "asciifolding",     # é → e
                        "english_stemmer",  # running → run
                        "synonym_filter",
                    ],
                },
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "edge_ngram_filter"],
                },
            },
            "filter": {
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
                "edge_ngram_filter": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                },
                "synonym_filter": {
                    "type": "synonym",
                    "synonyms": [
                        "laptop, notebook",
                        "phone, mobile, cell",
                        "tv, television",
                    ],
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
                    "keyword": {"type": "keyword"},  # For exact match and sorting
                },
            },
            "description": {"type": "text", "analyzer": "product_analyzer"},
            "category": {"type": "keyword"},
            "brand": {"type": "keyword"},
            "price": {"type": "float"},
            "rating": {"type": "float"},
            "in_stock": {"type": "boolean"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
        },
    },
}


# --- Search service ---

class SearchService:
    def __init__(self, es: AsyncElasticsearch, index: str = "products"):
        self.es = es
        self.index = index

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        sort_by: str = "_score",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Full-text search with filters and facets."""
        must = []
        filter_clauses = []

        # Main text search (multi-field with boosting)
        if query:
            must.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "name^3",          # Name is 3x more important
                        "description",
                        "tags^2",
                        "brand^2",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",   # Typo tolerance
                },
            })

        # Apply filters
        if filters:
            if "category" in filters:
                filter_clauses.append({"term": {"category": filters["category"]}})
            if "brand" in filters:
                filter_clauses.append({"terms": {"brand": filters["brand"]}})
            if "min_price" in filters or "max_price" in filters:
                price_range = {}
                if "min_price" in filters:
                    price_range["gte"] = filters["min_price"]
                if "max_price" in filters:
                    price_range["lte"] = filters["max_price"]
                filter_clauses.append({"range": {"price": price_range}})
            if "in_stock" in filters:
                filter_clauses.append({"term": {"in_stock": filters["in_stock"]}})

        # Build query
        body = {
            "query": {
                "bool": {
                    "must": must or [{"match_all": {}}],
                    "filter": filter_clauses,
                },
            },
            # Faceted aggregations
            "aggs": {
                "categories": {"terms": {"field": "category", "size": 20}},
                "brands": {"terms": {"field": "brand", "size": 30}},
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"to": 25, "key": "Under $25"},
                            {"from": 25, "to": 50, "key": "$25-$50"},
                            {"from": 50, "to": 100, "key": "$50-$100"},
                            {"from": 100, "key": "$100+"},
                        ],
                    },
                },
                "avg_rating": {"avg": {"field": "rating"}},
            },
            # Highlighting
            "highlight": {
                "fields": {
                    "name": {"number_of_fragments": 0},
                    "description": {"fragment_size": 150, "number_of_fragments": 3},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            # Pagination
            "from": (page - 1) * page_size,
            "size": page_size,
        }

        # Sorting
        if sort_by == "price_asc":
            body["sort"] = [{"price": "asc"}, "_score"]
        elif sort_by == "price_desc":
            body["sort"] = [{"price": "desc"}, "_score"]
        elif sort_by == "rating":
            body["sort"] = [{"rating": "desc"}, "_score"]
        elif sort_by == "newest":
            body["sort"] = [{"created_at": "desc"}, "_score"]

        result = await self.es.search(index=self.index, body=body)

        return {
            "total": result["hits"]["total"]["value"],
            "items": [
                {
                    **hit["_source"],
                    "_score": hit["_score"],
                    "_highlights": hit.get("highlight", {}),
                }
                for hit in result["hits"]["hits"]
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
            "page": page,
            "page_size": page_size,
        }

    async def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        """Prefix-based autocomplete suggestions."""
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
                "size": limit,
            },
        )
        return [hit["_source"]["name"] for hit in result["hits"]["hits"]]
```

Search backend patterns:
1. **Multi-field search with boost** — `name^3` weights title matches higher
2. **`fuzziness: "AUTO"`** — automatic typo tolerance based on word length
3. **Faceted aggregations** — category counts, price ranges for filter UI
4. **Edge n-gram analyzer** — autocomplete that matches prefixes (e.g., "lap" → "laptop")
5. **Highlight** — `<mark>` tags show matching text snippets in results'''
    ),
    (
        "patterns/search-ui",
        "Show search UI patterns: debounced input, faceted filtering, infinite scroll, and search analytics.",
        '''Search UI patterns:

```typescript
import { useState, useCallback, useEffect, useRef } from 'react';

// --- Debounced search hook ---

function useDebouncedSearch(delay: number = 300) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), delay);
    return () => clearTimeout(timer);
  }, [query, delay]);

  return { query, setQuery, debouncedQuery };
}


// --- Search with filters and facets ---

interface SearchFilters {
  category?: string;
  brands?: string[];
  priceRange?: { min?: number; max?: number };
  inStock?: boolean;
  sortBy?: string;
}

interface Facet {
  key: string;
  count: number;
}

interface SearchResult {
  total: number;
  items: any[];
  facets: {
    categories: Facet[];
    brands: Facet[];
    priceRanges: Facet[];
  };
}

function useSearch() {
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>({});
  const { query, setQuery, debouncedQuery } = useDebouncedSearch();

  const search = useCallback(async (q: string, f: SearchFilters) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('q', q);
      if (f.category) params.set('category', f.category);
      if (f.brands?.length) params.set('brands', f.brands.join(','));
      if (f.priceRange?.min) params.set('min_price', String(f.priceRange.min));
      if (f.priceRange?.max) params.set('max_price', String(f.priceRange.max));
      if (f.sortBy) params.set('sort', f.sortBy);

      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      setResults(data);
    } finally {
      setLoading(false);
    }
  }, []);

  // Search when query or filters change
  useEffect(() => {
    search(debouncedQuery, filters);
  }, [debouncedQuery, filters, search]);

  const updateFilter = useCallback((key: keyof SearchFilters, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  }, []);

  return { query, setQuery, results, loading, filters, updateFilter };
}


// --- Infinite scroll ---

function useInfiniteScroll(loadMore: () => Promise<void>) {
  const observerRef = useRef<IntersectionObserver>();
  const loadingRef = useRef(false);

  const sentinelRef = useCallback((node: HTMLElement | null) => {
    if (observerRef.current) observerRef.current.disconnect();

    observerRef.current = new IntersectionObserver(async ([entry]) => {
      if (entry.isIntersecting && !loadingRef.current) {
        loadingRef.current = true;
        await loadMore();
        loadingRef.current = false;
      }
    });

    if (node) observerRef.current.observe(node);
  }, [loadMore]);

  return sentinelRef;
}


// --- Search component ---

function SearchPage() {
  const { query, setQuery, results, loading, filters, updateFilter } = useSearch();

  return (
    <div className="flex gap-6">
      {/* Filters sidebar */}
      <aside className="w-64 shrink-0">
        {results?.facets.categories.map(cat => (
          <label key={cat.key} className="flex items-center gap-2">
            <input
              type="radio"
              name="category"
              checked={filters.category === cat.key}
              onChange={() => updateFilter('category', cat.key)}
            />
            <span>{cat.key}</span>
            <span className="text-gray-400 ml-auto">({cat.count})</span>
          </label>
        ))}

        <div className="mt-4">
          <h3>Price Range</h3>
          {results?.facets.priceRanges.map(range => (
            <label key={range.key} className="flex items-center gap-2">
              <input type="checkbox" />
              <span>{range.key} ({range.count})</span>
            </label>
          ))}
        </div>
      </aside>

      {/* Search results */}
      <main className="flex-1">
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search products..."
          className="w-full p-3 border rounded-lg"
        />

        {loading && <div className="animate-pulse">Searching...</div>}

        <p className="text-sm text-gray-500 my-2">
          {results?.total ?? 0} results
        </p>

        <div className="grid grid-cols-3 gap-4">
          {results?.items.map(item => (
            <div key={item.id}>
              <h3 dangerouslySetInnerHTML={{
                __html: item._highlights?.name?.[0] || item.name
              }} />
              <p>{item.price}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
```

Search UI patterns:
1. **Debounced input** — wait 300ms after typing stops before searching
2. **Faceted filters** — show category/brand counts from search aggregations
3. **URL params sync** — persist search state in URL for shareable links
4. **Infinite scroll** — `IntersectionObserver` on sentinel element triggers `loadMore`
5. **Highlighted results** — render `<mark>` tags from search highlight response'''
    ),
]
"""
