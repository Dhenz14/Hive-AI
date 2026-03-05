"""p16 vector databases"""

PAIRS = [
    (
        "ml/vector-database-fundamentals",
        "Explain vector database fundamentals including embedding storage, similarity search algorithms (HNSW, IVF, PQ), distance metrics (cosine, L2, dot product), indexing strategies, and when to use dedicated vector DBs vs extensions like pgvector. Include Python examples.",
        '''Vector databases store high-dimensional embeddings and enable efficient similarity search -- the backbone of RAG systems, recommendation engines, and semantic search.

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
# Cosine:  Text embeddings (OpenAI, Cohere) -- direction matters, not magnitude
# L2:      Image embeddings, when absolute position matters
# Dot:     When embeddings are pre-normalized (equivalent to cosine, faster)
```

### Approximate Nearest Neighbor (ANN) Algorithms

Exact search is O(n*d) -- too slow for millions of vectors. ANN algorithms trade accuracy for speed:

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
# Memory: Very low (compresses 1536-dim float32 -> 48 bytes)
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
                created_at TIMESTAMPTZ DEFAULT NOW()'''
    ),
    (
        "similarity",
        "} for row in rows ]",
        '''# <=>  Cosine distance (1 - cosine_similarity)
# <->  L2 (Euclidean) distance
# <#>  Negative inner product (for max inner product search)
```

### Using a Dedicated Vector DB (Qdrant example)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range,'''
    ),
    (
        "ml/embedding-models-and-chunking",
        "Explain text embedding models for vector search including model selection (OpenAI, Cohere, open-source), chunking strategies for documents, handling different content types, embedding caching, and dimension reduction techniques.",
        '''The quality of your vector search depends more on your embedding and chunking strategy than on the vector database itself. Bad embeddings in a great database still produce bad results.

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
            input=texts,'''
    ),
    (
        "ml/rag-pipeline-architecture",
        "Explain RAG (Retrieval-Augmented Generation) pipeline architecture including query preprocessing, retrieval strategies (dense, sparse, hybrid), reranking, context window management, citation generation, and evaluation metrics for RAG systems.",
        '''RAG combines the knowledge in your documents with the reasoning ability of LLMs. A well-designed pipeline handles query understanding, efficient retrieval, relevance ranking, and faithful generation.

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
        # (HyDE -- Hypothetical Document Embeddings)
        # Generate a hypothetical answer, embed THAT for retrieval
        return query

    async def _hybrid_retrieve(
        self, query: str
    ) -> list[RetrievedDocument]:
        """Combine dense and sparse retrieval."""
        # Dense retrieval (semantic similarity)
        query_embedding = (await self.embedder.embed([query]))[0]
        dense_results = await self.vector_store.search(
            query_embedding, top_k=self.top_k_retrieval'''
    ),
]
