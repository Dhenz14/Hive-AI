"""
Batch P6 — RAG Systems Deep Dive
Covers: chunking strategies, hybrid retrieval, reranking, evaluation, agentic RAG.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "rag/chunking-strategies",
        "Explain advanced document chunking strategies for RAG systems including fixed-size, semantic, recursive, and document-structure-aware chunking, covering the impact of chunk size on retrieval quality, overlap strategies, and provide a Python implementation of a production chunking pipeline with metadata preservation, chunk deduplication, and quality scoring for different document types.",
        r"""# Document Chunking for RAG: Beyond Naive Splitting

## Why Chunking Strategy Matters

The quality of a RAG system is bounded by its **retrieval quality**, which is directly determined by how documents are chunked. Poor chunking creates three failure modes: (1) chunks too small lose context needed for accurate answers, (2) chunks too large dilute the relevant signal with irrelevant text, and (3) chunks that split mid-concept force the LLM to reason from incomplete information.

**The key insight**: There is no universal "best" chunk size. The optimal strategy depends on document type, query patterns, embedding model context window, and the downstream LLM's ability to extract relevant information from noise.

## Chunking Strategies Compared

### 1. Fixed-Size Chunking (Baseline)

Split every N tokens/characters with optional overlap. Simple but breaks sentences and concepts arbitrarily.

### 2. Recursive Character Splitting

Split by paragraph first, then sentence, then word — recursively breaking at natural boundaries. Better than fixed-size but still unaware of document structure.

### 3. Semantic Chunking

Use embedding similarity between consecutive sentences to detect topic boundaries. Sentences with similar embeddings stay together; a drop in similarity triggers a chunk break.

### 4. Document-Structure-Aware

Use headers, sections, code blocks, tables, and lists as chunk boundaries. Preserves the author's logical organization.

## Production Implementation

```python
# Production chunking pipeline with multiple strategies
from __future__ import annotations

import dataclasses
import hashlib
import re
from typing import Any, Callable, Optional


@dataclasses.dataclass
class Chunk:
    # A document chunk with rich metadata for retrieval
    text: str
    chunk_id: str
    document_id: str
    chunk_index: int
    metadata: dict[str, Any]

    # Source tracking
    start_char: int = 0
    end_char: int = 0
    page_number: Optional[int] = None
    section_title: Optional[str] = None

    # Quality metrics
    token_count: int = 0
    sentence_count: int = 0
    has_code: bool = False
    has_table: bool = False
    language: str = "en"

    @property
    def content_hash(self) -> str:
        return hashlib.md5(self.text.encode()).hexdigest()[:12]


class TokenCounter:
    # Approximate token counting without loading a tokenizer
    # Rule of thumb: 1 token ~ 4 characters for English
    # For production, use tiktoken or the model's actual tokenizer
    @staticmethod
    def count(text: str) -> int:
        return len(text) // 4


class SentenceSplitter:
    # Split text into sentences, handling edge cases
    SENTENCE_ENDINGS = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z])'  # period/exclamation/question + space + capital
        r'|(?<=\n)\n+'  # double newlines (paragraph breaks)
    )

    # Don't split on common abbreviations
    ABBREVIATIONS = {"mr.", "mrs.", "dr.", "prof.", "sr.", "jr.",
                     "vs.", "etc.", "e.g.", "i.e.", "fig.", "eq."}

    @classmethod
    def split(cls, text: str) -> list[str]:
        # Split into sentences while respecting abbreviations
        sentences = cls.SENTENCE_ENDINGS.split(text)
        # Clean up
        return [s.strip() for s in sentences if s.strip()]


class RecursiveChunker:
    # Recursive character text splitter that respects natural boundaries
    #
    # Strategy: try splitting at the highest-level boundary first
    # (double newlines = paragraphs), then fall back to lower-level
    # boundaries (single newlines, sentences, words) if chunks are
    # still too large.
    #
    # This produces chunks that respect document structure while
    # staying within the target size.

    SEPARATORS = [
        "\n\n",      # paragraph breaks
        "\n",        # line breaks
        ". ",        # sentences
        ", ",        # clauses
        " ",         # words
        "",          # characters (last resort)
    ]

    def __init__(
        self,
        target_size: int = 512,     # target tokens per chunk
        max_size: int = 1024,       # absolute maximum tokens
        overlap: int = 64,          # overlap tokens between chunks
    ) -> None:
        self.target_size = target_size
        self.max_size = max_size
        self.overlap = overlap
        self.counter = TokenCounter()

    def chunk(self, text: str, doc_id: str = "", metadata: dict | None = None) -> list[Chunk]:
        metadata = metadata or {}
        raw_chunks = self._split_recursive(text, self.SEPARATORS)

        # Merge small chunks and add overlap
        merged = self._merge_with_overlap(raw_chunks)

        chunks = []
        char_offset = 0
        for i, chunk_text in enumerate(merged):
            # Find position in original text
            start = text.find(chunk_text[:50], char_offset)
            if start == -1:
                start = char_offset
            end = start + len(chunk_text)

            chunk = Chunk(
                text=chunk_text,
                chunk_id=f"{doc_id}_chunk_{i}",
                document_id=doc_id,
                chunk_index=i,
                metadata=metadata,
                start_char=start,
                end_char=end,
                token_count=self.counter.count(chunk_text),
                sentence_count=len(SentenceSplitter.split(chunk_text)),
                has_code="```" in chunk_text or "def " in chunk_text,
                has_table="|" in chunk_text and "---" in chunk_text,
            )
            chunks.append(chunk)
            char_offset = max(char_offset, start + 1)

        return chunks

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return [text]

        sep = separators[0]
        remaining_seps = separators[1:]

        if not sep:
            # Character-level split (last resort)
            chunks = []
            for i in range(0, len(text), self.target_size * 4):
                chunks.append(text[i:i + self.max_size * 4])
            return chunks

        parts = text.split(sep)
        result: list[str] = []
        current = ""

        for part in parts:
            candidate = f"{current}{sep}{part}" if current else part
            if self.counter.count(candidate) <= self.target_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                # If this single part exceeds target, split further
                if self.counter.count(part) > self.target_size:
                    sub_chunks = self._split_recursive(part, remaining_seps)
                    result.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current:
            result.append(current)

        return result

    def _merge_with_overlap(self, chunks: list[str]) -> list[str]:
        if not chunks:
            return []

        merged: list[str] = []
        for i, chunk in enumerate(chunks):
            if i > 0 and self.overlap > 0:
                # Add overlap from previous chunk
                prev_sentences = SentenceSplitter.split(chunks[i - 1])
                overlap_text = ""
                for sent in reversed(prev_sentences):
                    candidate = f"{sent} {overlap_text}".strip()
                    if self.counter.count(candidate) <= self.overlap:
                        overlap_text = candidate
                    else:
                        break
                if overlap_text:
                    chunk = f"{overlap_text}\n\n{chunk}"

            merged.append(chunk)

        return merged


class SemanticChunker:
    # Semantic chunking using embedding similarity.
    #
    # The insight: consecutive sentences about the same topic have
    # similar embeddings. A significant drop in cosine similarity
    # between consecutive sentences indicates a topic boundary.
    #
    # This produces chunks that are semantically coherent — each
    # chunk discusses one topic, making retrieval more precise.
    #
    # Trade-off: requires running the embedding model during chunking,
    # which is slower than text-based methods. However, the retrieval
    # quality improvement (typically 10-20% better recall) justifies
    # the cost for most applications.

    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]],
        similarity_threshold: float = 0.5,
        min_chunk_size: int = 100,    # minimum tokens
        max_chunk_size: int = 1024,   # maximum tokens
    ) -> None:
        self.embed_fn = embed_fn
        self.threshold = similarity_threshold
        self.min_size = min_chunk_size
        self.max_size = max_chunk_size
        self.counter = TokenCounter()

    def chunk(self, text: str, doc_id: str = "") -> list[Chunk]:
        sentences = SentenceSplitter.split(text)
        if len(sentences) <= 1:
            return [Chunk(
                text=text, chunk_id=f"{doc_id}_0",
                document_id=doc_id, chunk_index=0, metadata={},
                token_count=self.counter.count(text),
            )]

        # Embed all sentences
        embeddings = self.embed_fn(sentences)

        # Find topic boundaries by similarity drop
        boundaries = self._find_boundaries(embeddings)

        # Create chunks from boundary indices
        chunks = []
        start_idx = 0
        for i, boundary_idx in enumerate(boundaries + [len(sentences)]):
            chunk_sentences = sentences[start_idx:boundary_idx]
            chunk_text = " ".join(chunk_sentences)

            # Enforce max size by splitting if needed
            if self.counter.count(chunk_text) > self.max_size:
                sub_chunks = self._split_large_chunk(chunk_sentences, doc_id, len(chunks))
                chunks.extend(sub_chunks)
            else:
                chunks.append(Chunk(
                    text=chunk_text,
                    chunk_id=f"{doc_id}_chunk_{len(chunks)}",
                    document_id=doc_id,
                    chunk_index=len(chunks),
                    metadata={},
                    token_count=self.counter.count(chunk_text),
                    sentence_count=len(chunk_sentences),
                ))

            start_idx = boundary_idx

        return chunks

    def _find_boundaries(self, embeddings: list[list[float]]) -> list[int]:
        # Compute cosine similarity between consecutive sentences
        # and find points where similarity drops below threshold
        boundaries = []
        for i in range(1, len(embeddings)):
            sim = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if sim < self.threshold:
                boundaries.append(i)
        return boundaries

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _split_large_chunk(
        self, sentences: list[str], doc_id: str, start_idx: int
    ) -> list[Chunk]:
        chunks = []
        current: list[str] = []
        for sent in sentences:
            current.append(sent)
            if self.counter.count(" ".join(current)) >= self.max_size:
                chunk_text = " ".join(current[:-1]) if len(current) > 1 else current[0]
                chunks.append(Chunk(
                    text=chunk_text,
                    chunk_id=f"{doc_id}_chunk_{start_idx + len(chunks)}",
                    document_id=doc_id, chunk_index=start_idx + len(chunks),
                    metadata={}, token_count=self.counter.count(chunk_text),
                ))
                current = [sent]
        if current:
            chunk_text = " ".join(current)
            chunks.append(Chunk(
                text=chunk_text,
                chunk_id=f"{doc_id}_chunk_{start_idx + len(chunks)}",
                document_id=doc_id, chunk_index=start_idx + len(chunks),
                metadata={}, token_count=self.counter.count(chunk_text),
            ))
        return chunks


class StructureAwareChunker:
    # Document-structure-aware chunking for Markdown/HTML documents.
    #
    # Uses headers, code blocks, and section boundaries as natural
    # chunk points. Preserves the hierarchical structure by including
    # parent headers in each chunk's metadata.
    #
    # This is the best strategy for technical documentation because
    # authors organize content into logical sections that map well
    # to retrieval units.

    HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```', re.MULTILINE)

    def __init__(self, max_chunk_size: int = 1024) -> None:
        self.max_size = max_chunk_size
        self.counter = TokenCounter()

    def chunk(self, text: str, doc_id: str = "") -> list[Chunk]:
        # Split by headers while preserving hierarchy
        sections = self._extract_sections(text)
        chunks = []

        for section in sections:
            section_text = section["content"]
            if self.counter.count(section_text) <= self.max_size:
                chunks.append(Chunk(
                    text=section_text,
                    chunk_id=f"{doc_id}_chunk_{len(chunks)}",
                    document_id=doc_id,
                    chunk_index=len(chunks),
                    metadata={"headers": section["headers"]},
                    section_title=section["title"],
                    token_count=self.counter.count(section_text),
                    has_code="```" in section_text,
                ))
            else:
                # Section too large: split by paragraphs
                recursive = RecursiveChunker(
                    target_size=self.max_size // 2,
                    max_size=self.max_size,
                )
                sub_chunks = recursive.chunk(section_text, doc_id)
                for sc in sub_chunks:
                    sc.section_title = section["title"]
                    sc.metadata["headers"] = section["headers"]
                    sc.chunk_index = len(chunks)
                    sc.chunk_id = f"{doc_id}_chunk_{len(chunks)}"
                    chunks.append(sc)

        return chunks

    def _extract_sections(self, text: str) -> list[dict]:
        sections = []
        header_stack: list[tuple[int, str]] = []  # (level, title)

        # Split text at header boundaries
        parts = self.HEADER_PATTERN.split(text)

        # parts alternates: [text_before, #level, title, text_after, ...]
        current_content = parts[0] if parts else ""
        i = 1

        while i < len(parts) - 1:
            # Save current section if it has content
            if current_content.strip():
                sections.append({
                    "title": header_stack[-1][1] if header_stack else "Introduction",
                    "headers": [h[1] for h in header_stack],
                    "content": current_content.strip(),
                })

            # Process new header
            level = len(parts[i])  # number of # characters
            title = parts[i + 1]

            # Update header stack
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            header_stack.append((level, title))

            # Get content after this header
            current_content = f"{'#' * level} {title}\n\n"
            if i + 2 < len(parts):
                current_content += parts[i + 2]

            i += 3

        # Don't forget the last section
        if current_content.strip():
            sections.append({
                "title": header_stack[-1][1] if header_stack else "Content",
                "headers": [h[1] for h in header_stack],
                "content": current_content.strip(),
            })

        return sections if sections else [{"title": "Content", "headers": [], "content": text}]


class ChunkDeduplicator:
    # Remove near-duplicate chunks using MinHash.
    #
    # Overlapping chunks and document revisions can create near-duplicates
    # that waste embedding storage and degrade retrieval (multiple
    # results saying the same thing). MinHash provides fast approximate
    # deduplication with configurable similarity threshold.

    def __init__(self, similarity_threshold: float = 0.8, num_hashes: int = 128) -> None:
        self.threshold = similarity_threshold
        self.num_hashes = num_hashes

    def deduplicate(self, chunks: list[Chunk]) -> list[Chunk]:
        if len(chunks) <= 1:
            return chunks

        # Compute shingles and MinHash for each chunk
        signatures = []
        for chunk in chunks:
            shingles = self._get_shingles(chunk.text, k=3)
            sig = self._minhash(shingles)
            signatures.append(sig)

        # Remove chunks that are too similar to an earlier chunk
        keep = [True] * len(chunks)
        for i in range(len(chunks)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(chunks)):
                if not keep[j]:
                    continue
                sim = self._jaccard_from_minhash(signatures[i], signatures[j])
                if sim >= self.threshold:
                    # Keep the longer chunk (more context)
                    if len(chunks[j].text) > len(chunks[i].text):
                        keep[i] = False
                        break
                    else:
                        keep[j] = False

        return [c for c, k in zip(chunks, keep) if k]

    @staticmethod
    def _get_shingles(text: str, k: int = 3) -> set[str]:
        words = text.lower().split()
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

    def _minhash(self, shingles: set[str]) -> list[int]:
        import random
        random.seed(42)
        signature = []
        for _ in range(self.num_hashes):
            min_hash = float('inf')
            for shingle in shingles:
                h = hash(shingle + str(random.random()))
                min_hash = min(min_hash, h)
            signature.append(min_hash)
        return signature

    @staticmethod
    def _jaccard_from_minhash(sig1: list[int], sig2: list[int]) -> float:
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)


def test_recursive_chunker():
    text = """# Introduction

    This is the first paragraph about machine learning. It covers the basics
    of supervised learning and common algorithms.

    ## Neural Networks

    Neural networks are composed of layers of interconnected nodes. Each node
    applies a transformation to its inputs. The most common type is the
    feedforward network.

    ### Backpropagation

    Backpropagation computes gradients by applying the chain rule. This allows
    efficient training of deep networks with many layers.

    ## Decision Trees

    Decision trees split data based on feature thresholds. They are interpretable
    but prone to overfitting without regularization techniques like pruning.
    """

    chunker = RecursiveChunker(target_size=100, max_size=200, overlap=20)
    chunks = chunker.chunk(text, doc_id="ml_doc")

    print(f"Recursive chunker: {len(chunks)} chunks from {len(text)} chars")
    for chunk in chunks:
        print(f"  [{chunk.chunk_index}] {chunk.token_count} tokens: {chunk.text[:60]}...")


def test_structure_aware_chunker():
    text = """# API Reference

## Authentication

All API requests require a Bearer token in the Authorization header.

```python
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("/api/users", headers=headers)
```

## Endpoints

### GET /users

Returns a list of all users with pagination support.

| Parameter | Type | Description |
|-----------|------|-------------|
| page | int | Page number |
| limit | int | Items per page |

### POST /users

Create a new user account.
"""

    chunker = StructureAwareChunker(max_chunk_size=200)
    chunks = chunker.chunk(text, doc_id="api_doc")

    print(f"\nStructure-aware chunker: {len(chunks)} chunks")
    for chunk in chunks:
        print(f"  [{chunk.chunk_index}] section={chunk.section_title}: {chunk.text[:60]}...")
        print(f"    has_code={chunk.has_code}, has_table={chunk.has_table}")


if __name__ == "__main__":
    test_recursive_chunker()
    test_structure_aware_chunker()
    print("\nAll chunking tests passed!")
```

## Chunk Size Impact on Performance

| Chunk Size (tokens) | Recall@5 | Precision@5 | Answer Quality | Best For |
|---------------------|----------|-------------|----------------|----------|
| 64 | High | Low | Poor (missing context) | Fact lookup |
| 128 | High | Medium | Good for factual Q&A | FAQs, definitions |
| **256-512** | **Good** | **Good** | **Best overall** | **General purpose** |
| 1024 | Medium | Good | Good for complex reasoning | Technical docs |
| 2048+ | Low | High | Variable (noise dilution) | Long-form analysis |

## Key Takeaways

- **No single chunk size is optimal** for all use cases — the right strategy depends on document type, query patterns, and embedding model context window
- **Semantic chunking** (embedding-similarity-based) produces the most coherent chunks but requires running the embedding model during ingestion — a good trade-off for high-quality RAG
- **Structure-aware chunking** leverages the author's logical organization and preserves **hierarchical context** (parent headers) — best for technical documentation
- **Chunk overlap** (10-20% of chunk size) prevents information loss at chunk boundaries but increases storage requirements — always worth the cost for Q&A systems
- **Deduplication** is essential when processing document revisions or overlapping sources — near-duplicate chunks waste embedding storage and return redundant retrieval results
"""
    ),
    (
        "rag/hybrid-retrieval",
        "Explain hybrid retrieval for RAG systems combining dense vector search with sparse lexical search, covering BM25 and dense embedding fusion strategies, reciprocal rank fusion, learned sparse representations like SPLADE, and provide a Python implementation of a complete hybrid retrieval pipeline with configurable fusion weights, query expansion, and retrieval evaluation metrics.",
        r"""# Hybrid Retrieval: Combining Dense and Sparse Search

## Why Hybrid Beats Either Alone

Dense retrieval (embedding-based) excels at **semantic matching** — finding documents that mean the same thing even with different words. But it struggles with **exact term matching** — a query for "error code E1234" will miss documents containing that exact code if the embedding doesn't capture it.

Sparse retrieval (BM25/TF-IDF) excels at **exact matching** and **rare terms** but fails on **synonyms and paraphrasing**. A query for "how to fix memory leaks" won't match documents about "resolving heap exhaustion."

**Hybrid retrieval** combines both, achieving **5-15% better recall** than either method alone across standard benchmarks (BEIR, MTEB). This improvement compounds downstream — better retrieval means better LLM answers.

## Fusion Strategies

```python
# Complete hybrid retrieval pipeline
from __future__ import annotations

import dataclasses
import math
import re
from collections import Counter, defaultdict
from typing import Any, Callable, Optional


@dataclasses.dataclass
class Document:
    # A document in the retrieval corpus
    doc_id: str
    text: str
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    embedding: list[float] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class SearchResult:
    doc_id: str
    score: float
    text: str
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    source: str = ""  # "dense", "sparse", or "hybrid"


class BM25Index:
    # BM25 sparse retrieval index.
    #
    # BM25 scores documents based on term frequency (TF), inverse
    # document frequency (IDF), and document length normalization.
    # It remains competitive with neural retrievers for keyword-heavy
    # queries, which is why hybrid retrieval includes it.
    #
    # Parameters:
    # - k1 controls TF saturation (1.2-2.0 typical)
    # - b controls length normalization (0.75 typical)

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: dict[str, Document] = {}
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self.inverted_index: dict[str, dict[str, int]] = {}  # term -> {doc_id: tf}
        self.doc_count: int = 0

    def _tokenize(self, text: str) -> list[str]:
        # Simple tokenization: lowercase, split on non-alphanumeric
        return re.findall(r'\w+', text.lower())

    def add_document(self, doc: Document) -> None:
        tokens = self._tokenize(doc.text)
        self.documents[doc.doc_id] = doc
        self.doc_lengths[doc.doc_id] = len(tokens)
        self.doc_count += 1

        # Update average document length
        total = sum(self.doc_lengths.values())
        self.avg_doc_length = total / self.doc_count

        # Update inverted index
        tf = Counter(tokens)
        for term, count in tf.items():
            if term not in self.inverted_index:
                self.inverted_index[term] = {}
            self.inverted_index[term][doc.doc_id] = count

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        query_tokens = self._tokenize(query)
        scores: dict[str, float] = defaultdict(float)

        for token in query_tokens:
            if token not in self.inverted_index:
                continue

            posting_list = self.inverted_index[token]
            df = len(posting_list)  # document frequency
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

            for doc_id, tf in posting_list.items():
                doc_len = self.doc_lengths[doc_id]
                # BM25 scoring formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self.avg_doc_length
                )
                scores[doc_id] += idf * numerator / denominator

        # Sort by score and return top_k
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                doc_id=doc_id,
                score=score,
                text=self.documents[doc_id].text,
                metadata=self.documents[doc_id].metadata,
                source="sparse",
            )
            for doc_id, score in ranked[:top_k]
        ]


class DenseIndex:
    # Dense vector retrieval using cosine similarity.
    #
    # In production, use a vector database (Qdrant, Pinecone, Weaviate)
    # for efficient approximate nearest neighbor search (HNSW).
    # This brute-force implementation is for educational clarity.

    def __init__(self, embed_fn: Callable[[str], list[float]]) -> None:
        self.embed_fn = embed_fn
        self.documents: dict[str, Document] = {}

    def add_document(self, doc: Document) -> None:
        if not doc.embedding:
            doc.embedding = self.embed_fn(doc.text)
        self.documents[doc.doc_id] = doc

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        query_embedding = self.embed_fn(query)
        scores = []

        for doc_id, doc in self.documents.items():
            sim = self._cosine_similarity(query_embedding, doc.embedding)
            scores.append((doc_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                doc_id=doc_id,
                score=score,
                text=self.documents[doc_id].text,
                metadata=self.documents[doc_id].metadata,
                source="dense",
            )
            for doc_id, score in scores[:top_k]
        ]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class HybridRetriever:
    # Hybrid retrieval combining dense and sparse search.
    #
    # Fusion strategy options:
    # 1. Score interpolation: hybrid = alpha * dense + (1-alpha) * sparse
    # 2. Reciprocal Rank Fusion (RRF): position-based, no score normalization needed
    # 3. Learned fusion: train a model to weight sources (requires labeled data)
    #
    # RRF is the recommended default because it's robust to score
    # distribution differences between dense and sparse retrievers.

    def __init__(
        self,
        sparse_index: BM25Index,
        dense_index: DenseIndex,
        fusion: str = "rrf",        # "rrf", "interpolation", or "max"
        alpha: float = 0.5,          # weight for dense in interpolation
        rrf_k: int = 60,            # RRF constant
    ) -> None:
        self.sparse = sparse_index
        self.dense = dense_index
        self.fusion = fusion
        self.alpha = alpha
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        top_k: int = 10,
        sparse_weight: Optional[float] = None,
    ) -> list[SearchResult]:
        # Run both retrievers
        sparse_results = self.sparse.search(query, top_k=top_k * 2)
        dense_results = self.dense.search(query, top_k=top_k * 2)

        if self.fusion == "rrf":
            return self._rrf_fusion(sparse_results, dense_results, top_k)
        elif self.fusion == "interpolation":
            alpha = 1.0 - sparse_weight if sparse_weight is not None else self.alpha
            return self._score_interpolation(
                sparse_results, dense_results, alpha, top_k
            )
        else:
            return self._max_fusion(sparse_results, dense_results, top_k)

    def _rrf_fusion(
        self,
        sparse: list[SearchResult],
        dense: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        # Reciprocal Rank Fusion (Cormack et al., 2009)
        #
        # RRF score = sum over retrievers of: 1 / (k + rank)
        #
        # Why RRF works well:
        # 1. No score normalization needed (works on ranks, not scores)
        # 2. Robust to outlier scores in one retriever
        # 3. Documents found by both retrievers get a significant boost
        # 4. Constant k controls how much top ranks are favored (60 is standard)
        scores: dict[str, float] = defaultdict(float)
        doc_map: dict[str, SearchResult] = {}

        for rank, result in enumerate(sparse):
            scores[result.doc_id] += 1.0 / (self.rrf_k + rank + 1)
            doc_map[result.doc_id] = result

        for rank, result in enumerate(dense):
            scores[result.doc_id] += 1.0 / (self.rrf_k + rank + 1)
            doc_map[result.doc_id] = result

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                doc_id=doc_id,
                score=score,
                text=doc_map[doc_id].text,
                metadata=doc_map[doc_id].metadata,
                source="hybrid",
            )
            for doc_id, score in ranked[:top_k]
        ]

    def _score_interpolation(
        self,
        sparse: list[SearchResult],
        dense: list[SearchResult],
        alpha: float,
        top_k: int,
    ) -> list[SearchResult]:
        # Linear interpolation of normalized scores
        # Requires min-max normalization because BM25 and cosine
        # similarity have different score ranges

        def normalize(results: list[SearchResult]) -> dict[str, float]:
            if not results:
                return {}
            scores = [r.score for r in results]
            min_s, max_s = min(scores), max(scores)
            range_s = max_s - min_s if max_s != min_s else 1.0
            return {
                r.doc_id: (r.score - min_s) / range_s
                for r in results
            }

        sparse_norm = normalize(sparse)
        dense_norm = normalize(dense)
        doc_map = {r.doc_id: r for r in sparse + dense}

        combined: dict[str, float] = defaultdict(float)
        for doc_id, score in sparse_norm.items():
            combined[doc_id] += (1 - alpha) * score
        for doc_id, score in dense_norm.items():
            combined[doc_id] += alpha * score

        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                doc_id=doc_id, score=score,
                text=doc_map[doc_id].text,
                metadata=doc_map[doc_id].metadata,
                source="hybrid",
            )
            for doc_id, score in ranked[:top_k]
        ]

    def _max_fusion(
        self,
        sparse: list[SearchResult],
        dense: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        # Take the max score from either retriever
        scores: dict[str, float] = {}
        doc_map: dict[str, SearchResult] = {}
        for r in sparse + dense:
            if r.doc_id not in scores or r.score > scores[r.doc_id]:
                scores[r.doc_id] = r.score
                doc_map[r.doc_id] = r

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                doc_id=doc_id, score=score,
                text=doc_map[doc_id].text,
                metadata=doc_map[doc_id].metadata, source="hybrid",
            )
            for doc_id, score in ranked[:top_k]
        ]


class RetrievalEvaluator:
    # Evaluate retrieval quality with standard IR metrics
    #
    # Metrics:
    # - Recall@K: fraction of relevant docs in top K
    # - Precision@K: fraction of top K that are relevant
    # - MRR: reciprocal rank of first relevant result
    # - NDCG@K: normalized discounted cumulative gain

    @staticmethod
    def recall_at_k(
        results: list[SearchResult],
        relevant_ids: set[str],
        k: int,
    ) -> float:
        retrieved = {r.doc_id for r in results[:k]}
        return len(retrieved & relevant_ids) / max(len(relevant_ids), 1)

    @staticmethod
    def precision_at_k(
        results: list[SearchResult],
        relevant_ids: set[str],
        k: int,
    ) -> float:
        retrieved = [r.doc_id for r in results[:k]]
        relevant_count = sum(1 for doc_id in retrieved if doc_id in relevant_ids)
        return relevant_count / k

    @staticmethod
    def mrr(results: list[SearchResult], relevant_ids: set[str]) -> float:
        for i, result in enumerate(results):
            if result.doc_id in relevant_ids:
                return 1.0 / (i + 1)
        return 0.0

    @staticmethod
    def ndcg_at_k(
        results: list[SearchResult],
        relevance_scores: dict[str, float],
        k: int,
    ) -> float:
        dcg = 0.0
        for i, result in enumerate(results[:k]):
            rel = relevance_scores.get(result.doc_id, 0.0)
            dcg += rel / math.log2(i + 2)  # i+2 because log2(1) = 0

        # Ideal DCG
        ideal_rels = sorted(relevance_scores.values(), reverse=True)[:k]
        idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

        return dcg / idcg if idcg > 0 else 0.0


def test_hybrid_retrieval():
    # Simulated embedding function (random for demo)
    import random
    random.seed(42)
    def mock_embed(text: str) -> list[float]:
        random.seed(hash(text) % 2**31)
        return [random.gauss(0, 1) for _ in range(64)]

    # Build indices
    sparse_idx = BM25Index()
    dense_idx = DenseIndex(mock_embed)

    docs = [
        Document("d1", "Python async await coroutines event loop concurrency"),
        Document("d2", "JavaScript promises callbacks async programming patterns"),
        Document("d3", "Database query optimization index performance tuning"),
        Document("d4", "Python asyncio tutorial for beginners with examples"),
        Document("d5", "Error code E1234 connection timeout database driver"),
    ]

    for doc in docs:
        sparse_idx.add_document(doc)
        dense_idx.add_document(doc)

    hybrid = HybridRetriever(sparse_idx, dense_idx, fusion="rrf")

    # Query 1: Semantic match (dense should excel)
    results = hybrid.search("how to write concurrent code in Python", top_k=3)
    print("Semantic query results:")
    for r in results:
        print(f"  [{r.doc_id}] score={r.score:.4f}: {r.text[:50]}")

    # Query 2: Exact match (sparse should excel)
    results = hybrid.search("error code E1234", top_k=3)
    print("\nExact match query results:")
    for r in results:
        print(f"  [{r.doc_id}] score={r.score:.4f}: {r.text[:50]}")

    # Evaluate
    evaluator = RetrievalEvaluator()
    relevant = {"d1", "d4"}  # relevant for Python async query
    results = hybrid.search("Python async programming", top_k=5)
    print(f"\nEvaluation metrics:")
    print(f"  Recall@3: {evaluator.recall_at_k(results, relevant, 3):.2f}")
    print(f"  Precision@3: {evaluator.precision_at_k(results, relevant, 3):.2f}")
    print(f"  MRR: {evaluator.mrr(results, relevant):.2f}")


if __name__ == "__main__":
    test_hybrid_retrieval()
    print("\nHybrid retrieval tests passed!")
```

## Fusion Strategy Comparison

| Strategy | Strengths | Weaknesses | When to Use |
|----------|-----------|------------|-------------|
| **RRF** (k=60) | No normalization needed, robust | Ignores score magnitude | Default choice, production |
| **Score interpolation** | Tunable alpha, preserves confidence | Sensitive to score distributions | When you have eval data to tune alpha |
| **Max fusion** | Simple, fast | Doesn't boost dual-retrieval docs | Quick prototyping |
| **Learned fusion** | Optimal weights per query type | Requires training data, complexity | Enterprise with eval infrastructure |

## Key Takeaways

- **Hybrid retrieval consistently outperforms** either dense or sparse alone by 5-15% on recall metrics, because each method catches what the other misses
- **Reciprocal Rank Fusion** is the recommended default fusion strategy because it operates on ranks (not scores), making it robust to the different score distributions of BM25 and cosine similarity
- For **exact term matching** (error codes, API names, product IDs), sparse retrieval is essential — dense embeddings often fail to capture exact string matches
- **Query expansion** (adding synonyms or LLM-generated paraphrases to the query) can further boost recall by 5-10%, especially for sparse retrieval
- **Evaluation is non-negotiable**: track Recall@K, MRR, and NDCG with a labeled dataset to make data-driven decisions about fusion weights and retrieval parameters
"""
    ),
    (
        "rag/reranking-pipelines",
        "Explain reranking in RAG pipelines including cross-encoder rerankers, ColBERT late interaction, LLM-based reranking, and provide a Python implementation of a multi-stage retrieval pipeline with initial retrieval, cross-encoder reranking, diversity-aware selection, and context window packing for optimal LLM prompt construction.",
        r"""# Reranking: The Second Stage of RAG Retrieval

## Why Reranking Matters

First-stage retrieval (BM25 or dense) is optimized for **recall** — casting a wide net to find candidate documents. But these candidates are roughly ordered. A **cross-encoder reranker** takes these candidates and produces much more accurate relevance scores by jointly encoding the query and each document together.

**The numbers**: Adding a cross-encoder reranker typically improves **NDCG@10 by 10-25%** over first-stage retrieval alone. This is one of the highest-impact improvements you can make to a RAG pipeline.

**Why not use cross-encoders for first-stage retrieval?** Because cross-encoders score one (query, document) pair at a time — scoring 1 million documents would require 1 million forward passes. First-stage retrieval narrows to ~100 candidates, making cross-encoder scoring practical.

## Multi-Stage Pipeline

```python
# Complete multi-stage RAG retrieval pipeline
from __future__ import annotations

import dataclasses
import math
from typing import Any, Callable, Optional


@dataclasses.dataclass
class RankedDocument:
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    stage: str = ""
    relevance_explanation: str = ""


class CrossEncoderReranker:
    # Cross-encoder reranker for second-stage scoring.
    #
    # Unlike bi-encoders (which encode query and document separately),
    # cross-encoders encode them TOGETHER with full attention. This
    # captures fine-grained query-document interactions that bi-encoders
    # miss, like negation ("NOT Python") and specific requirements.
    #
    # Models: ms-marco-MiniLM-L-12-v2 (fast), bge-reranker-v2-m3 (accurate)
    #
    # In production, use sentence-transformers CrossEncoder or
    # the Cohere/Jina reranking API.

    def __init__(
        self,
        score_fn: Callable[[str, str], float],
        batch_size: int = 32,
    ) -> None:
        # score_fn takes (query, document) and returns relevance score
        self.score_fn = score_fn
        self.batch_size = batch_size

    def rerank(
        self,
        query: str,
        documents: list[RankedDocument],
        top_k: Optional[int] = None,
    ) -> list[RankedDocument]:
        # Score each document against the query
        scored = []
        for doc in documents:
            score = self.score_fn(query, doc.text)
            scored.append(RankedDocument(
                doc_id=doc.doc_id,
                text=doc.text,
                score=score,
                metadata=doc.metadata,
                stage="reranked",
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k] if top_k else scored


class LLMReranker:
    # LLM-based reranker using the language model itself to score relevance.
    #
    # This approach uses the generation model to evaluate whether each
    # document is relevant to the query. It's slower and more expensive
    # than cross-encoder reranking, but can capture more nuanced relevance
    # because it uses the same model that will generate the answer.
    #
    # Common approaches:
    # 1. Pointwise: "Is this document relevant? Score 1-5"
    # 2. Listwise: "Rank these documents by relevance"
    # 3. Pairwise: "Which document is more relevant, A or B?"
    #
    # Pointwise is simplest and most practical for production.

    def __init__(
        self,
        llm_fn: Callable[[str], str],
        max_docs: int = 20,
    ) -> None:
        self.llm_fn = llm_fn
        self.max_docs = max_docs

    def rerank(
        self,
        query: str,
        documents: list[RankedDocument],
        top_k: int = 5,
    ) -> list[RankedDocument]:
        # Pointwise relevance scoring with the LLM
        scored = []
        for doc in documents[:self.max_docs]:
            prompt = (
                f"Rate the relevance of this document to the query on a scale of 0-10.\n"
                f"Query: {query}\n"
                f"Document: {doc.text[:500]}\n"
                f"Score (0-10):"
            )
            response = self.llm_fn(prompt)
            try:
                score = float(response.strip().split()[0])
                score = max(0, min(10, score))
            except (ValueError, IndexError):
                score = 0.0

            scored.append(RankedDocument(
                doc_id=doc.doc_id,
                text=doc.text,
                score=score,
                metadata=doc.metadata,
                stage="llm_reranked",
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


class DiversitySelector:
    # Maximal Marginal Relevance (MMR) for diversity-aware selection.
    #
    # After reranking, the top results might all cover the same aspect
    # of the query. MMR balances relevance with diversity by penalizing
    # documents similar to already-selected ones.
    #
    # This is critical for RAG because the LLM needs diverse context
    # to generate comprehensive answers, not five paraphrases of the
    # same information.
    #
    # lambda_param controls the relevance-diversity trade-off:
    # - lambda=1.0: pure relevance (no diversity)
    # - lambda=0.5: balanced (recommended)
    # - lambda=0.0: pure diversity (ignores relevance)

    def __init__(
        self,
        similarity_fn: Callable[[str, str], float],
        lambda_param: float = 0.5,
    ) -> None:
        self.similarity_fn = similarity_fn
        self.lambda_param = lambda_param

    def select(
        self,
        documents: list[RankedDocument],
        top_k: int = 5,
    ) -> list[RankedDocument]:
        if len(documents) <= top_k:
            return documents

        selected: list[RankedDocument] = []
        remaining = list(documents)

        # Greedy MMR selection
        for _ in range(top_k):
            best_score = float("-inf")
            best_idx = 0

            for i, doc in enumerate(remaining):
                # Relevance component (from reranker score)
                relevance = doc.score

                # Diversity component (max similarity to already selected)
                if selected:
                    max_sim = max(
                        self.similarity_fn(doc.text, s.text)
                        for s in selected
                    )
                else:
                    max_sim = 0.0

                # MMR score: balance relevance and diversity
                mmr_score = (
                    self.lambda_param * relevance
                    - (1 - self.lambda_param) * max_sim
                )

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected


class ContextWindowPacker:
    # Pack selected documents into the LLM's context window optimally.
    #
    # Challenges:
    # 1. Documents may exceed the context window — need truncation
    # 2. More relevant documents should get more space
    # 3. Document order affects LLM attention (lost-in-the-middle effect)
    #
    # The "lost in the middle" effect (Liu et al., 2023): LLMs attend
    # more to the beginning and end of the context. Place the most
    # relevant documents first and last, less relevant in the middle.

    def __init__(
        self,
        max_context_tokens: int = 4096,
        token_counter: Callable[[str], int] = lambda x: len(x) // 4,
    ) -> None:
        self.max_tokens = max_context_tokens
        self.count_tokens = token_counter

    def pack(
        self,
        documents: list[RankedDocument],
        query: str,
        system_prompt_tokens: int = 200,
        answer_budget_tokens: int = 1024,
    ) -> str:
        # Pack documents into context, respecting token budget
        available = self.max_tokens - system_prompt_tokens - answer_budget_tokens
        query_tokens = self.count_tokens(query)
        available -= query_tokens

        if available <= 0:
            return ""

        # Allocate space proportionally to relevance score
        total_score = sum(max(d.score, 0.1) for d in documents)
        allocations: list[tuple[RankedDocument, int]] = []

        for doc in documents:
            # Proportional allocation with minimum guarantee
            weight = max(doc.score, 0.1) / total_score
            doc_budget = max(100, int(available * weight))
            allocations.append((doc, doc_budget))

        # Build context with lost-in-the-middle mitigation
        # Place docs in order: most relevant, least relevant, ..., 2nd most
        if len(allocations) >= 3:
            reordered = self._sandwich_order(allocations)
        else:
            reordered = allocations

        context_parts = []
        used_tokens = 0

        for doc, budget in reordered:
            doc_text = doc.text
            doc_tokens = self.count_tokens(doc_text)

            if doc_tokens > budget:
                # Truncate to budget
                char_budget = budget * 4  # approximate
                doc_text = doc_text[:char_budget] + "..."

            if used_tokens + self.count_tokens(doc_text) > available:
                break

            # Format with source attribution
            source = doc.metadata.get("source", doc.doc_id)
            context_parts.append(
                f"[Source: {source}]\n{doc_text}"
            )
            used_tokens += self.count_tokens(doc_text)

        return "\n\n---\n\n".join(context_parts)

    @staticmethod
    def _sandwich_order(
        items: list[tuple[RankedDocument, int]],
    ) -> list[tuple[RankedDocument, int]]:
        # Reorder to mitigate "lost in the middle" effect:
        # Place most relevant at start and end, least relevant in middle
        n = len(items)
        reordered: list[Optional[tuple[RankedDocument, int]]] = [None] * n

        left, right = 0, n - 1
        for i, item in enumerate(items):
            if i % 2 == 0:
                reordered[left] = item
                left += 1
            else:
                reordered[right] = item
                right -= 1

        return [x for x in reordered if x is not None]


class MultiStageRAGPipeline:
    # Complete multi-stage retrieval pipeline for RAG.
    #
    # Stages:
    # 1. Initial retrieval: BM25 + dense (hybrid), retrieve ~100 candidates
    # 2. Cross-encoder reranking: score top ~20-50 candidates with cross-encoder
    # 3. Diversity selection: MMR to ensure diverse context
    # 4. Context packing: fit selected documents into LLM context window
    #
    # Each stage reduces the candidate set while increasing scoring quality.

    def __init__(
        self,
        retriever_fn: Callable[[str, int], list[RankedDocument]],
        reranker: CrossEncoderReranker,
        diversity_selector: DiversitySelector,
        context_packer: ContextWindowPacker,
    ) -> None:
        self.retrieve = retriever_fn
        self.reranker = reranker
        self.diversity = diversity_selector
        self.packer = context_packer

    def run(
        self,
        query: str,
        initial_k: int = 100,
        rerank_k: int = 20,
        final_k: int = 5,
    ) -> tuple[str, list[RankedDocument]]:
        # Stage 1: Initial retrieval
        candidates = self.retrieve(query, initial_k)

        # Stage 2: Cross-encoder reranking
        reranked = self.reranker.rerank(query, candidates, top_k=rerank_k)

        # Stage 3: Diversity selection
        diverse = self.diversity.select(reranked, top_k=final_k)

        # Stage 4: Context packing
        context = self.packer.pack(diverse, query)

        return context, diverse


def test_pipeline():
    # Mock components for testing
    import random
    random.seed(42)

    def mock_retrieve(query: str, k: int) -> list[RankedDocument]:
        return [
            RankedDocument(f"doc_{i}", f"Content about {query} variant {i}",
                          random.random(), {"source": f"source_{i}"})
            for i in range(k)
        ]

    def mock_cross_encoder(query: str, doc: str) -> float:
        # Simulate: longer docs with query terms score higher
        overlap = len(set(query.lower().split()) & set(doc.lower().split()))
        return overlap / max(len(query.split()), 1) + random.random() * 0.1

    def mock_similarity(a: str, b: str) -> float:
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / max(union, 1)

    reranker = CrossEncoderReranker(mock_cross_encoder)
    diversity = DiversitySelector(mock_similarity, lambda_param=0.6)
    packer = ContextWindowPacker(max_context_tokens=2048)

    pipeline = MultiStageRAGPipeline(
        retriever_fn=mock_retrieve,
        reranker=reranker,
        diversity_selector=diversity,
        context_packer=packer,
    )

    context, docs = pipeline.run(
        "How does Python async await work?",
        initial_k=50, rerank_k=10, final_k=5,
    )

    print(f"Pipeline returned {len(docs)} documents")
    print(f"Context length: {len(context)} chars")
    for doc in docs:
        print(f"  [{doc.doc_id}] score={doc.score:.4f}: {doc.text[:50]}")


if __name__ == "__main__":
    test_pipeline()
    print("\nMulti-stage RAG pipeline tests passed!")
```

## Stage-by-Stage Impact

| Stage | Candidates | Scoring Quality | Latency Added |
|-------|-----------|----------------|---------------|
| **BM25 + Dense** | 1M → 100 | Rough ranking | 10-50ms |
| **Cross-encoder** | 100 → 20 | High-quality relevance | 50-200ms |
| **MMR diversity** | 20 → 5 | Diverse + relevant | <1ms |
| **Context packing** | 5 → prompt | Optimized for LLM | <1ms |

## Key Takeaways

- **Cross-encoder reranking** improves NDCG@10 by 10-25% over first-stage retrieval alone — it's the single highest-impact addition to a RAG pipeline
- **Maximal Marginal Relevance** ensures the LLM receives diverse context rather than five paraphrases of the same information — set lambda=0.5-0.7 for balanced relevance and diversity
- The **lost-in-the-middle effect** means LLMs attend more to the beginning and end of context — place the most relevant documents at these positions
- **Context window packing** should allocate space proportionally to document relevance and always reserve budget for the LLM's answer generation
- The full multi-stage pipeline adds ~100-300ms latency but improves answer quality significantly — this trade-off is almost always worthwhile for production RAG systems
"""
    ),
    (
        "rag/evaluation-frameworks",
        "Explain RAG system evaluation methodologies including component-level metrics (retrieval recall, context relevance, answer faithfulness), end-to-end evaluation with RAGAS framework, human evaluation protocols, and provide a Python implementation of a complete RAG evaluation suite with automated scoring, regression detection, and A/B testing support.",
        r"""# RAG Evaluation: Measuring What Matters

## The RAG Evaluation Challenge

RAG systems have multiple failure modes, and each requires different evaluation: (1) **retrieval failure** — the right documents aren't found, (2) **context relevance failure** — retrieved documents are irrelevant to the query, (3) **faithfulness failure** — the LLM generates information not in the context (hallucination), (4) **answer completeness failure** — the answer is correct but misses important information.

Evaluating only the final answer quality misses the root cause of failures. **Component-level evaluation** identifies which stage needs improvement.

## Evaluation Metrics

```python
# Complete RAG evaluation framework
from __future__ import annotations

import dataclasses
import json
import math
import statistics
from typing import Any, Callable, Optional


@dataclasses.dataclass
class RAGResult:
    # A single RAG system output to evaluate
    query: str
    answer: str
    retrieved_contexts: list[str]
    ground_truth_answer: Optional[str] = None
    ground_truth_contexts: Optional[list[str]] = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class EvalScores:
    # Evaluation scores for a single RAG result
    context_relevance: float = 0.0    # are retrieved docs relevant?
    context_recall: float = 0.0        # are ground truth docs retrieved?
    faithfulness: float = 0.0          # is answer grounded in context?
    answer_relevance: float = 0.0      # does answer address the query?
    answer_correctness: float = 0.0    # is answer factually correct?

    @property
    def overall(self) -> float:
        # Weighted overall score
        return (
            0.25 * self.context_relevance
            + 0.15 * self.context_recall
            + 0.30 * self.faithfulness
            + 0.15 * self.answer_relevance
            + 0.15 * self.answer_correctness
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "context_relevance": round(self.context_relevance, 3),
            "context_recall": round(self.context_recall, 3),
            "faithfulness": round(self.faithfulness, 3),
            "answer_relevance": round(self.answer_relevance, 3),
            "answer_correctness": round(self.answer_correctness, 3),
            "overall": round(self.overall, 3),
        }


class ContextRelevanceScorer:
    # Score how relevant retrieved contexts are to the query.
    #
    # Method: Use the LLM to judge whether each sentence in the
    # retrieved context is relevant to answering the query.
    # Score = (relevant sentences) / (total sentences)
    #
    # A low context_relevance score means the retriever is returning
    # documents that don't help answer the query -- fix the retriever.

    def __init__(self, llm_judge: Callable[[str], str]) -> None:
        self.judge = llm_judge

    def score(self, query: str, contexts: list[str]) -> float:
        if not contexts:
            return 0.0

        all_sentences = []
        for ctx in contexts:
            sentences = [s.strip() for s in ctx.split('.') if s.strip()]
            all_sentences.extend(sentences)

        if not all_sentences:
            return 0.0

        relevant_count = 0
        for sentence in all_sentences:
            prompt = (
                f"Is this sentence relevant to answering the query?\n"
                f"Query: {query}\n"
                f"Sentence: {sentence}\n"
                f"Answer only 'yes' or 'no':"
            )
            response = self.judge(prompt).strip().lower()
            if response.startswith("yes"):
                relevant_count += 1

        return relevant_count / len(all_sentences)


class FaithfulnessScorer:
    # Score whether the answer is grounded in the retrieved contexts.
    #
    # Method: Extract claims from the answer, then check if each
    # claim is supported by the context. Unsupported claims indicate
    # hallucination.
    #
    # Score = (supported claims) / (total claims)
    #
    # A low faithfulness score means the LLM is hallucinating --
    # this is the most critical metric for production RAG systems
    # because hallucinated answers erode user trust.

    def __init__(self, llm_judge: Callable[[str], str]) -> None:
        self.judge = llm_judge

    def score(self, answer: str, contexts: list[str]) -> float:
        # Step 1: Extract claims from the answer
        claims = self._extract_claims(answer)
        if not claims:
            return 1.0  # no claims to verify

        # Step 2: Verify each claim against context
        context_text = "\n".join(contexts)
        supported = 0

        for claim in claims:
            prompt = (
                f"Is this claim supported by the provided context?\n"
                f"Context: {context_text[:2000]}\n"
                f"Claim: {claim}\n"
                f"Answer only 'supported' or 'unsupported':"
            )
            response = self.judge(prompt).strip().lower()
            if "supported" in response and "unsupported" not in response:
                supported += 1

        return supported / len(claims)

    def _extract_claims(self, answer: str) -> list[str]:
        # Simple claim extraction: split into sentences
        # Production: use NLI or the LLM to decompose into atomic claims
        sentences = [s.strip() for s in answer.split('.') if len(s.strip()) > 10]
        return sentences[:10]  # cap at 10 claims for efficiency


class AnswerRelevanceScorer:
    # Score whether the answer actually addresses the query.
    #
    # Method: Generate questions that the answer would be a good
    # response to, then measure similarity between the generated
    # questions and the original query.
    #
    # A low answer_relevance score means the answer is off-topic --
    # the LLM is being distracted by irrelevant context or misinterpreting
    # the query.

    def __init__(
        self,
        llm_fn: Callable[[str], str],
        embed_fn: Callable[[str], list[float]],
    ) -> None:
        self.llm = llm_fn
        self.embed = embed_fn

    def score(self, query: str, answer: str) -> float:
        # Generate questions that this answer would address
        prompt = (
            f"Given this answer, generate 3 questions that it directly answers.\n"
            f"Answer: {answer[:500]}\n"
            f"Questions (one per line):"
        )
        response = self.llm(prompt)
        generated_questions = [
            q.strip().lstrip("0123456789.-) ")
            for q in response.strip().split('\n')
            if q.strip()
        ]

        if not generated_questions:
            return 0.0

        # Compare generated questions with original query
        query_emb = self.embed(query)
        similarities = []
        for gq in generated_questions[:3]:
            gq_emb = self.embed(gq)
            sim = self._cosine_sim(query_emb, gq_emb)
            similarities.append(sim)

        return sum(similarities) / len(similarities)

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0


class RAGEvaluator:
    # Complete RAG evaluation suite with regression detection.
    #
    # Runs all component-level metrics and aggregates into a report.
    # Supports A/B testing between RAG system variants and regression
    # detection against baseline scores.

    def __init__(
        self,
        llm_judge: Callable[[str], str],
        embed_fn: Callable[[str], list[float]],
    ) -> None:
        self.context_scorer = ContextRelevanceScorer(llm_judge)
        self.faithfulness_scorer = FaithfulnessScorer(llm_judge)
        self.relevance_scorer = AnswerRelevanceScorer(llm_judge, embed_fn)

    def evaluate(self, result: RAGResult) -> EvalScores:
        scores = EvalScores()

        # Context relevance
        scores.context_relevance = self.context_scorer.score(
            result.query, result.retrieved_contexts
        )

        # Context recall (if ground truth available)
        if result.ground_truth_contexts:
            scores.context_recall = self._context_recall(
                result.retrieved_contexts, result.ground_truth_contexts
            )

        # Faithfulness
        scores.faithfulness = self.faithfulness_scorer.score(
            result.answer, result.retrieved_contexts
        )

        # Answer relevance
        scores.answer_relevance = self.relevance_scorer.score(
            result.query, result.answer
        )

        # Answer correctness (if ground truth available)
        if result.ground_truth_answer:
            scores.answer_correctness = self._answer_correctness(
                result.answer, result.ground_truth_answer
            )

        return scores

    def evaluate_batch(
        self,
        results: list[RAGResult],
    ) -> dict[str, Any]:
        all_scores = [self.evaluate(r) for r in results]

        # Aggregate statistics
        metrics = {}
        for field in ["context_relevance", "context_recall", "faithfulness",
                      "answer_relevance", "answer_correctness", "overall"]:
            values = [getattr(s, field) if field != "overall" else s.overall
                     for s in all_scores]
            metrics[field] = {
                "mean": round(statistics.mean(values), 3),
                "median": round(statistics.median(values), 3),
                "std": round(statistics.stdev(values), 3) if len(values) > 1 else 0,
                "min": round(min(values), 3),
                "max": round(max(values), 3),
            }

        return {
            "num_samples": len(results),
            "metrics": metrics,
            "per_sample": [s.to_dict() for s in all_scores],
        }

    def detect_regression(
        self,
        current: dict[str, Any],
        baseline: dict[str, Any],
        threshold: float = 0.05,
    ) -> dict[str, Any]:
        # Detect significant regressions against a baseline
        regressions = []
        improvements = []

        for metric in current["metrics"]:
            curr_mean = current["metrics"][metric]["mean"]
            base_mean = baseline["metrics"][metric]["mean"]
            delta = curr_mean - base_mean

            if delta < -threshold:
                regressions.append({
                    "metric": metric,
                    "current": curr_mean,
                    "baseline": base_mean,
                    "delta": round(delta, 3),
                })
            elif delta > threshold:
                improvements.append({
                    "metric": metric,
                    "current": curr_mean,
                    "baseline": base_mean,
                    "delta": round(delta, 3),
                })

        return {
            "has_regression": len(regressions) > 0,
            "regressions": regressions,
            "improvements": improvements,
        }

    def _context_recall(
        self, retrieved: list[str], ground_truth: list[str]
    ) -> float:
        # What fraction of ground truth info appears in retrieved contexts
        if not ground_truth:
            return 1.0
        retrieved_text = " ".join(retrieved).lower()
        found = 0
        for gt in ground_truth:
            # Simple overlap check (production: use NLI)
            gt_words = set(gt.lower().split())
            retrieved_words = set(retrieved_text.split())
            overlap = len(gt_words & retrieved_words) / max(len(gt_words), 1)
            if overlap > 0.5:
                found += 1
        return found / len(ground_truth)

    def _answer_correctness(self, answer: str, ground_truth: str) -> float:
        # Simple F1 token overlap (production: use NLI or BERTScore)
        answer_tokens = set(answer.lower().split())
        gt_tokens = set(ground_truth.lower().split())
        if not gt_tokens:
            return 1.0
        precision = len(answer_tokens & gt_tokens) / max(len(answer_tokens), 1)
        recall = len(answer_tokens & gt_tokens) / max(len(gt_tokens), 1)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)


def test_evaluator():
    # Mock LLM judge and embedding function
    def mock_judge(prompt: str) -> str:
        if "relevant" in prompt.lower() or "supported" in prompt.lower():
            return "yes" if "python" in prompt.lower() else "no"
        return "How does Python work?\nWhat is asyncio?\nWhat are coroutines?"

    import random
    random.seed(42)
    def mock_embed(text: str) -> list[float]:
        random.seed(hash(text) % 2**31)
        return [random.gauss(0, 1) for _ in range(32)]

    evaluator = RAGEvaluator(mock_judge, mock_embed)

    result = RAGResult(
        query="How does Python async/await work?",
        answer="Python async/await uses coroutines for concurrent programming. "
               "The event loop schedules coroutines cooperatively.",
        retrieved_contexts=[
            "Python's asyncio module provides infrastructure for writing "
            "single-threaded concurrent code using coroutines.",
            "The await keyword suspends the coroutine until the awaited "
            "task completes.",
        ],
        ground_truth_answer="Python async/await provides cooperative multitasking "
                           "through coroutines managed by an event loop.",
    )

    scores = evaluator.evaluate(result)
    print(f"Evaluation scores: {json.dumps(scores.to_dict(), indent=2)}")

    # Batch evaluation
    batch_report = evaluator.evaluate_batch([result, result])
    print(f"\nBatch report:")
    for metric, stats in batch_report["metrics"].items():
        print(f"  {metric}: mean={stats['mean']}, std={stats['std']}")


if __name__ == "__main__":
    test_evaluator()
    print("\nRAG evaluation tests passed!")
```

## Metric Interpretation Guide

| Metric | Low Score Means | Fix |
|--------|----------------|-----|
| **Context Relevance** (<0.5) | Retriever returning irrelevant docs | Improve chunking, embedding model, or add reranking |
| **Context Recall** (<0.5) | Missing ground truth docs | More documents, better indexing, hybrid retrieval |
| **Faithfulness** (<0.7) | LLM hallucinating beyond context | Stronger prompting, temperature=0, add citations |
| **Answer Relevance** (<0.6) | Answer off-topic | Better prompt engineering, query understanding |
| **Answer Correctness** (<0.5) | Factually wrong | Improve all upstream stages, add verification |

## Key Takeaways

- **Component-level evaluation** (retrieval, context, faithfulness, answer) identifies the root cause of failures — evaluating only the final answer hides where the pipeline is broken
- **Faithfulness** is the most critical metric for production RAG because hallucinated answers erode user trust — target >0.85 for production systems
- **LLM-as-judge** evaluation is practical and correlates well (0.8+) with human evaluation for most metrics — but calibrate with human labels on a sample before trusting it fully
- **Regression detection** should run on every RAG system change (new embedding model, chunk size change, prompt modification) with a fixed evaluation set
- Build a **golden evaluation dataset** of 50-200 query-answer pairs with ground truth contexts — this is the most important investment for long-term RAG quality improvement
"""
    ),
    (
        "rag/agentic-rag",
        "Explain agentic RAG architectures where the LLM agent dynamically decides when and how to retrieve information, covering self-RAG with reflection, adaptive retrieval with query routing, iterative retrieval with follow-up queries, and provide a Python implementation of a complete agentic RAG system with tool use, retrieval planning, answer verification, and fallback strategies.",
        r"""# Agentic RAG: Self-Directing Retrieval Systems

## Beyond Static Retrieval

Traditional RAG follows a fixed pattern: retrieve → stuff context → generate. **Agentic RAG** makes the LLM an active participant in the retrieval process — it decides **when** to retrieve, **what** to search for, **whether** the results are sufficient, and **when** to stop and answer.

**Why this matters**: Not every query needs retrieval (factual questions the LLM knows), some queries need multiple retrievals (complex, multi-faceted questions), and some need retrieval from different sources (code vs docs vs web). A static pipeline handles none of these cases well.

## Agentic RAG Architecture

```python
# Complete agentic RAG system with dynamic retrieval
from __future__ import annotations

import dataclasses
import enum
import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class RetrievalDecision(enum.Enum):
    # The agent's decision about retrieval
    NO_RETRIEVAL = "no_retrieval"       # answer from knowledge
    SINGLE_RETRIEVAL = "single"          # one retrieval is enough
    MULTI_RETRIEVAL = "multi"            # need multiple queries
    ITERATIVE = "iterative"              # retrieve, check, retrieve more


@dataclasses.dataclass
class RetrievalPlan:
    decision: RetrievalDecision
    queries: list[str]
    sources: list[str]  # which retrieval tools to use
    reasoning: str


@dataclasses.dataclass
class AgentState:
    # Current state of the agentic RAG agent
    original_query: str
    retrieval_plan: Optional[RetrievalPlan] = None
    retrieved_contexts: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    draft_answer: Optional[str] = None
    verification_result: Optional[dict] = None
    iteration: int = 0
    max_iterations: int = 3
    is_complete: bool = False
    final_answer: str = ""


class QueryRouter:
    # Routes queries to appropriate retrieval sources.
    #
    # Different queries need different retrieval strategies:
    # - Factual questions → knowledge base
    # - Code questions → code search
    # - Recent events → web search
    # - Complex questions → multiple sources + decomposition

    def __init__(self, llm_fn: Callable[[str], str]) -> None:
        self.llm = llm_fn

    def plan_retrieval(self, query: str) -> RetrievalPlan:
        prompt = f"""Analyze this query and decide the retrieval strategy.

Query: {query}

Respond in JSON with:
- decision: "no_retrieval", "single", "multi", or "iterative"
- queries: list of search queries to execute
- sources: list of sources to search ("knowledge_base", "code_search", "web")
- reasoning: why this strategy

JSON:"""

        response = self.llm(prompt)
        try:
            plan_data = json.loads(response)
            return RetrievalPlan(
                decision=RetrievalDecision(plan_data.get("decision", "single")),
                queries=plan_data.get("queries", [query]),
                sources=plan_data.get("sources", ["knowledge_base"]),
                reasoning=plan_data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, ValueError):
            # Fallback: single retrieval with original query
            return RetrievalPlan(
                decision=RetrievalDecision.SINGLE_RETRIEVAL,
                queries=[query],
                sources=["knowledge_base"],
                reasoning="Fallback to single retrieval",
            )


class AnswerVerifier:
    # Verify whether the generated answer is sufficient and faithful.
    #
    # Self-RAG (Asai et al., 2023) introduces reflection tokens:
    # - [Retrieve]: should I retrieve more information?
    # - [IsRel]: is the retrieved passage relevant?
    # - [IsSup]: is the answer supported by the passage?
    # - [IsUse]: is the response useful?
    #
    # We implement a simplified version using LLM self-critique.

    def __init__(self, llm_fn: Callable[[str], str]) -> None:
        self.llm = llm_fn

    def verify(
        self,
        query: str,
        answer: str,
        contexts: list[str],
    ) -> dict[str, Any]:
        context_text = "\n".join(contexts[:3])  # limit for prompt size

        prompt = f"""Evaluate this answer for the given query.

Query: {query}
Context: {context_text[:1500]}
Answer: {answer}

Evaluate on these criteria (score 1-5 each):
1. Completeness: Does the answer fully address the query?
2. Faithfulness: Is every claim supported by the context?
3. Relevance: Is the answer focused on what was asked?
4. Needs_more_info: Does the answer need additional retrieval? (1=no, 5=definitely)

Also provide:
- missing_aspects: What aspects of the query are not addressed?
- follow_up_queries: Suggested follow-up search queries if more info needed

Respond in JSON."""

        response = self.llm(prompt)
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            result = {
                "completeness": 3, "faithfulness": 3,
                "relevance": 3, "needs_more_info": 2,
                "missing_aspects": [], "follow_up_queries": [],
            }

        result["is_sufficient"] = (
            result.get("completeness", 0) >= 4
            and result.get("faithfulness", 0) >= 4
            and result.get("needs_more_info", 5) <= 2
        )

        return result


class AgenticRAG:
    # Complete agentic RAG system with dynamic retrieval.
    #
    # The agent follows a loop:
    # 1. Plan: Analyze query, decide retrieval strategy
    # 2. Retrieve: Execute planned queries against chosen sources
    # 3. Generate: Draft an answer from retrieved context
    # 4. Verify: Check if the answer is complete and faithful
    # 5. Iterate: If verification fails, plan follow-up retrieval
    #
    # This loop continues until the answer passes verification
    # or max iterations is reached.

    def __init__(
        self,
        llm_fn: Callable[[str], str],
        retrieval_tools: dict[str, Callable[[str, int], list[dict]]],
        max_iterations: int = 3,
    ) -> None:
        self.llm = llm_fn
        self.tools = retrieval_tools
        self.router = QueryRouter(llm_fn)
        self.verifier = AnswerVerifier(llm_fn)
        self.max_iterations = max_iterations

    def run(self, query: str) -> dict[str, Any]:
        state = AgentState(
            original_query=query,
            max_iterations=self.max_iterations,
        )

        # Step 1: Plan retrieval
        state.retrieval_plan = self.router.plan_retrieval(query)
        logger.info(
            f"Retrieval plan: {state.retrieval_plan.decision.value} "
            f"with {len(state.retrieval_plan.queries)} queries"
        )

        # Handle no-retrieval case
        if state.retrieval_plan.decision == RetrievalDecision.NO_RETRIEVAL:
            answer = self._generate_without_context(query)
            return {
                "answer": answer,
                "contexts": [],
                "iterations": 0,
                "retrieval_decision": "no_retrieval",
            }

        # Iterative retrieve-generate-verify loop
        while not state.is_complete and state.iteration < state.max_iterations:
            state.iteration += 1
            logger.info(f"Iteration {state.iteration}/{state.max_iterations}")

            # Step 2: Retrieve
            queries = state.retrieval_plan.queries
            if state.verification_result:
                # Use follow-up queries from verification
                follow_ups = state.verification_result.get("follow_up_queries", [])
                if follow_ups:
                    queries = follow_ups

            new_contexts = self._execute_retrieval(
                queries, state.retrieval_plan.sources
            )
            state.retrieved_contexts.extend(new_contexts)

            # Deduplicate contexts
            seen = set()
            unique_contexts = []
            for ctx in state.retrieved_contexts:
                ctx_hash = hash(ctx.get("text", ""))
                if ctx_hash not in seen:
                    seen.add(ctx_hash)
                    unique_contexts.append(ctx)
            state.retrieved_contexts = unique_contexts

            # Step 3: Generate answer
            context_texts = [c["text"] for c in state.retrieved_contexts]
            state.draft_answer = self._generate_answer(
                query, context_texts, state.draft_answer
            )

            # Step 4: Verify
            state.verification_result = self.verifier.verify(
                query, state.draft_answer, context_texts
            )

            if state.verification_result["is_sufficient"]:
                state.is_complete = True
                state.final_answer = state.draft_answer
                logger.info("Answer verified as sufficient")
            else:
                logger.info(
                    f"Answer insufficient. Missing: "
                    f"{state.verification_result.get('missing_aspects', [])}"
                )

        # If we exhausted iterations, use the best draft
        if not state.is_complete:
            state.final_answer = state.draft_answer or "I could not find enough information to answer this question."

        return {
            "answer": state.final_answer,
            "contexts": state.retrieved_contexts,
            "iterations": state.iteration,
            "retrieval_decision": state.retrieval_plan.decision.value,
            "verification": state.verification_result,
        }

    def _execute_retrieval(
        self,
        queries: list[str],
        sources: list[str],
    ) -> list[dict]:
        all_results = []
        for query in queries:
            for source in sources:
                if source in self.tools:
                    try:
                        results = self.tools[source](query, 5)
                        for r in results:
                            r["source"] = source
                            r["query"] = query
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(f"Retrieval from {source} failed: {e}")
        return all_results

    def _generate_answer(
        self,
        query: str,
        contexts: list[str],
        previous_answer: Optional[str],
    ) -> str:
        context_text = "\n\n".join(contexts[:5])

        if previous_answer:
            prompt = (
                f"Improve this answer using additional context.\n\n"
                f"Query: {query}\n"
                f"Previous answer: {previous_answer}\n"
                f"Additional context:\n{context_text[:2000]}\n\n"
                f"Improved answer:"
            )
        else:
            prompt = (
                f"Answer this query using the provided context.\n\n"
                f"Query: {query}\n"
                f"Context:\n{context_text[:2000]}\n\n"
                f"Answer:"
            )

        return self.llm(prompt)

    def _generate_without_context(self, query: str) -> str:
        return self.llm(f"Answer this question: {query}")


def test_agentic_rag():
    # Mock LLM and retrieval tools
    call_count = {"llm": 0, "retrieve": 0}

    def mock_llm(prompt: str) -> str:
        call_count["llm"] += 1
        if "Analyze this query" in prompt:
            return json.dumps({
                "decision": "iterative",
                "queries": ["Python async patterns", "asyncio event loop"],
                "sources": ["knowledge_base"],
                "reasoning": "Complex topic needs multiple retrievals",
            })
        elif "Evaluate this answer" in prompt:
            if call_count["llm"] > 5:
                return json.dumps({
                    "completeness": 5, "faithfulness": 5,
                    "relevance": 5, "needs_more_info": 1,
                    "is_sufficient": True,
                    "missing_aspects": [], "follow_up_queries": [],
                })
            return json.dumps({
                "completeness": 3, "faithfulness": 4,
                "relevance": 4, "needs_more_info": 3,
                "is_sufficient": False,
                "missing_aspects": ["error handling patterns"],
                "follow_up_queries": ["async error handling Python"],
            })
        else:
            return "Python async/await enables concurrent programming through coroutines managed by an event loop."

    def mock_kb_search(query: str, k: int) -> list[dict]:
        call_count["retrieve"] += 1
        return [
            {"text": f"Document about {query}: asyncio provides event loop infrastructure.",
             "score": 0.9, "doc_id": f"doc_{call_count['retrieve']}"},
        ]

    agent = AgenticRAG(
        llm_fn=mock_llm,
        retrieval_tools={"knowledge_base": mock_kb_search},
        max_iterations=3,
    )

    result = agent.run("How does Python async/await work with error handling?")

    print(f"Answer: {result['answer'][:100]}...")
    print(f"Iterations: {result['iterations']}")
    print(f"Contexts retrieved: {len(result['contexts'])}")
    print(f"Retrieval decision: {result['retrieval_decision']}")
    print(f"LLM calls: {call_count['llm']}")
    print(f"Retrieval calls: {call_count['retrieve']}")


if __name__ == "__main__":
    test_agentic_rag()
    print("\nAgentic RAG tests passed!")
```

## Agentic RAG vs Static RAG

| Aspect | Static RAG | Agentic RAG |
|--------|-----------|-------------|
| **Retrieval** | Always, fixed query | Conditional, dynamic queries |
| **Iterations** | 1 | 1-N (adaptive) |
| **Query understanding** | None | LLM analyzes intent |
| **Source selection** | Fixed | Dynamic routing |
| **Answer verification** | None | Self-critique + retry |
| **Latency** | Low (1 LLM call) | Higher (2-6 LLM calls) |
| **Answer quality** | Good for simple queries | Better for complex queries |

## Key Takeaways

- **Agentic RAG** makes the LLM an active participant in retrieval — it decides when to retrieve, what to search for, and whether more information is needed
- **Query routing** directs different query types to appropriate sources (knowledge base, code search, web) rather than searching everything blindly
- **Self-verification** with follow-up retrieval catches incomplete answers before they reach the user — this iterative refinement significantly improves answer quality for complex queries
- The **cost-quality trade-off** is real: agentic RAG uses 2-6x more LLM calls than static RAG, so it should be reserved for complex queries where the quality improvement justifies the cost
- **Fallback strategies** are essential: if the agent can't find sufficient information after max iterations, it should clearly communicate what it knows and what it couldn't find, rather than hallucinating
"""
    ),
]
