"""Vector databases for AI — Pinecone, Weaviate, Milvus, pgvector, and selection criteria."""

PAIRS = [
    (
        "databases/vector-pinecone",
        "Show Pinecone vector database patterns: indexing, querying, namespaces, and metadata filtering.",
        '''Pinecone vector database patterns for production AI applications:

```python
# --- Pinecone client setup and index management ---

import os
from typing import Any
from pinecone import Pinecone, ServerlessSpec

def create_pinecone_client() -> Pinecone:
    """Initialize Pinecone client with API key."""
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable required")
    return Pinecone(api_key=api_key)


def create_index(
    pc: Pinecone,
    name: str,
    dimension: int = 1536,
    metric: str = "cosine",
    cloud: str = "aws",
    region: str = "us-east-1",
) -> None:
    """Create a serverless Pinecone index."""
    existing = [idx.name for idx in pc.list_indexes()]
    if name in existing:
        print(f"Index '{name}' already exists")
        return

    pc.create_index(
        name=name,
        dimension=dimension,
        metric=metric,           # cosine | euclidean | dotproduct
        spec=ServerlessSpec(
            cloud=cloud,
            region=region,
        ),
    )
    print(f"Created index '{name}' (dim={dimension}, metric={metric})")


def get_index(pc: Pinecone, name: str):
    """Get index handle for operations."""
    return pc.Index(name)
```

```python
# --- Upsert, namespace, and metadata operations ---

import hashlib
from dataclasses import dataclass, field

@dataclass
class Document:
    """Document to be indexed in Pinecone."""
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    doc_id: str | None = None

    def __post_init__(self) -> None:
        if self.doc_id is None:
            self.doc_id = hashlib.sha256(self.text.encode()).hexdigest()[:16]


def upsert_documents(
    index,
    documents: list[Document],
    namespace: str = "",
    batch_size: int = 100,
) -> dict[str, int]:
    """Upsert documents in batches with namespace isolation.

    Namespaces partition vectors within a single index:
      - "production" vs "staging" data
      - Per-tenant isolation in multi-tenant apps
      - A/B testing with different embedding models
    """
    total_upserted = 0
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        vectors = [
            {
                "id": doc.doc_id,
                "values": doc.embedding,
                "metadata": {
                    "text": doc.text[:1000],      # Store truncated text
                    **doc.metadata,
                },
            }
            for doc in batch
        ]
        result = index.upsert(vectors=vectors, namespace=namespace)
        total_upserted += result.upserted_count

    return {"upserted": total_upserted, "namespace": namespace}


def query_with_metadata_filter(
    index,
    query_embedding: list[float],
    namespace: str = "",
    top_k: int = 10,
    category: str | None = None,
    min_date: str | None = None,
    score_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Query with metadata filtering for precise retrieval.

    Pinecone metadata filter operators:
      $eq, $ne           — equality
      $gt, $gte, $lt, $lte — range
      $in, $nin           — set membership
      $exists             — field existence
      $and, $or           — logical combinators
    """
    metadata_filter: dict[str, Any] = {}

    if category:
        metadata_filter["category"] = {"$eq": category}

    if min_date:
        metadata_filter["created_at"] = {"$gte": min_date}

    # Combine filters with $and if multiple conditions
    if len(metadata_filter) > 1:
        metadata_filter = {
            "$and": [
                {k: v} for k, v in metadata_filter.items()
            ]
        }

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=namespace,
        filter=metadata_filter if metadata_filter else None,
        include_metadata=True,
        include_values=False,      # Skip returning vectors to save bandwidth
    )

    return [
        {
            "id": match.id,
            "score": match.score,
            "text": match.metadata.get("text", ""),
            "metadata": match.metadata,
        }
        for match in results.matches
        if match.score >= score_threshold
    ]
```

```python
# --- Hybrid search and index lifecycle ---

from pinecone import SparseValues

def hybrid_search(
    index,
    dense_embedding: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    namespace: str = "",
    alpha: float = 0.7,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Hybrid dense + sparse search (requires s1/p1 pod with dotproduct).

    alpha controls balance: 1.0 = pure dense, 0.0 = pure sparse.
    Sparse vectors come from BM25 or SPLADE encoders.
    """
    # Scale vectors by alpha for weighted combination
    scaled_dense = [v * alpha for v in dense_embedding]
    scaled_sparse = [v * (1 - alpha) for v in sparse_values]

    results = index.query(
        vector=scaled_dense,
        sparse_vector=SparseValues(
            indices=sparse_indices,
            values=scaled_sparse,
        ),
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )

    return [
        {"id": m.id, "score": m.score, "metadata": m.metadata}
        for m in results.matches
    ]


def delete_by_metadata(
    index, namespace: str, filter_dict: dict[str, Any]
) -> None:
    """Delete vectors matching metadata filter."""
    index.delete(filter=filter_dict, namespace=namespace)


def describe_index_stats(index) -> dict[str, Any]:
    """Get index statistics including per-namespace counts."""
    stats = index.describe_index_stats()
    return {
        "total_vectors": stats.total_vector_count,
        "dimension": stats.dimension,
        "namespaces": {
            ns: data.vector_count
            for ns, data in stats.namespaces.items()
        },
    }
```

Key Pinecone patterns:

| Feature | Detail |
|---|---|
| Namespaces | Partition vectors within one index; free, no extra cost |
| Metadata filtering | Rich operators ($eq, $in, $gt, $and, $or) on scalar fields |
| Batch upsert | 100 vectors per batch optimal; max 2MB per request |
| Hybrid search | Dense + sparse on dotproduct indexes (pod-based) |
| Serverless | Auto-scaling, pay-per-query; best for variable workloads |
| Pod-based | Dedicated resources; needed for hybrid search, high QPS |

1. **Namespace isolation** -- partition data per tenant or environment at zero cost
2. **Metadata-first filtering** -- narrow search space before vector similarity
3. **Batch operations** -- upsert in 100-vector batches for throughput
4. **Score thresholds** -- filter low-confidence results client-side
5. **Hybrid search** -- combine dense semantics with sparse keyword matching'''
    ),
    (
        "databases/vector-weaviate",
        "Explain Weaviate vector database: schema design, vectorizer modules, and hybrid search.",
        '''Weaviate vector database with schema management and hybrid search:

```python
# --- Weaviate client and schema management ---

import weaviate
from weaviate.classes.config import (
    Configure,
    Property,
    DataType,
    VectorDistances,
    Tokenization,
)
from weaviate.classes.query import MetadataQuery, Filter
from typing import Any


def connect_weaviate(
    url: str = "http://localhost:8080",
    api_key: str | None = None,
    openai_key: str | None = None,
) -> weaviate.WeaviateClient:
    """Connect to Weaviate with optional API keys."""
    headers = {}
    if openai_key:
        headers["X-OpenAI-Api-Key"] = openai_key

    if api_key:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=url,
            auth_credentials=weaviate.auth.AuthApiKey(api_key),
            headers=headers,
        )
    else:
        client = weaviate.connect_to_local(
            host=url.replace("http://", "").split(":")[0],
            headers=headers,
        )
    return client


def create_article_collection(client: weaviate.WeaviateClient) -> None:
    """Create a collection with vectorizer and properties.

    Weaviate vectorizer modules:
      text2vec-openai       — OpenAI embeddings
      text2vec-cohere       — Cohere embeddings
      text2vec-huggingface  — HuggingFace models
      text2vec-transformers — Self-hosted transformers
      multi2vec-clip        — Multimodal CLIP embeddings
    """
    client.collections.create(
        name="Article",
        description="Knowledge base articles",

        # Vectorizer: auto-embeds text properties
        vectorizer_config=Configure.Vectorizer.text2vec_openai(
            model="text-embedding-3-small",
            dimensions=1536,
        ),

        # Generative module for RAG
        generative_config=Configure.Generative.openai(
            model="gpt-4o-mini",
        ),

        # Vector index configuration
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
            ef_construction=128,
            max_connections=16,
            ef=100,
        ),

        # Inverted index for filtering
        inverted_index_config=Configure.inverted_index(
            index_timestamps=True,
        ),

        properties=[
            Property(
                name="title",
                data_type=DataType.TEXT,
                tokenization=Tokenization.WORD,
                index_filterable=True,
                index_searchable=True,
            ),
            Property(
                name="content",
                data_type=DataType.TEXT,
                tokenization=Tokenization.WORD,
                index_searchable=True,
            ),
            Property(
                name="category",
                data_type=DataType.TEXT,
                tokenization=Tokenization.FIELD,
                index_filterable=True,
            ),
            Property(
                name="published_at",
                data_type=DataType.DATE,
                index_filterable=True,
            ),
            Property(
                name="view_count",
                data_type=DataType.INT,
                index_filterable=True,
            ),
        ],
    )
```

```python
# --- Data ingestion and querying ---

from datetime import datetime
import uuid


def ingest_articles(
    client: weaviate.WeaviateClient,
    articles: list[dict[str, Any]],
    batch_size: int = 200,
) -> int:
    """Batch-insert articles with auto-vectorization."""
    collection = client.collections.get("Article")
    inserted = 0

    with collection.batch.dynamic() as batch:
        for article in articles:
            batch.add_object(
                properties={
                    "title": article["title"],
                    "content": article["content"],
                    "category": article.get("category", "general"),
                    "published_at": article.get("published_at", datetime.now().isoformat()),
                    "view_count": article.get("view_count", 0),
                },
                uuid=article.get("id", str(uuid.uuid4())),
            )
            inserted += 1

    failed = collection.batch.failed_objects
    if failed:
        print(f"Failed to insert {len(failed)} objects")
    return inserted


def semantic_search(
    client: weaviate.WeaviateClient,
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Semantic (near_text) search with optional filtering."""
    collection = client.collections.get("Article")

    filters = None
    if category:
        filters = Filter.by_property("category").equal(category)

    results = collection.query.near_text(
        query=query,
        limit=limit,
        filters=filters,
        return_metadata=MetadataQuery(distance=True, certainty=True),
    )

    return [
        {
            "uuid": str(obj.uuid),
            "title": obj.properties["title"],
            "content": obj.properties["content"][:200],
            "category": obj.properties["category"],
            "distance": obj.metadata.distance,
            "certainty": obj.metadata.certainty,
        }
        for obj in results.objects
    ]
```

```python
# --- Hybrid search and RAG ---

def hybrid_search(
    client: weaviate.WeaviateClient,
    query: str,
    alpha: float = 0.5,
    limit: int = 10,
    min_views: int = 0,
) -> list[dict[str, Any]]:
    """Hybrid search combining BM25 keyword + vector similarity.

    alpha controls the balance:
      0.0 = pure BM25 keyword search
      0.5 = equal weight
      1.0 = pure vector search
    """
    collection = client.collections.get("Article")

    filters = None
    if min_views > 0:
        filters = Filter.by_property("view_count").greater_than(min_views)

    results = collection.query.hybrid(
        query=query,
        alpha=alpha,
        limit=limit,
        filters=filters,
        return_metadata=MetadataQuery(score=True, explain_score=True),
    )

    return [
        {
            "uuid": str(obj.uuid),
            "title": obj.properties["title"],
            "score": obj.metadata.score,
            "explanation": obj.metadata.explain_score,
        }
        for obj in results.objects
    ]


def generative_search(
    client: weaviate.WeaviateClient,
    query: str,
    prompt_template: str = "Summarize: {content}",
    limit: int = 5,
) -> dict[str, Any]:
    """RAG: retrieve then generate using Weaviate generative module."""
    collection = client.collections.get("Article")

    results = collection.generate.near_text(
        query=query,
        limit=limit,
        single_prompt=prompt_template,
        grouped_task="Synthesize these articles into a comprehensive answer.",
    )

    return {
        "generated_answer": results.generated,
        "sources": [
            {
                "title": obj.properties["title"],
                "generated": obj.generated,
            }
            for obj in results.objects
        ],
    }


def bm25_search(
    client: weaviate.WeaviateClient,
    query: str,
    properties: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Pure keyword BM25 search on specific properties."""
    collection = client.collections.get("Article")

    results = collection.query.bm25(
        query=query,
        query_properties=properties or ["title^2", "content"],
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )

    return [
        {
            "title": obj.properties["title"],
            "score": obj.metadata.score,
        }
        for obj in results.objects
    ]
```

Key Weaviate patterns:

| Feature | Detail |
|---|---|
| Auto-vectorization | Vectorizer modules embed text at insert time |
| Hybrid search | BM25 + vector with tunable alpha parameter |
| Generative search | Built-in RAG with single/grouped prompts |
| Multi-tenancy | Native tenant isolation per collection |
| Filters | Type-safe filtering on indexed properties |
| HNSW tuning | ef_construction, max_connections, ef for recall/speed |

1. **Vectorizer modules** -- auto-embed at ingestion, no external embedding calls needed
2. **Hybrid alpha** -- tune between keyword precision and semantic recall
3. **Generative RAG** -- built-in generate step eliminates external LLM plumbing
4. **Property tokenization** -- WORD for full-text, FIELD for exact match filters
5. **Batch ingestion** -- dynamic batching handles rate limiting automatically'''
    ),
    (
        "databases/vector-milvus",
        "Demonstrate Milvus vector database: collection management, IVF_FLAT vs HNSW indexes, and partitions.",
        '''Milvus vector database with collection management and index strategies:

```python
# --- Milvus connection and collection management ---

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
from typing import Any


def connect_milvus(
    host: str = "localhost",
    port: int = 19530,
    alias: str = "default",
    token: str | None = None,
) -> None:
    """Connect to Milvus server or Zilliz Cloud."""
    params: dict[str, Any] = {"alias": alias, "host": host, "port": port}
    if token:
        params["token"] = token
        params["secure"] = True
    connections.connect(**params)
    print(f"Connected to Milvus at {host}:{port}")


def create_document_collection(
    name: str = "documents",
    dimension: int = 1536,
    max_text_length: int = 65535,
) -> Collection:
    """Create a collection with schema for document search.

    Milvus field types:
      INT64       — primary key, counters
      VARCHAR     — text fields (max 65535 chars)
      FLOAT_VECTOR — dense embeddings
      SPARSE_FLOAT_VECTOR — sparse vectors (BM25/SPLADE)
      JSON        — flexible metadata
      ARRAY       — typed arrays (INT, VARCHAR, etc.)
    """
    fields = [
        FieldSchema(
            name="doc_id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
        ),
        FieldSchema(
            name="title",
            dtype=DataType.VARCHAR,
            max_length=512,
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=max_text_length,
        ),
        FieldSchema(
            name="category",
            dtype=DataType.VARCHAR,
            max_length=64,
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=dimension,
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
        ),
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Document collection for semantic search",
        enable_dynamic_field=True,
    )

    collection = Collection(name=name, schema=schema)
    print(f"Created collection '{name}' with {len(fields)} fields")
    return collection


def create_partitions(
    collection: Collection,
    partition_names: list[str],
) -> None:
    """Create partitions for data isolation and targeted search.

    Partitions enable:
      - Search within a subset (e.g., by tenant or category)
      - Independent data loading/release
      - Faster queries on specific segments
    """
    for name in partition_names:
        if not collection.has_partition(name):
            collection.create_partition(name)
            print(f"Created partition: {name}")
```

```python
# --- Index creation: IVF_FLAT vs HNSW ---

def create_ivf_flat_index(
    collection: Collection,
    field_name: str = "embedding",
    nlist: int = 128,
    metric: str = "COSINE",
) -> None:
    """Create IVF_FLAT index — good balance of speed and recall.

    IVF_FLAT partitions vectors into nlist clusters using k-means.
    At query time, searches nprobe nearest clusters.

    Tuning:
      nlist  — number of clusters (sqrt(N) to 4*sqrt(N))
      nprobe — clusters to search at query (1-nlist, higher = better recall)

    Best for: datasets < 10M vectors, when exact results matter
    """
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": metric,
        "params": {"nlist": nlist},
    }
    collection.create_index(
        field_name=field_name,
        index_params=index_params,
    )
    print(f"IVF_FLAT index created (nlist={nlist}, metric={metric})")


def create_hnsw_index(
    collection: Collection,
    field_name: str = "embedding",
    m: int = 16,
    ef_construction: int = 256,
    metric: str = "COSINE",
) -> None:
    """Create HNSW index — best recall, higher memory usage.

    HNSW builds a hierarchical navigable small-world graph.

    Tuning:
      M               — connections per node (4-64, default 16)
      efConstruction   — build-time search width (higher = better graph)
      ef               — query-time search width (set at search time)

    Best for: highest recall requirements, datasets < 50M vectors
    Memory: ~1.5x more than IVF_FLAT
    """
    index_params = {
        "index_type": "HNSW",
        "metric_type": metric,
        "params": {
            "M": m,
            "efConstruction": ef_construction,
        },
    }
    collection.create_index(
        field_name=field_name,
        index_params=index_params,
    )
    print(f"HNSW index created (M={m}, efConstruction={ef_construction})")


# --- Index comparison ---
# | Index     | Build time | Query speed | Recall | Memory    | Best for            |
# |-----------|-----------|-------------|--------|-----------|---------------------|
# | FLAT      | None      | Slowest     | 100%   | 1x        | < 100K vectors      |
# | IVF_FLAT  | Medium    | Fast        | 95-99% | 1x        | 1M-10M vectors      |
# | IVF_SQ8   | Medium    | Faster      | 90-95% | 0.25x     | Memory constrained  |
# | HNSW      | Slow      | Fastest     | 98-99% | 1.5x      | < 50M, best recall  |
# | IVF_PQ    | Slow      | Fast        | 85-95% | 0.1-0.25x | > 10M, low memory   |
# | DISKANN   | Slow      | Fast        | 95-98% | 0.1x+disk | > 100M vectors      |
```

```python
# --- Insert, search, and partition operations ---

import numpy as np


def insert_documents(
    collection: Collection,
    titles: list[str],
    contents: list[str],
    categories: list[str],
    embeddings: list[list[float]],
    partition_name: str | None = None,
    batch_size: int = 1000,
) -> list[int]:
    """Batch insert documents into collection or partition."""
    all_ids: list[int] = []

    for i in range(0, len(titles), batch_size):
        batch_data = [
            titles[i : i + batch_size],
            contents[i : i + batch_size],
            categories[i : i + batch_size],
            embeddings[i : i + batch_size],
            [{"source": "api", "version": 1}] * len(titles[i : i + batch_size]),
        ]

        kwargs: dict[str, Any] = {"data": batch_data}
        if partition_name:
            kwargs["partition_name"] = partition_name

        result = collection.insert(**kwargs)
        all_ids.extend(result.primary_keys)

    collection.flush()
    return all_ids


def search_documents(
    collection: Collection,
    query_embedding: list[float],
    top_k: int = 10,
    partition_names: list[str] | None = None,
    category_filter: str | None = None,
    nprobe: int = 16,
    ef: int = 128,
) -> list[dict[str, Any]]:
    """Search with index-specific parameters and filtering."""
    collection.load()

    search_params: dict[str, Any] = {}
    # Detect index type for correct search params
    index_info = collection.index()
    index_type = index_info.params.get("index_type", "FLAT")

    if index_type == "IVF_FLAT":
        search_params = {"metric_type": "COSINE", "params": {"nprobe": nprobe}}
    elif index_type == "HNSW":
        search_params = {"metric_type": "COSINE", "params": {"ef": ef}}
    else:
        search_params = {"metric_type": "COSINE"}

    # Expression filter
    expr = None
    if category_filter:
        expr = f'category == "{category_filter}"'

    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=expr,
        partition_names=partition_names,
        output_fields=["title", "content", "category", "metadata"],
    )

    hits: list[dict[str, Any]] = []
    for hit in results[0]:
        hits.append({
            "id": hit.id,
            "distance": hit.distance,
            "title": hit.entity.get("title"),
            "content": hit.entity.get("content", "")[:200],
            "category": hit.entity.get("category"),
        })

    return hits
```

Key Milvus patterns:

| Feature | Detail |
|---|---|
| Partitions | Isolate data segments for targeted search |
| IVF_FLAT | Cluster-based index, good speed/recall balance |
| HNSW | Graph-based index, best recall, more memory |
| Dynamic fields | Schema-flexible JSON metadata |
| Expression filters | SQL-like boolean expressions on scalar fields |
| GPU indexes | GPU_IVF_FLAT, GPU_CAGRA for 10-100x speedup |

1. **Choose index by scale** -- FLAT < 100K, IVF_FLAT 1-10M, HNSW for best recall, DISKANN > 100M
2. **Partition by access pattern** -- search only relevant data subsets
3. **Tune nprobe/ef at query time** -- trade latency for recall
4. **Batch inserts** -- 1000+ vectors per insert for throughput
5. **Flush after insert** -- ensure data is persisted and searchable'''
    ),
    (
        "databases/vector-pgvector",
        "Show pgvector in PostgreSQL: indexing strategies, HNSW, and production patterns.",
        '''pgvector in PostgreSQL for vector similarity search:

```python
# --- pgvector setup and table creation ---

import psycopg2
from psycopg2.extras import execute_values
from typing import Any
from contextlib import contextmanager


@contextmanager
def get_connection(dsn: str = "postgresql://localhost:5432/vectordb"):
    """Database connection context manager."""
    conn = psycopg2.connect(dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def setup_pgvector(dsn: str) -> None:
    """Initialize pgvector extension and create tables."""
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Enable pgvector extension
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Create documents table with vector column
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id          BIGSERIAL PRIMARY KEY,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'general',
                embedding   vector(1536),         -- OpenAI ada-002 dimension
                metadata    JSONB DEFAULT '{}',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            );

            -- GIN index on metadata for JSONB queries
            CREATE INDEX IF NOT EXISTS idx_documents_metadata
                ON documents USING GIN (metadata);

            -- B-tree index for category filtering
            CREATE INDEX IF NOT EXISTS idx_documents_category
                ON documents (category);

            -- Partial index for active documents
            CREATE INDEX IF NOT EXISTS idx_documents_active
                ON documents (created_at)
                WHERE metadata->>'status' = 'active';
        """)
        print("pgvector setup complete")


def create_hnsw_index(
    dsn: str,
    m: int = 16,
    ef_construction: int = 64,
    lists: int | None = None,
) -> None:
    """Create HNSW or IVFFlat index on vector column.

    HNSW (recommended for most cases):
      - No training step required
      - Better recall at same speed
      - Higher memory usage
      - Supports INSERT without rebuild

    IVFFlat:
      - Requires training data (table must have rows)
      - Lower memory usage
      - Faster build time
      - Must REINDEX after large inserts
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # HNSW index — best for most workloads
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw
            ON documents
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = {m}, ef_construction = {ef_construction});
        """)

        print(f"HNSW index created (m={m}, ef_construction={ef_construction})")
```

```python
# --- Insertion and similarity search ---

def insert_documents(
    dsn: str,
    documents: list[dict[str, Any]],
    batch_size: int = 500,
) -> int:
    """Batch insert documents with embeddings."""
    inserted = 0

    with get_connection(dsn) as conn:
        cur = conn.cursor()

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            values = [
                (
                    doc["title"],
                    doc["content"],
                    doc.get("category", "general"),
                    doc["embedding"],            # Pass as Python list
                    psycopg2.extras.Json(doc.get("metadata", {})),
                )
                for doc in batch
            ]

            execute_values(
                cur,
                """INSERT INTO documents (title, content, category, embedding, metadata)
                   VALUES %s""",
                values,
                template="(%s, %s, %s, %s::vector, %s)",
            )
            inserted += len(batch)

    return inserted


def similarity_search(
    dsn: str,
    query_embedding: list[float],
    top_k: int = 10,
    category: str | None = None,
    ef_search: int = 100,
    distance: str = "cosine",
) -> list[dict[str, Any]]:
    """Similarity search with filtering and HNSW tuning.

    Distance operators:
      <=>  cosine distance    (vector_cosine_ops)
      <->  L2 distance        (vector_l2_ops)
      <#>  inner product       (vector_ip_ops)
      <+>  L1/Manhattan        (vector_l1_ops)
    """
    # Map distance type to operator
    ops = {
        "cosine": "<=>",
        "l2": "<->",
        "inner_product": "<#>",
    }
    operator = ops.get(distance, "<=>")

    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Set HNSW search parameter for this session
        cur.execute(f"SET hnsw.ef_search = {ef_search};")

        # Build query with optional filter
        where_clause = ""
        params: list[Any] = [query_embedding]

        if category:
            where_clause = "WHERE category = %s"
            params.append(category)

        params.append(top_k)

        cur.execute(f"""
            SELECT
                id,
                title,
                LEFT(content, 200) AS content_preview,
                category,
                1 - (embedding {operator} %s::vector) AS similarity,
                metadata,
                created_at
            FROM documents
            {where_clause}
            ORDER BY embedding {operator} %s::vector
            LIMIT %s;
        """, (*params[:1], *params[1:-1], *params[:1], params[-1]))

        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
```

```python
# --- Advanced pgvector patterns ---

def hybrid_search_pgvector(
    dsn: str,
    query_text: str,
    query_embedding: list[float],
    top_k: int = 10,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """Hybrid search using Reciprocal Rank Fusion (RRF).

    Combines:
      - Full-text search (tsvector + GIN index)
      - Vector similarity search (HNSW)
    Using RRF to merge rankings without score normalization.
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        cur.execute("""
            WITH semantic AS (
                SELECT id, title, content, category,
                    ROW_NUMBER() OVER (
                        ORDER BY embedding <=> %(emb)s::vector
                    ) AS rank_s
                FROM documents
                ORDER BY embedding <=> %(emb)s::vector
                LIMIT %(limit)s * 2
            ),
            fulltext AS (
                SELECT id, title, content, category,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(
                            to_tsvector('english', content),
                            plainto_tsquery('english', %(query)s)
                        ) DESC
                    ) AS rank_f
                FROM documents
                WHERE to_tsvector('english', content)
                    @@ plainto_tsquery('english', %(query)s)
                LIMIT %(limit)s * 2
            )
            SELECT
                COALESCE(s.id, f.id) AS id,
                COALESCE(s.title, f.title) AS title,
                LEFT(COALESCE(s.content, f.content), 200) AS content,
                COALESCE(s.category, f.category) AS category,
                -- RRF score: sum of 1/(k + rank) from each source
                COALESCE(1.0 / (%(k)s + s.rank_s), 0) +
                COALESCE(1.0 / (%(k)s + f.rank_f), 0) AS rrf_score
            FROM semantic s
            FULL OUTER JOIN fulltext f ON s.id = f.id
            ORDER BY rrf_score DESC
            LIMIT %(limit)s;
        """, {
            "emb": query_embedding,
            "query": query_text,
            "limit": top_k,
            "k": rrf_k,
        })

        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def check_index_usage(dsn: str) -> list[dict[str, Any]]:
    """Check if vector index is being used in queries."""
    with get_connection(dsn) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                schemaname, tablename, indexname, idx_scan,
                pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
            FROM pg_stat_user_indexes
            WHERE indexname LIKE '%embedding%'
            ORDER BY idx_scan DESC;
        """)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
```

Key pgvector patterns:

| Feature | Detail |
|---|---|
| HNSW index | Best recall, no rebuild needed, higher memory |
| IVFFlat index | Lower memory, needs training data, periodic REINDEX |
| Distance ops | <=>(cosine), <->(L2), <#>(inner product) |
| ef_search | Query-time HNSW tuning via SET parameter |
| Hybrid search | Combine tsvector full-text with vector via RRF |
| JSONB metadata | Rich filtering with GIN-indexed JSON fields |

1. **Use HNSW over IVFFlat** -- better recall, no rebuild, slight memory cost
2. **Tune ef_search per query** -- SET hnsw.ef_search for recall/speed tradeoff
3. **Combine with PostgreSQL features** -- JOINs, transactions, JSONB, full-text
4. **Hybrid RRF** -- merge full-text and vector rankings without score normalization
5. **Partial indexes** -- index only active/relevant rows for faster search'''
    ),
    (
        "databases/vector-comparison",
        "Compare vector databases: Pinecone vs Weaviate vs Milvus vs pgvector and selection criteria.",
        '''Vector database comparison and selection guide:

```python
# --- Vector database abstraction layer ---

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol
from enum import Enum


class VectorDBType(Enum):
    """Supported vector database backends."""
    PINECONE = "pinecone"
    WEAVIATE = "weaviate"
    MILVUS = "milvus"
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"
    CHROMA = "chroma"


@dataclass
class SearchResult:
    """Unified search result across vector databases."""
    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_relevant(self) -> bool:
        """Check if result meets minimum relevance threshold."""
        return self.score >= 0.7


class VectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> int:
        """Insert or update vectors."""
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors."""
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> int:
        """Delete vectors by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Get total vector count."""
        ...


class EmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...
```

```python
# --- Selection criteria scoring ---

from dataclasses import dataclass


@dataclass
class SelectionCriteria:
    """Score vector databases against requirements."""
    dataset_size: int             # Number of vectors
    query_latency_ms: int         # Target p99 latency
    recall_target: float          # Minimum recall (0-1)
    needs_filtering: bool         # Metadata filtering required
    needs_hybrid: bool            # BM25 + vector search
    needs_multi_tenancy: bool     # Tenant isolation
    managed_preferred: bool       # Managed service vs self-hosted
    budget_monthly_usd: int       # Monthly budget
    existing_postgres: bool       # Already running PostgreSQL
    team_size: int                # Engineering team size


def score_databases(
    criteria: SelectionCriteria,
) -> list[dict[str, Any]]:
    """Score each vector database against requirements.

    Returns ranked list of recommendations.
    """
    scores: list[dict[str, Any]] = []

    # --- Pinecone ---
    pinecone_score = 0.0
    if criteria.managed_preferred:
        pinecone_score += 3.0
    if criteria.team_size <= 5:
        pinecone_score += 2.0       # Low operational overhead
    if criteria.dataset_size < 10_000_000:
        pinecone_score += 2.0
    if criteria.needs_filtering:
        pinecone_score += 1.5
    if criteria.needs_multi_tenancy:
        pinecone_score += 2.0       # Namespace-based isolation
    if criteria.needs_hybrid:
        pinecone_score += 0.5       # Supported but requires pod-based
    scores.append({
        "db": "Pinecone",
        "score": pinecone_score,
        "pros": ["Fully managed", "Zero ops", "Namespace multi-tenancy"],
        "cons": ["Vendor lock-in", "Cost at scale", "Limited hybrid search"],
    })

    # --- Weaviate ---
    weaviate_score = 0.0
    if criteria.needs_hybrid:
        weaviate_score += 3.0       # Best hybrid search
    if criteria.recall_target > 0.95:
        weaviate_score += 2.0
    if criteria.needs_multi_tenancy:
        weaviate_score += 2.5       # Native multi-tenancy
    if criteria.needs_filtering:
        weaviate_score += 2.0
    if not criteria.managed_preferred:
        weaviate_score += 1.0       # Good self-hosted option
    scores.append({
        "db": "Weaviate",
        "score": weaviate_score,
        "pros": ["Built-in hybrid search", "Auto-vectorization", "RAG support"],
        "cons": ["Newer ecosystem", "Memory hungry", "Complex clustering"],
    })

    # --- Milvus ---
    milvus_score = 0.0
    if criteria.dataset_size > 10_000_000:
        milvus_score += 3.0         # Scales to billions
    if criteria.query_latency_ms < 10:
        milvus_score += 2.0         # GPU acceleration
    if not criteria.managed_preferred:
        milvus_score += 2.0         # Best self-hosted scale
    if criteria.needs_filtering:
        milvus_score += 1.5
    scores.append({
        "db": "Milvus",
        "score": milvus_score,
        "pros": ["Massive scale", "GPU support", "Flexible indexes"],
        "cons": ["Complex deployment", "Higher ops overhead", "Steep learning curve"],
    })

    # --- pgvector ---
    pgvector_score = 0.0
    if criteria.existing_postgres:
        pgvector_score += 4.0       # No new infrastructure
    if criteria.dataset_size < 5_000_000:
        pgvector_score += 2.0
    if criteria.budget_monthly_usd < 500:
        pgvector_score += 2.0       # Free extension
    if criteria.needs_filtering:
        pgvector_score += 2.5       # Full SQL power
    if criteria.needs_hybrid:
        pgvector_score += 2.0       # tsvector + vector
    scores.append({
        "db": "pgvector",
        "score": pgvector_score,
        "pros": ["Free", "Full SQL", "Existing Postgres", "ACID transactions"],
        "cons": ["Scale ceiling ~5M", "No GPU", "Manual tuning needed"],
    })

    # Sort by score descending
    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores
```

```python
# --- Decision matrix and migration strategy ---

COMPARISON_MATRIX = """
| Criteria          | Pinecone    | Weaviate    | Milvus      | pgvector   | Qdrant     |
|-------------------|-------------|-------------|-------------|------------|------------|
| Max scale         | 100M+       | 100M+       | 1B+         | ~5-10M     | 100M+      |
| Hosting           | Managed     | Both        | Both        | Self/Cloud | Both       |
| Hybrid search     | Limited     | Excellent   | Good        | Good (RRF) | Good       |
| Multi-tenancy     | Namespaces  | Native      | Partitions  | Row-level  | Collections|
| Filtering         | Rich        | Rich        | Expressions | Full SQL   | Rich       |
| GPU support       | No          | No          | Yes         | No         | No         |
| ACID transactions | No          | No          | No          | Yes        | No         |
| Built-in RAG      | No          | Yes         | No          | No         | No         |
| Learning curve    | Low         | Medium      | High        | Low (SQL)  | Low        |
| Cost (small)      | Free tier   | Free (OSS)  | Free (OSS)  | Free ext   | Free (OSS) |
| Cost (large)      | $$$         | $$          | $$          | $          | $$         |
| Best for          | Startups    | Hybrid/RAG  | Enterprise  | Existing PG| General    |
"""


def recommend_vector_db(
    criteria: SelectionCriteria,
) -> dict[str, Any]:
    """Generate a recommendation report."""
    rankings = score_databases(criteria)
    top_pick = rankings[0]
    runner_up = rankings[1] if len(rankings) > 1 else None

    recommendation = {
        "primary": top_pick["db"],
        "primary_score": top_pick["score"],
        "primary_pros": top_pick["pros"],
        "primary_cons": top_pick["cons"],
        "runner_up": runner_up["db"] if runner_up else None,
        "comparison_matrix": COMPARISON_MATRIX,
    }

    # Add migration notes
    if criteria.existing_postgres and top_pick["db"] != "pgvector":
        recommendation["migration_note"] = (
            "Consider starting with pgvector (zero infra cost) "
            "and migrating to {top_pick['db']} when you outgrow it."
        )

    # Add scale warnings
    if criteria.dataset_size > 50_000_000 and top_pick["db"] == "pgvector":
        recommendation["scale_warning"] = (
            "pgvector may struggle above 50M vectors. "
            "Plan migration to Milvus or a managed solution."
        )

    return recommendation


# Quick selection guide:
#
# "I have PostgreSQL already" -> pgvector
# "I want zero ops"          -> Pinecone
# "I need hybrid search"     -> Weaviate
# "I have 100M+ vectors"     -> Milvus
# "I need built-in RAG"      -> Weaviate
# "I want GPU acceleration"  -> Milvus
# "I need ACID + vectors"    -> pgvector
# "I'm a startup, < 1M vecs" -> Pinecone free tier or pgvector
```

Vector database selection summary:

| Scenario | Recommended DB | Reason |
|---|---|---|
| Existing PostgreSQL, < 5M vectors | pgvector | Zero new infra, full SQL |
| Startup, managed, < 10M vectors | Pinecone | Zero ops, free tier |
| Hybrid search + RAG pipeline | Weaviate | Built-in BM25 + vector + generative |
| Enterprise scale, > 100M vectors | Milvus | GPU support, billion-scale |
| Multi-tenant SaaS | Weaviate or Pinecone | Native tenant isolation |
| Budget-constrained | pgvector | Free PostgreSQL extension |

1. **Start with pgvector** if you already run PostgreSQL and have < 5M vectors
2. **Choose Pinecone** for zero-ops managed service with fast time-to-production
3. **Pick Weaviate** when hybrid search and built-in RAG are critical requirements
4. **Use Milvus** for massive scale, GPU acceleration, or billion-vector datasets
5. **Abstract your vector store** -- build an interface layer to allow future migration'''
    ),
]
