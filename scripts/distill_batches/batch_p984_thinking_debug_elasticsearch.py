"""Thinking-trace pairs: Elasticsearch debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My Elasticsearch index has thousands of dynamically created fields and performance is degrading. Queries are slow and I'm getting "Limit of total fields [1000] has been exceeded" errors. How do I fix the mapping explosion?''',
        r'''<think>
Mapping explosion happens when Elasticsearch creates a new field mapping for every unique key it encounters in documents. This is common with:
1. Log data with dynamic keys (e.g., HTTP headers as field names)
2. User-defined metadata stored as flat fields
3. Nested objects with unpredictable keys

Each field mapping consumes memory in the cluster state. Too many fields slow down queries, increase memory usage, and can hit the default limit of 1000 fields.

Solutions:
1. Disable dynamic mapping
2. Use the flattened field type
3. Restructure data to use key-value pairs instead of dynamic keys
4. Use strict mapping with explicit field definitions
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
The issue is that the default BM25 scoring in Elasticsearch treats all terms equally and does not boost exact matches. "Red Shirt with Cotton blend" might score higher because:
1. The document is shorter (BM25 has a field-length normalization)
2. "shirt" and "cotton" appear as exact tokens
3. There is no boost for matching all terms vs some terms

To fix relevance:
1. Use multi_match with cross_fields or best_fields
2. Add an exact match boost using a keyword sub-field
3. Use function_score or bool query with should clauses at different match levels
4. Configure custom analyzers
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
Bulk API in Elasticsearch returns a response where each item can individually succeed or fail. The caller needs to parse the response to find which items failed and why. Common issues:
1. Type mismatches (e.g., sending a string to an integer field)
2. Version conflicts (using external versioning)
3. Document too large
4. Index does not exist (if auto-create is disabled)

The solution is proper error handling with retry logic for transient errors and dead-letter handling for permanent errors.
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
Yellow status means all primary shards are allocated but some replica shards are not. Red means some primary shards are unassigned (data loss risk).

Common causes:
1. Not enough nodes for the number of replicas
2. Disk space too low (watermark reached)
3. Shard allocation filtering rules
4. Node left the cluster and replicas have not been reassigned yet
5. Awareness/zone settings preventing allocation

Diagnosis steps:
1. Check _cluster/allocation/explain
2. Check _cat/shards to find unassigned shards
3. Check disk usage
4. Check allocation settings
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
Query timeouts on large indices can be caused by:
1. Inefficient queries (wildcards, regex, deeply nested)
2. Too many shards or too-large shards
3. Insufficient resources (memory, CPU)
4. Missing or wrong field types (text vs keyword)
5. Script queries or heavy aggregations
6. No query timeout set (waits indefinitely)

Let me provide optimization strategies.
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
