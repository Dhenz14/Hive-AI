"""Vector search — embeddings, similarity search, RAG patterns, and vector databases."""

PAIRS = [
    (
        "ai/vector-search",
        "Show vector search patterns: embedding generation, similarity search with FAISS/pgvector, and indexing strategies.",
        '''Vector search and similarity patterns:

```python
import numpy as np
from typing import Optional
import hashlib
import json


# --- Embedding generation ---

class EmbeddingService:
    """Generate embeddings using OpenAI or local models."""

    def __init__(self, client, model: str = "text-embedding-3-small",
                 cache=None):
        self.client = client
        self.model = model
        self.cache = cache

    async def embed(self, text: str) -> list[float]:
        # Check cache first
        if self.cache:
            cache_key = f"emb:{hashlib.md5(text.encode()).hexdigest()}"
            cached = await self.cache.get(cache_key)
            if cached:
                return json.loads(cached)

        response = await self.client.embeddings.create(
            model=self.model, input=text
        )
        embedding = response.data[0].embedding

        if self.cache:
            await self.cache.set(cache_key, json.dumps(embedding), ex=86400)
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed for efficiency (max 2048 texts per call)."""
        all_embeddings = []
        for i in range(0, len(texts), 2048):
            batch = texts[i:i + 2048]
            response = await self.client.embeddings.create(
                model=self.model, input=batch
            )
            all_embeddings.extend([d.embedding for d in response.data])
        return all_embeddings


# --- FAISS in-memory search ---

import faiss

class FAISSIndex:
    """Fast in-memory vector search with FAISS."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        # IVF index for large datasets (faster, approximate)
        quantizer = faiss.IndexFlatIP(dimension)  # Inner product
        self.index = faiss.IndexIVFFlat(quantizer, dimension, 100)
        self.id_map = {}  # FAISS index -> document ID
        self.trained = False

    def add(self, doc_id: str, embedding: list[float]):
        vector = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vector)  # Normalize for cosine similarity
        idx = self.index.ntotal
        self.index.add(vector)
        self.id_map[idx] = doc_id

    def train(self, embeddings: list[list[float]]):
        """Train IVF index (required before adding vectors)."""
        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)
        self.index.train(vectors)
        self.trained = True

    def search(self, query_embedding: list[float],
               k: int = 10) -> list[tuple[str, float]]:
        query = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query)

        self.index.nprobe = 10  # Search 10 clusters (accuracy/speed tradeoff)
        scores, indices = self.index.search(query, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx in self.id_map:
                results.append((self.id_map[idx], float(score)))
        return results


# --- PostgreSQL pgvector ---

class PgVectorStore:
    """Vector search with pgvector extension."""

    def __init__(self, pool):
        self.pool = pool

    async def setup(self):
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    embedding vector(1536),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # HNSW index (fast approximate search)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_embedding
                ON documents USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)

    async def upsert(self, doc_id: str, content: str,
                     embedding: list[float], metadata: dict = None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO documents (id, content, embedding, metadata)
                VALUES ($1, $2, $3::vector, $4::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET content = $2, embedding = $3::vector,
                    metadata = $4::jsonb
            """, doc_id, content, str(embedding), json.dumps(metadata or {}))

    async def search(self, query_embedding: list[float],
                     k: int = 10, filter_metadata: dict = None) -> list[dict]:
        where_clause = ""
        params = [str(query_embedding), k]

        if filter_metadata:
            conditions = []
            for i, (key, value) in enumerate(filter_metadata.items(), 3):
                conditions.append(f"metadata->>'{key}' = ${i}")
                params.append(value)
            where_clause = "WHERE " + " AND ".join(conditions)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, content, metadata,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM documents
                {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """, *params)

            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ]

    async def delete(self, doc_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)
```

Vector search patterns:
1. **Normalize embeddings** — use cosine similarity via normalized L2
2. **HNSW index** — fast approximate nearest neighbor (pgvector, FAISS)
3. **Batch embedding** — reduce API calls by batching texts
4. **Cache embeddings** — same text always produces same embedding
5. **Metadata filtering** — combine vector search with structured filters'''
    ),
    (
        "ai/rag-patterns",
        "Show RAG (Retrieval-Augmented Generation) patterns: chunking, retrieval, reranking, and context assembly.",
        '''RAG implementation patterns:

```python
import re
from dataclasses import dataclass, field
from typing import Optional


# --- Document chunking strategies ---

@dataclass
class Chunk:
    content: str
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0
    doc_id: str = ""

def chunk_by_tokens(text: str, max_tokens: int = 500,
                    overlap: int = 50) -> list[Chunk]:
    """Split text into overlapping chunks by approximate token count."""
    words = text.split()
    # Rough approximation: 1 token ≈ 0.75 words
    words_per_chunk = int(max_tokens * 0.75)
    overlap_words = int(overlap * 0.75)

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + words_per_chunk, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append(Chunk(content=chunk_text, chunk_index=len(chunks)))
        start = end - overlap_words
        if start >= len(words):
            break
    return chunks


def chunk_by_semantic(text: str) -> list[Chunk]:
    """Split by semantic boundaries (paragraphs, sections)."""
    # Split on double newlines (paragraphs)
    sections = re.split(r'\n\n+', text)

    chunks = []
    current = ""
    for section in sections:
        if len(current) + len(section) < 2000:
            current += "\n\n" + section if current else section
        else:
            if current:
                chunks.append(Chunk(content=current.strip(),
                                   chunk_index=len(chunks)))
            current = section

    if current:
        chunks.append(Chunk(content=current.strip(),
                           chunk_index=len(chunks)))
    return chunks


def chunk_code(code: str, language: str = "python") -> list[Chunk]:
    """Split code by top-level functions/classes."""
    if language == "python":
        pattern = r'^(class |def |async def )'
        lines = code.split('\n')
        chunks = []
        current_lines = []

        for line in lines:
            if re.match(pattern, line) and current_lines:
                chunks.append(Chunk(
                    content='\n'.join(current_lines),
                    chunk_index=len(chunks),
                    metadata={"language": language},
                ))
                current_lines = []
            current_lines.append(line)

        if current_lines:
            chunks.append(Chunk(
                content='\n'.join(current_lines),
                chunk_index=len(chunks),
                metadata={"language": language},
            ))
        return chunks
    return [Chunk(content=code)]


# --- RAG pipeline ---

class RAGPipeline:
    def __init__(self, embedder, vector_store, llm_client,
                 reranker=None):
        self.embedder = embedder
        self.store = vector_store
        self.llm = llm_client
        self.reranker = reranker

    async def ingest(self, doc_id: str, content: str,
                     metadata: dict = None):
        """Chunk, embed, and store a document."""
        chunks = chunk_by_tokens(content, max_tokens=500, overlap=50)

        for chunk in chunks:
            chunk_id = f"{doc_id}#chunk{chunk.chunk_index}"
            embedding = await self.embedder.embed(chunk.content)
            await self.store.upsert(
                doc_id=chunk_id,
                content=chunk.content,
                embedding=embedding,
                metadata={
                    **(metadata or {}),
                    "doc_id": doc_id,
                    "chunk_index": chunk.chunk_index,
                },
            )

    async def query(self, question: str, k: int = 5,
                    filter_metadata: dict = None) -> str:
        """Retrieve relevant chunks and generate answer."""
        # Step 1: Embed query
        query_embedding = await self.embedder.embed(question)

        # Step 2: Retrieve candidates (fetch more than k for reranking)
        fetch_k = k * 3 if self.reranker else k
        candidates = await self.store.search(
            query_embedding, k=fetch_k,
            filter_metadata=filter_metadata,
        )

        # Step 3: Rerank (optional but improves quality)
        if self.reranker and candidates:
            candidates = await self.reranker.rerank(
                question, candidates, top_k=k
            )
        else:
            candidates = candidates[:k]

        if not candidates:
            return "I don't have enough information to answer that question."

        # Step 4: Assemble context
        context = "\n\n---\n\n".join(
            f"[Source: {c['metadata'].get('doc_id', 'unknown')}]\n{c['content']}"
            for c in candidates
        )

        # Step 5: Generate answer
        response = await self.llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": (
                    "Answer the question based on the provided context. "
                    "If the context doesn't contain relevant information, "
                    "say so. Cite sources when possible."
                )},
                {"role": "user", "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {question}"
                )},
            ],
            temperature=0.1,
        )

        return response.choices[0].message.content


# --- Reranker ---

class CrossEncoderReranker:
    """Rerank results using a cross-encoder model."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)

    async def rerank(self, query: str, candidates: list[dict],
                     top_k: int = 5) -> list[dict]:
        pairs = [(query, c["content"]) for c in candidates]
        scores = self.model.predict(pairs)

        # Sort by reranker score
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return [c for c, _ in scored[:top_k]]
```

RAG patterns:
1. **Chunk with overlap** — prevent information loss at boundaries
2. **Semantic chunking** — split at natural boundaries (paragraphs, functions)
3. **Reranking** — cross-encoder reranking improves retrieval quality significantly
4. **Metadata filtering** — combine vector search with structured filters
5. **Source citation** — include source references in generated answers'''
    ),
]
"""
