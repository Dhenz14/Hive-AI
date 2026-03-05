PAIRS = [
    (
        "ml/vector-database-fundamentals",
        r"""Explain vector database fundamentals including embedding storage, similarity search algorithms (HNSW, IVF, PQ), distance metrics (cosine, L2, dot product), indexing strategies, and when to use dedicated vector DBs vs extensions like pgvector. Include Python examples.""",
        r"""## Vector Database Fundamentals: Embeddings, Similarity Search, and Index Selection

Vector databases store high-dimensional embeddings and enable efficient similarity search — the backbone of RAG systems, recommendation engines, and semantic search.

### Core Concepts

```python
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class VectorRecord:
    id: str
    embedding: np.ndarray  # e.g., 1536-dim from OpenAI, 768-dim from BERT
    metadata: dict  # Filterable attributes
    text: str  # Original text for retrieval


# Distance metrics determine "similarity":
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """1 = identical direction, 0 = orthogonal, -1 = opposite."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """0 = identical, larger = more different."""
    return np.linalg.norm(a - b)


def dot_product(a: np.ndarray, b: np.ndarray) -> float:
    """Higher = more similar (when vectors are normalized, equals cosine)."""
    return np.dot(a, b)


# When to use which metric:
# Cosine:  Text embeddings (OpenAI, Cohere) — direction matters, not magnitude
# L2:      Image embeddings, when absolute position matters
# Dot:     When embeddings are pre-normalized (equivalent to cosine, faster)
```

### Approximate Nearest Neighbor (ANN) Algorithms

Exact search is O(n*d) — too slow for millions of vectors. ANN algorithms trade accuracy for speed:

```python
# HNSW (Hierarchical Navigable Small World)
# Best for: Low-latency queries, high recall
# Memory: High (keeps full vectors + graph in RAM)
# Build time: Moderate
# Query time: O(log n) with high recall (>95%)

# How HNSW works:
# 1. Builds a multi-layer graph of vectors
# 2. Top layers: sparse, for coarse navigation
# 3. Bottom layers: dense, for fine-grained search
# 4. Search starts at top, navigates down greedily

# IVF (Inverted File Index)
# Best for: Large datasets, moderate latency
# Memory: Lower (can keep inverted lists on disk)
# Build time: Fast (k-means clustering)
# Query time: O(n/k * nprobe) where k = clusters, nprobe = clusters to search

# How IVF works:
# 1. Cluster vectors into k groups using k-means
# 2. At query time, find nearest clusters
# 3. Search only vectors in those clusters
# 4. nprobe controls accuracy/speed tradeoff

# Product Quantization (PQ)
# Best for: Memory-constrained, billion-scale
# Memory: Very low (compresses 1536-dim float32 → 48 bytes)
# Build time: Moderate
# Query time: Fast (operates on compressed vectors)
# Accuracy: Lower than HNSW, tunable

# Combinations: IVF-PQ, HNSW-PQ for best of both worlds
```

### Using pgvector (PostgreSQL Extension)

```python
import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector


async def setup_pgvector(pool: asyncpg.Pool):
    """Set up pgvector extension and table."""
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                embedding vector(1536),  -- OpenAI dimension
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # HNSW index for fast similarity search
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_embedding
            ON documents USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200)
        """)
        # m = connections per node (higher = more accurate, more memory)
        # ef_construction = build-time beam width (higher = better index)


async def insert_documents(pool, documents: list[dict]):
    """Batch insert documents with embeddings."""
    async with pool.acquire() as conn:
        await register_vector(conn)
        await conn.executemany(
            """INSERT INTO documents (content, metadata, embedding)
            VALUES ($1, $2, $3)""",
            [
                (doc["content"], json.dumps(doc["metadata"]),
                 np.array(doc["embedding"], dtype=np.float32))
                for doc in documents
            ],
        )


async def similarity_search(
    pool: asyncpg.Pool,
    query_embedding: list[float],
    top_k: int = 5,
    metadata_filter: dict = None,
) -> list[dict]:
    """Search for similar documents with optional metadata filtering."""
    async with pool.acquire() as conn:
        await register_vector(conn)

        embedding = np.array(query_embedding, dtype=np.float32)

        if metadata_filter:
            # Combine vector similarity with metadata filtering
            rows = await conn.fetch(
                """
                SELECT id, content, metadata,
                       1 - (embedding <=> $1) as similarity
                FROM documents
                WHERE metadata @> $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                embedding,
                json.dumps(metadata_filter),
                top_k,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata,
                       1 - (embedding <=> $1) as similarity
                FROM documents
                ORDER BY embedding <=> $1
                LIMIT $2
                """,
                embedding,
                top_k,
            )

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "similarity": float(row["similarity"]),
            }
            for row in rows
        ]


# Distance operators in pgvector:
# <=>  Cosine distance (1 - cosine_similarity)
# <->  L2 (Euclidean) distance
# <#>  Negative inner product (for max inner product search)
```

### Using a Dedicated Vector DB (Qdrant example)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range,
)


class VectorStore:
    """Vector store abstraction over Qdrant."""

    def __init__(self, url: str = "http://localhost:6333"):
        self.client = QdrantClient(url=url)

    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: Distance = Distance.COSINE,
    ):
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=dimension,
                distance=distance,
                on_disk=False,  # Keep in RAM for speed
                hnsw_config={"m": 16, "ef_construct": 200},
            ),
        )

        # Create payload indexes for filtering
        self.client.create_payload_index(
            name, "category", "keyword"
        )
        self.client.create_payload_index(
            name, "created_at", "datetime"
        )

    def upsert(self, collection: str, records: list[dict]):
        points = [
            PointStruct(
                id=rec["id"],
                vector=rec["embedding"],
                payload={
                    "text": rec["text"],
                    "category": rec.get("category", ""),
                    "source": rec.get("source", ""),
                    "created_at": rec.get("created_at", ""),
                },
            )
            for rec in records
        ]
        self.client.upsert(collection, points, wait=True)

    def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 5,
        category: str = None,
        min_score: float = 0.0,
    ) -> list[dict]:
        filters = None
        if category:
            filters = Filter(
                must=[
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category),
                    ),
                ],
            )

        results = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=filters,
            limit=top_k,
            score_threshold=min_score,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "text": hit.payload.get("text", ""),
                "metadata": hit.payload,
            }
            for hit in results
        ]

    def search_with_reranking(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 5,
        oversampling: int = 3,
    ) -> list[dict]:
        """Two-stage retrieval: ANN then rerank."""
        # Stage 1: Retrieve more candidates than needed
        candidates = self.search(
            collection, query_vector, top_k=top_k * oversampling
        )

        # Stage 2: Rerank with exact scoring or cross-encoder
        # (In production, use a cross-encoder model here)
        # For now, just return top-k by ANN score
        return candidates[:top_k]
```

### pgvector vs Dedicated Vector DB

```
pgvector (PostgreSQL extension):
✓ No additional infrastructure — lives in your existing DB
✓ Full SQL + vector search in one query (JOINs, aggregation)
✓ ACID transactions across vector and relational data
✓ Good for: < 10M vectors, hybrid queries, simpler ops
✗ Performance ceiling at ~5M vectors
✗ No built-in sharding for horizontal scaling

Dedicated Vector DB (Qdrant, Pinecone, Weaviate, Milvus):
✓ Optimized for vector operations — 10-100x faster at scale
✓ Built-in sharding and replication
✓ Advanced features: multi-tenancy, quantization, hybrid search
✓ Good for: > 10M vectors, high QPS, production RAG
✗ Additional infrastructure to manage
✗ Data consistency between vector DB and primary DB
```

**Vector DB selection guide**: (1) Start with pgvector if you already use PostgreSQL and have < 5M vectors, (2) Use HNSW index for low-latency, high-recall requirements, (3) Use IVF-PQ for billion-scale datasets where memory is constrained, (4) Always normalize embeddings before indexing if using cosine similarity, (5) Pre-filter by metadata, then vector search — not the reverse — for best performance."""
    ),
    (
        "ml/embedding-models-and-chunking",
        r"""Explain text embedding models for vector search including model selection (OpenAI, Cohere, open-source), chunking strategies for documents, handling different content types, embedding caching, and dimension reduction techniques.""",
        r"""## Text Embeddings for Vector Search: Models, Chunking, and Optimization

The quality of your vector search depends more on your embedding and chunking strategy than on the vector database itself. Bad embeddings in a great database still produce bad results.

### Embedding Model Selection

```python
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class EmbeddingModel(ABC):
    """Abstract embedding model interface."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def dimension(self) -> int:
        ...


class OpenAIEmbeddings(EmbeddingModel):
    """OpenAI text-embedding-3-small/large."""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str = None):
        import openai
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self._dim = 1536 if "small" in model else 3072

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Batch up to 2048 texts per call
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def dimension(self) -> int:
        return self._dim


class LocalEmbeddings(EmbeddingModel):
    """Local model using sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self._dim = self.model.get_sentence_embedding_dimension()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # sentence-transformers is synchronous
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,  # Unit vectors for cosine
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def dimension(self) -> int:
        return self._dim


# Model comparison:
# | Model                        | Dim  | Speed  | Quality | Cost     |
# |------------------------------|------|--------|---------|----------|
# | text-embedding-3-small       | 1536 | Fast   | Good    | $0.02/1M |
# | text-embedding-3-large       | 3072 | Medium | Best    | $0.13/1M |
# | BAAI/bge-small-en-v1.5       | 384  | Fast   | Good    | Free     |
# | BAAI/bge-large-en-v1.5       | 1024 | Slow   | Great   | Free     |
# | nomic-embed-text-v1.5        | 768  | Medium | Great   | Free     |
```

### Chunking Strategies

How you split documents into chunks dramatically affects retrieval quality:

```python
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    start_idx: int = 0
    end_idx: int = 0


class DocumentChunker:
    """Multi-strategy document chunker."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        strategy: str = "semantic",
    ):
        self.chunk_size = chunk_size
        self.overlap = chunk_overlap
        self.strategy = strategy

    def chunk(self, text: str, metadata: dict = None) -> list[Chunk]:
        metadata = metadata or {}

        if self.strategy == "fixed":
            return self._fixed_size(text, metadata)
        elif self.strategy == "sentence":
            return self._sentence_boundary(text, metadata)
        elif self.strategy == "semantic":
            return self._semantic(text, metadata)
        elif self.strategy == "recursive":
            return self._recursive(text, metadata)
        raise ValueError(f"Unknown strategy: {self.strategy}")

    def _fixed_size(self, text: str, metadata: dict) -> list[Chunk]:
        """Simple fixed-size chunking with overlap."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            if len(chunk_words) < self.overlap and chunks:
                break
            chunks.append(Chunk(
                text=" ".join(chunk_words),
                metadata={**metadata, "chunk_idx": len(chunks)},
            ))
        return chunks

    def _sentence_boundary(self, text: str, metadata: dict) -> list[Chunk]:
        """Split on sentence boundaries, respect chunk_size."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = []
        current_len = 0

        for sentence in sentences:
            sent_len = len(sentence.split())
            if current_len + sent_len > self.chunk_size and current:
                chunks.append(Chunk(
                    text=" ".join(current),
                    metadata={**metadata, "chunk_idx": len(chunks)},
                ))
                # Keep overlap sentences
                overlap_len = 0
                overlap_start = len(current)
                for j in range(len(current) - 1, -1, -1):
                    overlap_len += len(current[j].split())
                    if overlap_len >= self.overlap:
                        overlap_start = j
                        break
                current = current[overlap_start:]
                current_len = sum(len(s.split()) for s in current)

            current.append(sentence)
            current_len += sent_len

        if current:
            chunks.append(Chunk(
                text=" ".join(current),
                metadata={**metadata, "chunk_idx": len(chunks)},
            ))
        return chunks

    def _recursive(self, text: str, metadata: dict) -> list[Chunk]:
        """Recursive splitting: try larger separators first."""
        separators = ["\n\n", "\n", ". ", " "]

        def _split(text: str, separators: list[str]) -> list[str]:
            if not separators or len(text.split()) <= self.chunk_size:
                return [text]

            sep = separators[0]
            parts = text.split(sep)
            results = []
            current = ""

            for part in parts:
                candidate = current + sep + part if current else part
                if len(candidate.split()) > self.chunk_size:
                    if current:
                        results.append(current)
                    # Try splitting the oversized part with next separator
                    if len(part.split()) > self.chunk_size:
                        results.extend(_split(part, separators[1:]))
                        current = ""
                    else:
                        current = part
                else:
                    current = candidate

            if current:
                results.append(current)
            return results

        texts = _split(text, separators)
        return [
            Chunk(text=t.strip(), metadata={**metadata, "chunk_idx": i})
            for i, t in enumerate(texts) if t.strip()
        ]

    def _semantic(self, text: str, metadata: dict) -> list[Chunk]:
        """Semantic chunking: split where topic changes."""
        # Start with sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 3:
            return [Chunk(text=text, metadata=metadata)]

        # Use sentence-level features to detect topic boundaries
        # (In production, compute sentence embeddings and split where
        #  cosine similarity between adjacent sentences drops)
        # Simplified: use paragraph + heading detection
        return self._recursive(text, metadata)


# Chunking best practices:
# 1. chunk_size 256-1024 tokens depending on model and use case
# 2. Smaller chunks = more precise retrieval, less context
# 3. Larger chunks = more context, less precise
# 4. Overlap 10-20% prevents splitting important context
# 5. Preserve document structure (headers, sections) when possible
```

### Embedding Cache

```python
import hashlib
import json
import sqlite3
from typing import Optional


class EmbeddingCache:
    """Cache embeddings to avoid recomputation."""

    def __init__(self, db_path: str = "embeddings_cache.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                text_hash TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _hash(self, text: str, model: str) -> str:
        content = f"{model}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, text: str, model: str) -> Optional[list[float]]:
        row = self.conn.execute(
            "SELECT embedding FROM embeddings WHERE text_hash = ?",
            (self._hash(text, model),)
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    def put(self, text: str, model: str, embedding: list[float]):
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings (text_hash, model, embedding) VALUES (?, ?, ?)",
            (self._hash(text, model), model, json.dumps(embedding))
        )
        self.conn.commit()

    def get_or_compute(
        self, texts: list[str], model_name: str, embed_fn
    ) -> list[list[float]]:
        """Batch-aware caching: only compute missing embeddings."""
        results = [None] * len(texts)
        to_compute = []
        to_compute_indices = []

        for i, text in enumerate(texts):
            cached = self.get(text, model_name)
            if cached:
                results[i] = cached
            else:
                to_compute.append(text)
                to_compute_indices.append(i)

        if to_compute:
            new_embeddings = embed_fn(to_compute)
            for idx, text, emb in zip(to_compute_indices, to_compute, new_embeddings):
                results[idx] = emb
                self.put(text, model_name, emb)

        return results
```

**Embedding and chunking principles**: (1) Match chunk size to your embedding model's training context — most models work best at 256-512 tokens, (2) Cache embeddings aggressively — they're expensive to compute and deterministic, (3) Use recursive chunking as the default — it respects document structure, (4) Normalize embeddings before storage if using cosine similarity, (5) Test retrieval quality with real queries before scaling — bad chunking can't be fixed by a better database."""
    ),
    (
        "ml/rag-pipeline-architecture",
        r"""Explain RAG (Retrieval-Augmented Generation) pipeline architecture including query preprocessing, retrieval strategies (dense, sparse, hybrid), reranking, context window management, citation generation, and evaluation metrics for RAG systems.""",
        r"""## RAG Pipeline Architecture: Retrieval, Reranking, and Production Patterns

RAG combines the knowledge in your documents with the reasoning ability of LLMs. A well-designed pipeline handles query understanding, efficient retrieval, relevance ranking, and faithful generation.

### Pipeline Overview

```
User Query
    │
    ├── 1. Query Preprocessing
    │      ├── Query expansion/reformulation
    │      └── Intent classification
    │
    ├── 2. Retrieval (fast, recall-focused)
    │      ├── Dense retrieval (vector similarity)
    │      ├── Sparse retrieval (BM25/keyword)
    │      └── Hybrid (combine both)
    │
    ├── 3. Reranking (slow, precision-focused)
    │      └── Cross-encoder scoring
    │
    ├── 4. Context Assembly
    │      ├── Deduplication
    │      ├── Context window fitting
    │      └── Source tracking
    │
    └── 5. Generation
           ├── Prompt construction
           ├── LLM inference
           └── Citation extraction
```

### Full Pipeline Implementation

```python
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class RetrievedDocument:
    id: str
    text: str
    score: float
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGResponse:
    answer: str
    sources: list[dict]
    confidence: float


class RAGPipeline:
    """Production RAG pipeline with hybrid retrieval and reranking."""

    def __init__(
        self,
        embedder,
        vector_store,
        sparse_index,
        reranker,
        llm,
        top_k_retrieval: int = 20,
        top_k_rerank: int = 5,
        max_context_tokens: int = 4000,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.sparse_index = sparse_index
        self.reranker = reranker
        self.llm = llm
        self.top_k_retrieval = top_k_retrieval
        self.top_k_rerank = top_k_rerank
        self.max_context_tokens = max_context_tokens

    async def query(self, user_query: str) -> RAGResponse:
        # Step 1: Query preprocessing
        processed_query = self._preprocess_query(user_query)

        # Step 2: Hybrid retrieval
        candidates = await self._hybrid_retrieve(processed_query)

        # Step 3: Reranking
        reranked = await self._rerank(processed_query, candidates)

        # Step 4: Context assembly
        context, sources = self._assemble_context(reranked)

        # Step 5: Generation
        answer = await self._generate(user_query, context, sources)

        return answer

    def _preprocess_query(self, query: str) -> str:
        """Expand or reformulate the query for better retrieval."""
        # Simple: strip and normalize
        query = query.strip()

        # Advanced: use LLM to generate search queries
        # (HyDE — Hypothetical Document Embeddings)
        # Generate a hypothetical answer, embed THAT for retrieval
        return query

    async def _hybrid_retrieve(
        self, query: str
    ) -> list[RetrievedDocument]:
        """Combine dense and sparse retrieval."""
        # Dense retrieval (semantic similarity)
        query_embedding = (await self.embedder.embed([query]))[0]
        dense_results = await self.vector_store.search(
            query_embedding, top_k=self.top_k_retrieval
        )

        # Sparse retrieval (BM25 keyword matching)
        sparse_results = self.sparse_index.search(
            query, top_k=self.top_k_retrieval
        )

        # Reciprocal Rank Fusion (RRF) to combine results
        return self._reciprocal_rank_fusion(
            [dense_results, sparse_results],
            k=60,  # RRF constant
        )

    def _reciprocal_rank_fusion(
        self, result_lists: list[list], k: int = 60
    ) -> list[RetrievedDocument]:
        """Combine multiple ranked lists using RRF."""
        scores: dict[str, float] = {}
        doc_map: dict[str, RetrievedDocument] = {}

        for results in result_lists:
            for rank, doc in enumerate(results):
                doc_id = doc.id if hasattr(doc, "id") else doc["id"]
                scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
                if doc_id not in doc_map:
                    doc_map[doc_id] = doc

        # Sort by fused score
        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        return [doc_map[doc_id] for doc_id in sorted_ids[:self.top_k_retrieval]]

    async def _rerank(
        self, query: str, candidates: list[RetrievedDocument]
    ) -> list[RetrievedDocument]:
        """Rerank candidates using a cross-encoder."""
        if not candidates:
            return []

        pairs = [(query, doc.text) for doc in candidates]
        scores = await self.reranker.score(pairs)

        for doc, score in zip(candidates, scores):
            doc.score = score

        candidates.sort(key=lambda d: d.score, reverse=True)
        return candidates[:self.top_k_rerank]

    def _assemble_context(
        self, documents: list[RetrievedDocument]
    ) -> tuple[str, list[dict]]:
        """Fit documents into context window with deduplication."""
        seen_texts = set()
        context_parts = []
        sources = []
        total_tokens = 0

        for i, doc in enumerate(documents):
            # Deduplicate
            text_hash = hash(doc.text[:200])
            if text_hash in seen_texts:
                continue
            seen_texts.add(text_hash)

            # Estimate tokens (rough: 1 token ≈ 4 chars)
            doc_tokens = len(doc.text) // 4
            if total_tokens + doc_tokens > self.max_context_tokens:
                # Truncate last document to fit
                remaining = self.max_context_tokens - total_tokens
                truncated = doc.text[:remaining * 4]
                context_parts.append(f"[Source {i+1}]: {truncated}")
                sources.append({"id": doc.id, "source": doc.source, "score": doc.score})
                break

            context_parts.append(f"[Source {i+1}]: {doc.text}")
            sources.append({"id": doc.id, "source": doc.source, "score": doc.score})
            total_tokens += doc_tokens

        return "\n\n".join(context_parts), sources

    async def _generate(
        self, query: str, context: str, sources: list[dict]
    ) -> RAGResponse:
        """Generate answer with citations."""
        prompt = f"""Answer the following question based on the provided context.
If the context doesn't contain enough information, say so.
Cite sources using [Source N] notation.

Context:
{context}

Question: {query}

Answer:"""

        response = await self.llm.generate(prompt)
        answer = response.text

        # Extract which sources were actually cited
        cited_sources = []
        for i, source in enumerate(sources):
            if f"[Source {i+1}]" in answer:
                cited_sources.append(source)

        # Confidence based on retrieval scores
        avg_score = np.mean([s["score"] for s in sources]) if sources else 0

        return RAGResponse(
            answer=answer,
            sources=cited_sources or sources[:3],
            confidence=float(avg_score),
        )
```

### Evaluation Metrics for RAG

```python
class RAGEvaluator:
    """Evaluate RAG pipeline quality."""

    def __init__(self, llm):
        self.llm = llm

    async def evaluate(
        self,
        query: str,
        answer: str,
        context: str,
        reference: str = None,
    ) -> dict:
        """Compute RAG quality metrics."""
        metrics = {}

        # 1. Faithfulness: Is the answer grounded in the context?
        metrics["faithfulness"] = await self._score_faithfulness(
            answer, context
        )

        # 2. Relevance: Does the answer address the query?
        metrics["relevance"] = await self._score_relevance(query, answer)

        # 3. Context recall: Did retrieval find relevant documents?
        if reference:
            metrics["context_recall"] = await self._score_context_recall(
                reference, context
            )

        return metrics

    async def _score_faithfulness(self, answer: str, context: str) -> float:
        """Score 0-1: are all claims in the answer supported by context?"""
        prompt = f"""Given the context and answer below, score the faithfulness
of the answer on a scale of 0.0 to 1.0.
1.0 = every claim in the answer is supported by the context
0.0 = the answer contains unsupported or contradicted claims

Context: {context[:2000]}
Answer: {answer}

Score (just the number):"""

        response = await self.llm.generate(prompt, max_tokens=10)
        try:
            return float(response.text.strip())
        except ValueError:
            return 0.5

    async def _score_relevance(self, query: str, answer: str) -> float:
        prompt = f"""Score how well this answer addresses the question.
1.0 = perfectly answers the question
0.0 = completely irrelevant

Question: {query}
Answer: {answer}

Score (just the number):"""

        response = await self.llm.generate(prompt, max_tokens=10)
        try:
            return float(response.text.strip())
        except ValueError:
            return 0.5
```

**RAG pipeline principles**: (1) Hybrid retrieval (dense + sparse) consistently outperforms either alone, (2) Reranking with a cross-encoder is the highest-leverage improvement for precision, (3) Chunk documents at 256-512 tokens with overlap for optimal retrieval, (4) Always track sources — users need to verify generated answers, (5) Evaluate with faithfulness (is it grounded?) and relevance (does it answer the question?) — not just "does it look good?"."""
    ),
]
