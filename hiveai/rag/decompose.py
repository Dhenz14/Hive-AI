"""
Query Decomposition — break complex multi-entity queries into sub-queries.

For queries like "compare tokio vs goroutines for concurrent HTTP servers",
a single embedding may only match one domain well. Decomposition splits this
into 2-3 targeted sub-queries, retrieves for each, and merges via RRF.

Replaces the regex-based entity extraction which misses lowercase/camelCase terms.
"""
import json
import logging
import hashlib
import threading

logger = logging.getLogger(__name__)

from collections import OrderedDict
_decompose_cache: OrderedDict = OrderedDict()
_decompose_cache_lock = threading.Lock()
_DECOMPOSE_CACHE_MAX = 100

_DECOMPOSE_PROMPT = """Break this query into 2-3 independent sub-queries that together answer the original question. Each sub-query should be self-contained and searchable.

Return ONLY a JSON array of strings, nothing else. Example: ["sub-query 1", "sub-query 2"]

Query: {query}"""


def decompose_query(query: str) -> list[str]:
    """
    Break a complex query into 2-3 sub-queries via fast model.
    Returns the original query as a single-element list if decomposition fails.
    Cost: ~150ms (1 fast LLM call), cached per query.
    """
    cache_key = hashlib.md5(query.lower().strip().encode()).hexdigest()

    with _decompose_cache_lock:
        if cache_key in _decompose_cache:
            return _decompose_cache[cache_key]

    try:
        from hiveai.llm.client import fast

        result = fast(_DECOMPOSE_PROMPT.format(query=query), max_tokens=200)
        if not result:
            return [query]

        # Parse JSON array from response (handle markdown code fences)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        sub_queries = json.loads(result)
        if not isinstance(sub_queries, list) or len(sub_queries) < 2:
            return [query]

        # Cap at 3 sub-queries, filter empty strings
        sub_queries = [q.strip() for q in sub_queries[:3] if q.strip()]
        if not sub_queries:
            return [query]

        with _decompose_cache_lock:
            if cache_key in _decompose_cache:
                _decompose_cache.move_to_end(cache_key)
            _decompose_cache[cache_key] = sub_queries
            while len(_decompose_cache) > _DECOMPOSE_CACHE_MAX:
                _decompose_cache.popitem(last=False)

        logger.info(f"Query decomposed: '{query[:50]}' → {len(sub_queries)} sub-queries")
        return sub_queries

    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"Query decomposition failed (using original): {e}")
        return [query]


def should_decompose(query: str, difficulty: str = "") -> bool:
    """
    Decide whether to decompose a query.
    Only for complex queries with multiple entities or comparison patterns.
    """
    if difficulty and difficulty not in ("complex", "moderate"):
        return False

    q = query.lower()
    # Comparison patterns
    if any(p in q for p in [" vs ", " versus ", " compare ", " difference between ", " or "]):
        return True
    # Multi-entity indicators (3+ significant words after stop-word removal)
    words = [w for w in q.split() if len(w) > 3]
    if len(words) >= 8:
        return True

    return False
