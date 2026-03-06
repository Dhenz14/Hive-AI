"""Thinking-trace pairs: Elasticsearch debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My Elasticsearch index has thousands of dynamically created fields and performance is degrading. Queries are slow and I'm getting "Limit of total fields [1000] has been exceeded" errors. How do I fix the mapping explosion?''',
        r'''<think>
Thousands of dynamically created fields and hitting the 1000 field limit. This is a mapping explosion -- but why is it happening?

The most likely cause: the user is indexing documents with dynamic keys. For example, storing HTTP headers as `header_x_forwarded_for`, `header_x_request_id`, etc. -- each unique header name becomes a new field in the mapping. Or maybe they are storing user-defined metadata as top-level fields. Elasticsearch's default `dynamic: true` setting creates a new mapping entry for every new field it sees.

Could this be fixed by just raising the field limit? You could set `index.mapping.total_fields.limit` to 10000, but that is treating the symptom, not the cause. Each field mapping lives in the cluster state, which is replicated to every node. Thousands of fields bloat the cluster state, slow down mapping updates, and increase memory usage across the cluster. So raising the limit is a temporary bandage that makes things worse over time.

What about `dynamic: false`? That would silently accept unknown fields without indexing them -- the data is stored in `_source` but not searchable. That might be fine if they only need to search on known fields. But if they need to search dynamic fields too, they would need the `flattened` type, which stores all nested keys as keywords in a single field.

Actually, the best approach depends on the query patterns. If they need full-text search on dynamic fields, `flattened` is limiting because it only supports keyword-level queries (no full-text analysis). In that case, restructuring the data as key-value pairs with a nested type gives more flexibility, but nested queries are more complex and slower.

The tradeoff: `flattened` is simple and efficient but limited to exact matches. Key-value nested arrays are flexible but slower for queries. `dynamic: strict` is the safest but requires knowing all fields upfront. I would recommend `flattened` for metadata and headers, `dynamic: strict` for the main document fields.
</think>

Mapping explosion occurs when dynamic mapping creates a new field for every unique key. Here is how to diagnose and fix it:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://localhost:9200"])
INDEX = "my-index"

# ============================================================
# DIAGNOSIS: Check current mapping size
# ============================================================

def diagnose_mapping(index):
    """Count fields and identify mapping explosion."""
    mapping = es.indices.get_mapping(index=index)
    properties = mapping[index]["mappings"].get("properties", {})

    def count_fields(props, prefix=""):
        count = 0
        for name, config in props.items():
            count += 1
            if "properties" in config:
                count += count_fields(config["properties"], f"{prefix}{name}.")
        return count

    total = count_fields(properties)
    print(f"Total fields in {index}: {total}")

    # Find field name patterns suggesting dynamic keys
    suspicious = []
    for name in properties:
        if len(name) > 50 or name.startswith("header_") or "-" in name:
            suspicious.append(name)
    if suspicious:
        print(f"Suspicious dynamic fields: {suspicious[:10]}...")

    return total

diagnose_mapping(INDEX)

# ============================================================
# FIX 1: Use flattened field type (best for arbitrary JSON)
# ============================================================

# Delete and recreate index with proper mapping
es.indices.create(
    index="logs-fixed-v1",
    body={
        "mappings": {
            "dynamic": "strict",  # Reject unknown fields
            "properties": {
                "timestamp": {"type": "date"},
                "message": {"type": "text"},
                "level": {"type": "keyword"},
                # Use "flattened" for arbitrary metadata
                # This stores all sub-fields as keywords in a single field
                "metadata": {"type": "flattened"},
                "headers": {"type": "flattened"},
            },
        },
    },
)

# Now you can store any structure in metadata without mapping explosion
es.index(index="logs-fixed-v1", body={
    "timestamp": "2024-01-15T10:30:00Z",
    "message": "Request received",
    "level": "info",
    "metadata": {
        "request_id": "abc-123",
        "user_agent": "Mozilla/5.0",
        "custom_header_x_trace_id": "xyz-789",
        "any_dynamic_key": "any_value",
    },
})
# Only 4 field mappings, not 4 + N dynamic fields!

# ============================================================
# FIX 2: Restructure as key-value pairs (nested)
# ============================================================

es.indices.create(
    index="logs-fixed-v2",
    body={
        "mappings": {
            "properties": {
                "timestamp": {"type": "date"},
                "message": {"type": "text"},
                # Instead of dynamic fields, use a nested array
                "attributes": {
                    "type": "nested",
                    "properties": {
                        "key": {"type": "keyword"},
                        "value": {"type": "keyword"},
                    },
                },
            },
        },
    },
)

# Convert dynamic keys to key-value pairs
es.index(index="logs-fixed-v2", body={
    "timestamp": "2024-01-15T10:30:00Z",
    "message": "Request received",
    "attributes": [
        {"key": "request_id", "value": "abc-123"},
        {"key": "user_agent", "value": "Mozilla/5.0"},
        {"key": "trace_id", "value": "xyz-789"},
    ],
})

# Query key-value pairs with nested query
result = es.search(index="logs-fixed-v2", body={
    "query": {
        "nested": {
            "path": "attributes",
            "query": {
                "bool": {
                    "must": [
                        {"term": {"attributes.key": "request_id"}},
                        {"term": {"attributes.value": "abc-123"}},
                    ],
                },
            },
        },
    },
})

# ============================================================
# FIX 3: Disable dynamic mapping entirely
# ============================================================

es.indices.create(
    index="logs-strict",
    body={
        "mappings": {
            # "strict" rejects documents with unknown fields
            # "false" silently ignores unknown fields (stores but not indexed)
            "dynamic": "false",
            "properties": {
                "timestamp": {"type": "date"},
                "message": {"type": "text"},
                "level": {"type": "keyword"},
            },
        },
    },
)

# ============================================================
# FIX 4: Use runtime fields for occasional queries
# ============================================================

# Store raw JSON as text, use runtime fields for ad-hoc queries
es.indices.create(
    index="logs-runtime",
    body={
        "mappings": {
            "properties": {
                "timestamp": {"type": "date"},
                "message": {"type": "text"},
                "raw_metadata": {"type": "text", "index": False},
            },
        },
    },
)

# Query with runtime field (computed at query time)
result = es.search(index="logs-runtime", body={
    "runtime_mappings": {
        "extracted_request_id": {
            "type": "keyword",
            "script": {
                "source": """
                    String raw = doc['raw_metadata'].value;
                    // Parse and extract the field at query time
                    emit(raw.contains('abc-123') ? 'abc-123' : '');
                """,
            },
        },
    },
    "query": {
        "term": {"extracted_request_id": "abc-123"},
    },
})
```

**Prevention checklist:**
1. Always set `"dynamic": "strict"` or `"dynamic": "false"` on production indices
2. Use `flattened` type for arbitrary JSON metadata
3. Set `index.mapping.total_fields.limit` explicitly (do not just raise it blindly)
4. Monitor field count: `GET /my-index/_mapping` and count properties regularly
5. Use index templates to enforce mapping rules on new indices''',
    ),
    (
        "thinking/debugging",
        r'''My Elasticsearch search results have poor relevance. Exact matches are ranked lower than partial matches, and common words dominate the scoring. How do I improve search relevance?

es.search(index="products", body={
    "query": {
        "match": {
            "name": "blue cotton shirt"
        }
    }
})
# Returns "Red Shirt with Cotton blend" before "Blue Cotton Shirt"''',
        r'''<think>
The user searches "blue cotton shirt" but "Red Shirt with Cotton blend" ranks above "Blue Cotton Shirt". That is clearly wrong -- the exact match should be first. Let me think about why BM25 would score it this way.

BM25 scoring depends on term frequency, inverse document frequency, and field length normalization. "Red Shirt with Cotton blend" has 5 tokens; "Blue Cotton Shirt" has 3 tokens. BM25 normalizes by field length, so shorter documents get a slight boost per matching term. Both documents match "shirt" and "cotton" (2 out of 3 query terms). But the first document also contains more total tokens, so the term frequency of "shirt" and "cotton" relative to field length is actually higher in the second document. Hmm, that should favor "Blue Cotton Shirt" then.

Wait, could it be IDF? "shirt" and "cotton" might appear in many documents (low IDF), while "blue" has higher IDF but only matches the second document. Actually, the default `match` query uses OR logic -- it returns documents matching ANY term. So "Red Shirt with Cotton blend" matches 2 of 3 terms, and "Blue Cotton Shirt" matches 3 of 3. With 3 matching terms, the second should score higher...

Unless the index has a lot of documents with "blue" in them, making "blue" have low IDF. Or maybe the first document has other field matches (like a description field) contributing to the score via a multi_match or copy_to.

Actually, the fundamental problem is simpler: the default `match` query does not differentiate between "all terms matched" and "some terms matched" beyond the additive BM25 scores. And there is no boost for an exact phrase match. The fix is a multi-tier bool query with should clauses: exact keyword match (highest boost), phrase match, all-terms-and match, any-terms-or match. That way "Blue Cotton Shirt" gets huge boosts from the exact and phrase tiers that "Red Shirt with Cotton blend" cannot match.
</think>

Poor search relevance in Elasticsearch usually requires a multi-layered scoring approach. Here is how to fix it:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://localhost:9200"])

# ============================================================
# STEP 1: Better field mapping with multiple analyzers
# ============================================================

es.indices.create(
    index="products-v2",
    body={
        "settings": {
            "analysis": {
                "analyzer": {
                    "standard_lowercase": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "trim"],
                    },
                    "edge_ngram_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "edge_ngram_filter"],
                    },
                },
                "filter": {
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
                    "analyzer": "standard_lowercase",
                    "fields": {
                        # Exact keyword match (highest boost)
                        "keyword": {"type": "keyword"},
                        # Raw text with no analysis (phrase matching)
                        "raw": {
                            "type": "text",
                            "analyzer": "standard_lowercase",
                        },
                    },
                },
                "description": {"type": "text"},
                "category": {"type": "keyword"},
                "price": {"type": "float"},
                "popularity": {"type": "integer"},
            },
        },
    },
)

# ============================================================
# STEP 2: Multi-tier relevance query
# ============================================================

def search_products(query_text):
    """Search with tiered relevance scoring."""
    return es.search(
        index="products-v2",
        body={
            "query": {
                "bool": {
                    # All should clauses contribute to score
                    "should": [
                        # Tier 1: Exact match (highest boost)
                        {
                            "term": {
                                "name.keyword": {
                                    "value": query_text,
                                    "boost": 10,
                                },
                            },
                        },
                        # Tier 2: Exact phrase match
                        {
                            "match_phrase": {
                                "name": {
                                    "query": query_text,
                                    "boost": 5,
                                },
                            },
                        },
                        # Tier 3: All terms must match
                        {
                            "match": {
                                "name": {
                                    "query": query_text,
                                    "operator": "and",
                                    "boost": 3,
                                },
                            },
                        },
                        # Tier 4: Any term matches (broadest)
                        {
                            "match": {
                                "name": {
                                    "query": query_text,
                                    "operator": "or",
                                    "minimum_should_match": "50%",
                                    "boost": 1,
                                },
                            },
                        },
                        # Tier 5: Description match (lowest boost)
                        {
                            "match": {
                                "description": {
                                    "query": query_text,
                                    "boost": 0.5,
                                },
                            },
                        },
                    ],
                    "minimum_should_match": 1,
                },
            },
            # Debug: explain scoring
            "explain": False,
        },
    )

results = search_products("blue cotton shirt")
for hit in results["hits"]["hits"]:
    print(f"  Score: {hit['_score']:.2f} | {hit['_source']['name']}")

# ============================================================
# STEP 3: Function score for business logic boosting
# ============================================================

def search_with_business_logic(query_text):
    """Combine text relevance with business metrics."""
    return es.search(
        index="products-v2",
        body={
            "query": {
                "function_score": {
                    "query": {
                        "bool": {
                            "should": [
                                {"match_phrase": {"name": {"query": query_text, "boost": 5}}},
                                {"match": {"name": {"query": query_text, "operator": "and", "boost": 3}}},
                                {"match": {"name": {"query": query_text, "boost": 1}}},
                            ],
                            "minimum_should_match": 1,
                        },
                    },
                    "functions": [
                        # Boost by popularity (log scale)
                        {
                            "field_value_factor": {
                                "field": "popularity",
                                "factor": 1.2,
                                "modifier": "log1p",
                                "missing": 1,
                            },
                        },
                        # Boost items in stock
                        {
                            "filter": {"term": {"in_stock": True}},
                            "weight": 2,
                        },
                    ],
                    # Multiply text score by function scores
                    "score_mode": "multiply",
                    "boost_mode": "multiply",
                },
            },
        },
    )

# ============================================================
# STEP 4: Debug relevance with explain API
# ============================================================

def explain_score(index, doc_id, query_text):
    """Understand why a document got its score."""
    result = es.explain(
        index=index,
        id=doc_id,
        body={
            "query": {
                "match": {"name": query_text},
            },
        },
    )
    print(f"Score: {result['explanation']['value']}")
    print(f"Explanation: {result['explanation']['description']}")
    for detail in result["explanation"].get("details", []):
        print(f"  - {detail['description']}: {detail['value']}")

# explain_score("products-v2", "doc-id-here", "blue cotton shirt")
```

**Key relevance improvements:**
1. Use tiered `should` clauses: exact > phrase > all-terms > any-terms
2. Add a `.keyword` sub-field for exact match boosting
3. Use `function_score` to incorporate business metrics (popularity, recency)
4. Use the `_explain` API to understand why specific documents rank where they do
5. Tune `minimum_should_match` to control how many query terms must appear''',
    ),
    (
        "thinking/debugging",
        r'''My Elasticsearch bulk indexing is failing with some documents rejected while others succeed. I'm getting errors like "mapper_parsing_exception" and "version_conflict_engine_exception" but the error handling is difficult because bulk returns partial success. How do I handle bulk indexing failures properly?''',
        r'''<think>
Bulk indexing with partial failures -- some documents succeed, some fail. The tricky part is that `helpers.bulk()` by default raises an exception on the first error, which means the caller does not know which documents succeeded and which failed.

Let me think about the error types. A `mapper_parsing_exception` means a document has a field value that does not match the mapping -- like sending "not_a_number" to a float field. This is a permanent error; retrying would fail the same way. A `version_conflict_engine_exception` means another process updated the document between the read and write -- this might succeed on retry if using optimistic concurrency. An `es_rejected_execution_exception` means the thread pool is full -- that is definitely worth retrying after a backoff.

Could you just use `raise_on_error=False` to get all errors? Yes, that returns a tuple of (success_count, error_list). But the error list items do not always contain the original document data, so you cannot easily reconstruct what to retry.

Actually, I think the right approach is a wrapper that: (1) calls bulk with `raise_on_error=False`, (2) classifies each error as retryable or permanent, (3) retries the retryable ones with exponential backoff, and (4) collects the permanent failures into a dead letter queue for manual review. The tradeoff is complexity -- this is a lot more code than just calling `helpers.bulk()` -- but for production systems indexing millions of documents, silently losing data is not acceptable.

One more thing: connection-level failures (Redis/ES node goes down mid-batch) need separate handling because the entire batch fails, not individual documents. Those should be retried as a whole batch.
</think>

Elasticsearch bulk operations return per-item success/failure status. Here is how to handle partial failures properly:

```python
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import (
    ConnectionError,
    ConnectionTimeout,
    TransportError,
)
import logging
import json
import time

logger = logging.getLogger(__name__)
es = Elasticsearch(["http://localhost:9200"])

# ============================================================
# PROBLEM: Naive bulk indexing loses failed documents
# ============================================================

# BAD: No error handling
# helpers.bulk(es, documents)  # Throws on first error

# LESS BAD: But still loses context about which docs failed
# success, errors = helpers.bulk(es, documents, raise_on_error=False)

# ============================================================
# FIX: Comprehensive bulk indexing with error handling
# ============================================================

class BulkIndexer:
    """Resilient bulk indexer with retry and dead-letter handling."""

    # Errors that are worth retrying
    RETRYABLE_ERRORS = {
        "es_rejected_execution_exception",  # Thread pool full
        "cluster_block_exception",          # Cluster read-only
        "timeout",                          # Operation timed out
    }

    # Errors that should not be retried (data problem)
    PERMANENT_ERRORS = {
        "mapper_parsing_exception",      # Type mismatch
        "illegal_argument_exception",    # Bad field value
        "strict_dynamic_mapping_exception",  # Unknown field
    }

    def __init__(self, es_client, index, batch_size=500, max_retries=3):
        self.es = es_client
        self.index = index
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dead_letter = []  # Documents that permanently failed
        self.stats = {
            "total": 0, "success": 0,
            "retried": 0, "failed": 0,
        }

    def index_documents(self, documents):
        """Index documents in batches with error handling."""
        batch = []
        for doc in documents:
            batch.append(doc)
            if len(batch) >= self.batch_size:
                self._index_batch(batch)
                batch = []
        if batch:
            self._index_batch(batch)

        logger.info(
            "Indexing complete: %d total, %d success, %d retried, %d failed",
            self.stats["total"], self.stats["success"],
            self.stats["retried"], self.stats["failed"],
        )
        return self.stats, self.dead_letter

    def _index_batch(self, documents, attempt=0):
        """Index a batch with retry logic."""
        actions = []
        for doc in documents:
            action = {
                "_index": self.index,
                "_source": doc,
            }
            if "_id" in doc:
                action["_id"] = doc.pop("_id")
            actions.append(action)

        self.stats["total"] += len(actions)

        try:
            success, errors = helpers.bulk(
                self.es,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
                chunk_size=len(actions),
                request_timeout=60,
            )
            self.stats["success"] += success

            if errors:
                self._handle_errors(errors, documents, attempt)

        except (ConnectionError, ConnectionTimeout) as e:
            # Entire batch failed due to connection issue
            logger.warning("Connection error on batch: %s", e)
            if attempt < self.max_retries:
                wait = 2 ** attempt
                logger.info("Retrying entire batch in %ds...", wait)
                time.sleep(wait)
                self._index_batch(documents, attempt + 1)
            else:
                logger.error("Batch failed after %d retries", self.max_retries)
                for doc in documents:
                    self.dead_letter.append({
                        "document": doc,
                        "error": str(e),
                        "error_type": "connection_error",
                    })
                self.stats["failed"] += len(documents)

    def _handle_errors(self, errors, documents, attempt):
        """Classify errors as retryable or permanent."""
        retry_docs = []
        for error_item in errors:
            # Extract error details
            op_type = list(error_item.keys())[0]  # "index", "create", etc.
            error_info = error_item[op_type]
            error_type = error_info.get("error", {}).get("type", "unknown")
            error_reason = error_info.get("error", {}).get("reason", "")
            doc_id = error_info.get("_id", "unknown")

            if error_type in self.RETRYABLE_ERRORS and attempt < self.max_retries:
                logger.warning(
                    "Retryable error for doc %s: %s", doc_id, error_reason
                )
                # Find the original document and queue for retry
                retry_docs.append(error_info.get("_source", {}))
                self.stats["retried"] += 1
            else:
                logger.error(
                    "Permanent error for doc %s: %s - %s",
                    doc_id, error_type, error_reason,
                )
                self.dead_letter.append({
                    "document_id": doc_id,
                    "error_type": error_type,
                    "error_reason": error_reason,
                })
                self.stats["failed"] += 1

        if retry_docs:
            wait = 2 ** attempt
            time.sleep(wait)
            self._index_batch(retry_docs, attempt + 1)

# ============================================================
# USAGE
# ============================================================

indexer = BulkIndexer(es, index="products", batch_size=500, max_retries=3)

documents = [
    {"_id": "1", "name": "Blue Shirt", "price": 29.99},
    {"_id": "2", "name": "Red Hat", "price": "not_a_number"},  # Will fail
    {"_id": "3", "name": "Green Pants", "price": 49.99},
]

stats, dead_letters = indexer.index_documents(documents)
print(f"Stats: {stats}")
print(f"Dead letters: {len(dead_letters)}")
for dl in dead_letters:
    print(f"  Failed: {dl}")
```

**Key patterns:**
1. Always use `raise_on_error=False` with `helpers.bulk()` to handle partial failures
2. Classify errors as retryable (thread pool, timeout) vs permanent (bad data)
3. Implement exponential backoff for retryable errors
4. Collect dead letters for investigation and potential manual fix
5. Log per-document error details for debugging mapping issues''',
    ),
    (
        "thinking/debugging",
        r'''My Elasticsearch cluster has unassigned shards and some indices are in yellow or red status. How do I diagnose and fix shard allocation problems?

GET _cluster/health shows:
{
  "status": "yellow",
  "number_of_nodes": 3,
  "unassigned_shards": 5,
  "active_primary_shards": 20,
  "active_shards": 35
}''',
        r'''<think>
Yellow cluster health with 5 unassigned shards. Yellow means all primaries are assigned but some replicas are not. The cluster can serve reads and writes, but it is not fully redundant.

First question: is this a 3-node cluster with replicas configured correctly? They have 3 nodes, 20 primary shards, and 35 active shards. If each index has 1 replica, there should be 40 shards total (20 primary + 20 replica). 35 active + 5 unassigned = 40 total. So there are 5 replica shards that cannot be allocated.

Why would replicas fail to allocate on a 3-node cluster? Elasticsearch will not place a primary and its replica on the same node. With 3 nodes and 20 primaries, the replicas should distribute fine -- unless some nodes are out of disk space.

Could it be the disk watermark? Elasticsearch has three watermark levels: low (85%) stops allocating new shards to that node, high (90%) starts moving shards away, flood stage (95%) makes indices read-only. If one or two nodes are above the low watermark, replicas cannot be placed there, and if all valid target nodes are full, the replicas stay unassigned.

Another possibility: someone disabled allocation during maintenance and forgot to re-enable it. `cluster.routing.allocation.enable` set to "none" or "primaries" would prevent replica allocation.

Or it could be allocation awareness rules -- if the cluster has zone awareness configured and one zone lost a node, Elasticsearch would refuse to put both copies in the same zone.

The diagnostic approach should be: (1) check `_cluster/allocation/explain` for the specific reason each shard is unassigned, (2) check disk usage per node, (3) check cluster settings for any allocation restrictions. The fix depends on the cause -- disk full requires cleanup, missing nodes require reducing replicas, disabled allocation just needs re-enabling.
</think>

Unassigned shards in Elasticsearch have specific causes that can be diagnosed systematically. Here is the process:

```python
from elasticsearch import Elasticsearch
import json

es = Elasticsearch(["http://localhost:9200"])

# ============================================================
# STEP 1: Find which shards are unassigned and why
# ============================================================

def diagnose_unassigned_shards():
    """Identify all unassigned shards and their allocation failure reasons."""

    # List all unassigned shards
    shards = es.cat.shards(format="json", h="index,shard,prirep,state,node,unassigned.reason")
    unassigned = [s for s in shards if s["state"] == "UNASSIGNED"]

    print(f"Found {len(unassigned)} unassigned shards:")
    for shard in unassigned:
        print(f"  Index: {shard['index']}, "
              f"Shard: {shard['shard']}, "
              f"Type: {'Primary' if shard['prirep'] == 'p' else 'Replica'}, "
              f"Reason: {shard.get('unassigned.reason', 'unknown')}")

    # Get detailed explanation for the first unassigned shard
    if unassigned:
        explain = es.cluster.allocation_explain(body={
            "index": unassigned[0]["index"],
            "shard": int(unassigned[0]["shard"]),
            "primary": unassigned[0]["prirep"] == "p",
        })
        print(f"\nDetailed explanation for {unassigned[0]['index']}[{unassigned[0]['shard']}]:")
        print(f"  Allocate decision: {explain.get('allocate_explanation', 'N/A')}")

        # Show per-node decisions
        for node_decision in explain.get("node_allocation_decisions", []):
            node_name = node_decision["node_name"]
            decision = node_decision["deciders"]
            for decider in decision:
                if decider["decision"] == "NO":
                    print(f"  Node {node_name}: REJECTED by {decider['decider']} - {decider['explanation']}")

    return unassigned

unassigned = diagnose_unassigned_shards()

# ============================================================
# STEP 2: Check common causes
# ============================================================

def check_disk_space():
    """Check if disk watermarks are blocking allocation."""
    nodes = es.cat.nodes(format="json", h="name,disk.used_percent,disk.total,disk.used")
    print("\nDisk usage per node:")
    for node in nodes:
        pct = float(node.get("disk.used_percent", 0))
        status = "OK"
        if pct > 85:
            status = "WARNING (low watermark)"
        if pct > 90:
            status = "CRITICAL (high watermark)"
        if pct > 95:
            status = "FLOOD STAGE (read-only!)"
        print(f"  {node['name']}: {pct:.1f}% used ({node.get('disk.used', '?')}/{node.get('disk.total', '?')}) - {status}")

def check_allocation_settings():
    """Check if allocation is disabled or filtered."""
    settings = es.cluster.get_settings(flat_settings=True, include_defaults=False)
    print("\nCluster allocation settings:")
    for key, value in settings.get("persistent", {}).items():
        if "allocation" in key:
            print(f"  {key}: {value}")
    for key, value in settings.get("transient", {}).items():
        if "allocation" in key:
            print(f"  {key}: {value}")

check_disk_space()
check_allocation_settings()

# ============================================================
# STEP 3: Apply fixes based on the cause
# ============================================================

# FIX A: Disk watermark reached -- clear space or adjust watermarks
es.cluster.put_settings(body={
    "persistent": {
        # Raise watermarks temporarily (NOT a long-term fix)
        "cluster.routing.allocation.disk.watermark.low": "90%",
        "cluster.routing.allocation.disk.watermark.high": "95%",
        "cluster.routing.allocation.disk.watermark.flood_stage": "97%",
    },
})

# FIX B: Not enough nodes for replicas
# If you have 1 node but replicas=1, reduce replicas to 0
es.indices.put_settings(
    index="my-index",
    body={"index": {"number_of_replicas": 0}},
)

# FIX C: Allocation was disabled (common after maintenance)
es.cluster.put_settings(body={
    "persistent": {
        "cluster.routing.allocation.enable": "all",  # Re-enable
    },
})

# FIX D: Force reroute for stuck shards
es.cluster.reroute(body={
    "commands": [
        {
            "allocate_replica": {
                "index": "my-index",
                "shard": 0,
                "node": "node-2",
            },
        },
    ],
})

# FIX E: For red index with lost primary -- accept data loss
# WARNING: This means the shard data is gone
es.cluster.reroute(body={
    "commands": [
        {
            "allocate_empty_primary": {
                "index": "my-index",
                "shard": 0,
                "node": "node-1",
                "accept_data_loss": True,  # Last resort!
            },
        },
    ],
})

# ============================================================
# STEP 4: Preventive monitoring
# ============================================================

def monitor_cluster():
    """Regular health check for shard allocation."""
    health = es.cluster.health()
    status = health["status"]
    unassigned = health["unassigned_shards"]

    if status == "red":
        print("CRITICAL: Primary shards missing -- data loss risk!")
    elif status == "yellow":
        print(f"WARNING: {unassigned} replica shards unassigned")
    else:
        print("OK: All shards allocated")

    # Check for indices with too many shards
    indices = es.cat.indices(format="json", h="index,pri,rep,store.size")
    for idx in indices:
        pri = int(idx.get("pri", 0))
        if pri > 5:
            print(f"  Warning: {idx['index']} has {pri} primary shards (consider reducing)")

monitor_cluster()
```

**Common causes and fixes summary:**
1. **Disk full** (85%+): Delete old indices, increase disk, adjust watermarks
2. **Not enough nodes**: Reduce `number_of_replicas` to match node count minus 1
3. **Allocation disabled**: Set `cluster.routing.allocation.enable` to "all"
4. **Node left cluster**: Wait for automatic recovery or force reroute
5. **Red status**: Use `allocate_empty_primary` only as a last resort (data loss)''',
    ),
    (
        "thinking/debugging",
        r'''My Elasticsearch queries are timing out on large indices. I get "SearchPhaseExecutionException: all shards failed" with timeout errors. The index has 50 million documents. How do I optimize query performance?''',
        r'''<think>
50 million documents and all shards failing with timeouts. That is a lot of docs but should not be unmanageable for Elasticsearch. Let me think about what could cause timeouts at this scale.

First thought: what kind of query are they running? A simple term or match query on 50M docs should be fast (milliseconds). But a leading wildcard like `*shirt*` would scan every term in the inverted index -- that is brutal at scale. Or deep pagination with `from: 100000, size: 10` -- ES has to score and sort 100,010 documents across all shards, then discard 100,000 of them.

Could it be a shard sizing issue? If the index has too many small shards, the overhead of querying each shard (thread scheduling, merging results) adds up. Conversely, if it has too few shards that are very large (100GB+), individual shard queries take too long. The sweet spot is 10-50 GB per shard.

What about aggregations? A terms aggregation on a high-cardinality text field across 50M docs would be very expensive because it needs to build the full term list in memory. Using keyword fields with the `execution_hint: map` or reducing the aggregation scope with filters would help.

Actually, I should also consider whether the query uses scoring where it does not need to. If they are filtering (e.g., "show me all products in category X with price > 50"), using a bool filter context instead of must context skips the scoring phase entirely and enables caching. Filters are dramatically faster than scoring queries for large result sets.

The other big win: `_source` filtering. If the documents are large (many fields, nested objects), returning the full `_source` for thousands of results transfers a lot of data. Limiting `_source` to only the needed fields reduces both memory and network overhead.

I would start by profiling the slow query with `"profile": true` to see which phase is taking the most time -- the query phase (scoring/matching) or the fetch phase (retrieving documents).
</think>

Query timeouts on 50M+ document indices require optimization at multiple levels. Here are the key fixes:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://localhost:9200"], timeout=30)

INDEX = "large-index"

# ============================================================
# FIX 1: Add explicit query timeouts
# ============================================================

# Always set a timeout to prevent runaway queries
result = es.search(
    index=INDEX,
    body={
        "timeout": "10s",  # Fail fast instead of hanging
        "query": {"match": {"title": "important query"}},
    },
    request_timeout=15,  # HTTP-level timeout
)

if result.get("timed_out"):
    print("WARNING: Query timed out -- results are partial")

# ============================================================
# FIX 2: Avoid expensive query patterns
# ============================================================

# BAD: Leading wildcard scans every term in the index
# {"wildcard": {"name": "*shirt*"}}

# GOOD: Use match or prefix instead
result = es.search(index=INDEX, body={
    "query": {
        "bool": {
            "should": [
                {"match": {"name": "shirt"}},
                {"prefix": {"name.keyword": "shirt"}},
            ],
        },
    },
})

# BAD: Script queries are slow on large indices
# {"script": {"source": "doc['price'].value * 2 > params.threshold"}}

# GOOD: Use range queries with precomputed fields
result = es.search(index=INDEX, body={
    "query": {"range": {"price": {"gt": 50}}},
})

# BAD: Deep pagination with from/size
# {"from": 100000, "size": 10}  # Reads 100010 docs!

# GOOD: Use search_after for deep pagination
result = es.search(index=INDEX, body={
    "size": 100,
    "sort": [{"_score": "desc"}, {"_id": "asc"}],
    "query": {"match": {"title": "shirt"}},
})

# For next page, use the last document's sort values
last_sort = result["hits"]["hits"][-1]["sort"]
next_page = es.search(index=INDEX, body={
    "size": 100,
    "sort": [{"_score": "desc"}, {"_id": "asc"}],
    "query": {"match": {"title": "shirt"}},
    "search_after": last_sort,
})

# ============================================================
# FIX 3: Optimize index structure
# ============================================================

# Check shard sizes -- ideal shard size is 10-50 GB
shards = es.cat.shards(index=INDEX, format="json", h="shard,store")
for shard in shards:
    print(f"Shard {shard['shard']}: {shard.get('store', 'N/A')}")

# If shards are too large, reindex with more primary shards
# If shards are too small (< 1 GB), reduce shard count

# Force merge to reduce segment count (run during low traffic)
es.indices.forcemerge(
    index=INDEX,
    max_num_segments=1,  # One segment per shard (best query perf)
    request_timeout=600,
)

# ============================================================
# FIX 4: Use filter context for non-scoring queries
# ============================================================

# Filters are cached and skip scoring (much faster)
result = es.search(index=INDEX, body={
    "query": {
        "bool": {
            # Scoring query (expensive)
            "must": [
                {"match": {"title": "shirt"}},
            ],
            # Filter context (cached, no scoring)
            "filter": [
                {"term": {"category": "clothing"}},
                {"range": {"price": {"gte": 10, "lte": 100}}},
                {"term": {"in_stock": True}},
            ],
        },
    },
})

# ============================================================
# FIX 5: Limit returned fields and source
# ============================================================

result = es.search(index=INDEX, body={
    "query": {"match": {"title": "shirt"}},
    # Only return specific fields (reduces network/memory)
    "_source": ["title", "price", "category"],
    # Or disable source entirely if you only need IDs
    # "_source": False,
    "size": 20,
})

# ============================================================
# FIX 6: Profile slow queries
# ============================================================

result = es.search(index=INDEX, body={
    "profile": True,  # Enable query profiling
    "query": {"match": {"title": "shirt"}},
    "size": 1,
})

# Analyze profile output
for shard_profile in result.get("profile", {}).get("shards", []):
    for search in shard_profile.get("searches", []):
        for query in search.get("query", []):
            print(f"Query type: {query['type']}")
            print(f"Time: {query['time_in_nanos'] / 1e6:.1f} ms")
            print(f"Description: {query['description']}")

# ============================================================
# FIX 7: Use index sorting for range queries
# ============================================================

# If you frequently filter by date, sort the index by date
es.indices.create(
    index="logs-sorted",
    body={
        "settings": {
            "index": {
                "sort.field": "timestamp",
                "sort.order": "desc",
            },
        },
        "mappings": {
            "properties": {
                "timestamp": {"type": "date"},
                "message": {"type": "text"},
            },
        },
    },
)
# Range queries on the sort field can skip entire segments
```

**Performance checklist:**
1. Always set `"timeout"` in queries to fail fast
2. Use `filter` context for non-scoring conditions (cached)
3. Avoid leading wildcards, script queries, and deep pagination
4. Use `search_after` instead of `from`/`size` for deep pagination
5. Keep shard size between 10-50 GB; run `forcemerge` during off-peak
6. Use `_source` filtering to reduce response size
7. Profile slow queries with `"profile": true`''',
    ),
]
