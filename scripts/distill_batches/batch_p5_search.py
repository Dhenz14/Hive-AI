"""
Batch P5 -- Search Engine Internals: inverted indices, BM25 scoring,
Elasticsearch patterns, semantic/hybrid search, autocomplete systems.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Inverted Index Construction ---
    (
        "search/inverted-index-construction",
        "Explain how to build an inverted index from scratch in Python including tokenization, "
        "stemming, stopword removal, positional indices for phrase queries, TF-IDF scoring, "
        "Boolean and ranked retrieval, persistence to disk, and a complete working text search "
        "engine implementation with type hints and production considerations.",
        r"""
# Building an Inverted Index: The Core of Every Search Engine

## Why Inverted Indices Power Search

Every search engine -- from Google to the search bar in your email client -- relies on an
**inverted index** as its foundational data structure. The name "inverted" comes from the
fact that instead of mapping documents to the words they contain (a forward index), we
map each word to the set of documents that contain it. This inversion is what makes search
fast: given a query term, we can immediately look up which documents match without scanning
every document in the corpus.

**Because** a naive full-text scan is O(N * L) where N is the number of documents and L
is the average document length, even a modest corpus of 100,000 documents becomes
unbearably slow. An inverted index reduces query-time lookup to O(1) per term (hash
table) followed by set intersection operations on posting lists. The **trade-off** is that
we pay an upfront cost to build and maintain the index, and we consume additional storage
for the index structure itself. However, this trade-off is overwhelmingly worthwhile for
any collection queried more than once.

**Common mistake**: Many developers build a simple `dict[str, set[int]]` mapping tokens to
document IDs and call it done. This approach ignores critical components like positional
information (needed for phrase queries), term frequency storage (needed for ranking), and
document length normalization. A production inverted index is significantly more nuanced.

## Text Processing Pipeline

Before we can index documents, we need a robust **text processing pipeline**. The quality
of your search results depends heavily on how well you normalize and transform raw text
into index tokens. Each stage introduces a **trade-off** between recall (finding all
relevant documents) and precision (avoiding irrelevant results).

### Tokenization, Stopwords, and Stemming

```python
from __future__ import annotations

import math
import re
import struct
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Iterator

# ---- Text Processing Pipeline ----

class Tokenizer:
    # Splits raw text into normalized tokens

    # Common English stopwords that add noise to search results
    STOP_WORDS: Set[str] = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "nor", "not", "so", "yet", "both", "either",
        "it", "its", "this", "that", "these", "those", "i", "we",
        "you", "he", "she", "they", "me", "him", "her", "us", "them",
    }

    # Simple suffix-stripping rules inspired by the Porter stemmer
    STEM_RULES: List[Tuple[str, str]] = [
        ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
        ("anci", "ance"), ("izer", "ize"), ("ously", "ous"),
        ("iveness", "ive"), ("fulness", "ful"), ("ousness", "ous"),
        ("ating", "ate"), ("ation", "ate"), ("ement", ""),
        ("ness", ""), ("ment", ""), ("ing", ""), ("ies", "y"),
        ("ally", "al"), ("ling", "l"), ("able", ""), ("ible", ""),
        ("sses", "ss"), ("eed", "ee"), ("ed", ""), ("ly", ""),
        ("er", ""), ("es", "e"), ("s", ""),
    ]

    def __init__(
        self,
        remove_stopwords: bool = True,
        apply_stemming: bool = True,
        min_token_length: int = 2,
    ) -> None:
        self.remove_stopwords = remove_stopwords
        self.apply_stemming = apply_stemming
        self.min_token_length = min_token_length
        # Matches sequences of alphanumeric characters
        self._pattern = re.compile(r"[a-z0-9]+")

    def stem(self, token: str) -> str:
        # Apply longest-matching suffix rule
        if len(token) <= 4:
            return token
        for suffix, replacement in self.STEM_RULES:
            if token.endswith(suffix):
                candidate = token[: -len(suffix)] + replacement
                if len(candidate) >= 2:
                    return candidate
        return token

    def tokenize(self, text: str) -> List[str]:
        # Full pipeline: lowercase -> split -> filter -> stem
        lowered = text.lower()
        raw_tokens = self._pattern.findall(lowered)
        result: List[str] = []
        for tok in raw_tokens:
            if len(tok) < self.min_token_length:
                continue
            if self.remove_stopwords and tok in self.STOP_WORDS:
                continue
            if self.apply_stemming:
                tok = self.stem(tok)
            result.append(tok)
        return result

    def tokenize_with_positions(self, text: str) -> List[Tuple[str, int]]:
        # Returns (token, position) pairs for positional indexing
        lowered = text.lower()
        raw_tokens = self._pattern.findall(lowered)
        result: List[Tuple[str, int]] = []
        pos = 0
        for tok in raw_tokens:
            if len(tok) < self.min_token_length:
                pos += 1
                continue
            if self.remove_stopwords and tok in self.STOP_WORDS:
                pos += 1
                continue
            processed = self.stem(tok) if self.apply_stemming else tok
            result.append((processed, pos))
            pos += 1
        return result
```

The stemming rules above are a simplified version of the **Porter Stemmer**. In production,
you would use NLTK's `PorterStemmer` or the more aggressive `SnowballStemmer`. The
**pitfall** of aggressive stemming is over-conflation: "university" and "universe" might
collapse to the same stem, producing false matches. Therefore, many modern systems use
**lemmatization** (reducing to dictionary forms) instead of stemming, accepting the higher
computational cost for better precision.

## The Inverted Index Data Structure

### Positional Posting Lists and TF-IDF

A posting list stores, for each term, the list of documents containing that term along
with positional and frequency data. **Best practice** is to store positions alongside
document IDs so you can support phrase queries and proximity searches.

```python
@dataclass
class Posting:
    # A single posting entry for one document
    doc_id: int
    term_frequency: int
    positions: List[int] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    # Metadata about an indexed document
    doc_id: int
    original_text: str
    token_count: int
    title: str = ""


class InvertedIndex:
    # Complete inverted index with TF-IDF scoring and positional queries

    def __init__(self, tokenizer: Optional[Tokenizer] = None) -> None:
        self.tokenizer = tokenizer or Tokenizer()
        # term -> list of Posting objects, sorted by doc_id
        self._index: Dict[str, List[Posting]] = defaultdict(list)
        # doc_id -> document metadata
        self._documents: Dict[int, DocumentMetadata] = {}
        # Total number of indexed documents
        self._doc_count: int = 0
        # Average document length for BM25-style normalization
        self._avg_doc_length: float = 0.0
        self._total_tokens: int = 0

    def add_document(
        self,
        doc_id: int,
        text: str,
        title: str = "",
    ) -> None:
        # Index a single document with positional information
        if doc_id in self._documents:
            raise ValueError(f"Document {doc_id} already indexed")

        token_positions = self.tokenizer.tokenize_with_positions(text)
        token_count = len(token_positions)

        self._documents[doc_id] = DocumentMetadata(
            doc_id=doc_id,
            original_text=text,
            token_count=token_count,
            title=title,
        )

        # Group positions by term
        term_positions: Dict[str, List[int]] = defaultdict(list)
        for token, pos in token_positions:
            term_positions[token].append(pos)

        # Create postings
        for term, positions in term_positions.items():
            posting = Posting(
                doc_id=doc_id,
                term_frequency=len(positions),
                positions=sorted(positions),
            )
            self._index[term].append(posting)

        self._doc_count += 1
        self._total_tokens += token_count
        self._avg_doc_length = self._total_tokens / self._doc_count

    def _idf(self, term: str) -> float:
        # Inverse document frequency with smoothing
        # IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        df = len(self._index.get(term, []))
        if df == 0:
            return 0.0
        return math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1.0)

    def _tf(self, term_freq: int) -> float:
        # Logarithmic term frequency to dampen high counts
        if term_freq == 0:
            return 0.0
        return 1.0 + math.log(term_freq)

    def search_tfidf(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        # Ranked retrieval using TF-IDF scoring
        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[int, float] = defaultdict(float)
        for token in query_tokens:
            idf = self._idf(token)
            for posting in self._index.get(token, []):
                tf = self._tf(posting.term_frequency)
                scores[posting.doc_id] += tf * idf

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def boolean_and(self, terms: List[str]) -> Set[int]:
        # Boolean AND: intersection of posting lists
        processed = [self.tokenizer.stem(t.lower()) for t in terms]
        if not processed:
            return set()
        # Start with the shortest posting list (optimization)
        posting_lists = []
        for term in processed:
            postings = self._index.get(term, [])
            posting_lists.append({p.doc_id for p in postings})
        posting_lists.sort(key=len)
        result = posting_lists[0]
        for pl in posting_lists[1:]:
            result &= pl
            if not result:
                break
        return result

    def phrase_search(self, phrase: str) -> List[int]:
        # Find documents containing exact phrase using positional index
        tokens = self.tokenizer.tokenize(phrase)
        if len(tokens) < 2:
            return [p.doc_id for p in self._index.get(tokens[0], [])] if tokens else []

        # Get posting lists for all terms
        all_postings: List[Dict[int, List[int]]] = []
        for token in tokens:
            doc_positions: Dict[int, List[int]] = {}
            for posting in self._index.get(token, []):
                doc_positions[posting.doc_id] = posting.positions
            all_postings.append(doc_positions)

        # Find documents that contain ALL terms
        candidate_docs = set(all_postings[0].keys())
        for dp in all_postings[1:]:
            candidate_docs &= set(dp.keys())

        # Check positional adjacency
        matching_docs: List[int] = []
        for doc_id in candidate_docs:
            first_positions = all_postings[0][doc_id]
            for start_pos in first_positions:
                match = True
                for offset, dp in enumerate(all_postings[1:], start=1):
                    if (start_pos + offset) not in dp[doc_id]:
                        match = False
                        break
                if match:
                    matching_docs.append(doc_id)
                    break
        return matching_docs
```

The **key insight** in positional indexing is that we store not just *which* documents
contain a term, but *where* in each document the term appears. This enables phrase queries
like "machine learning" by verifying that "machine" appears at position N and "learning"
at position N+1 in the same document. Without positional data, you can only do bag-of-words
Boolean queries.

## Persistence and Disk-Based Index

A production index must survive process restarts. The **best practice** is to serialize
the index to disk in a format that supports memory-mapped access for fast loading.

```python
class PersistentIndex(InvertedIndex):
    # Extends InvertedIndex with JSON-based disk persistence.
    # Production systems use binary formats (e.g., Lucene's segment files),
    # but JSON is readable and sufficient for moderate-scale indices.

    def __init__(
        self,
        index_dir: str,
        tokenizer: Optional[Tokenizer] = None,
    ) -> None:
        super().__init__(tokenizer)
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.index_dir / "index.json"
        self._docs_path = self.index_dir / "documents.json"
        self._meta_path = self.index_dir / "metadata.json"

    def save(self) -> None:
        # Serialize entire index to disk
        index_data: Dict[str, list] = {}
        for term, postings in self._index.items():
            index_data[term] = [
                {
                    "doc_id": p.doc_id,
                    "tf": p.term_frequency,
                    "positions": p.positions,
                }
                for p in postings
            ]
        self._index_path.write_text(json.dumps(index_data), encoding="utf-8")

        docs_data = {
            str(doc_id): {
                "text": meta.original_text,
                "token_count": meta.token_count,
                "title": meta.title,
            }
            for doc_id, meta in self._documents.items()
        }
        self._docs_path.write_text(json.dumps(docs_data), encoding="utf-8")

        metadata = {
            "doc_count": self._doc_count,
            "avg_doc_length": self._avg_doc_length,
            "total_tokens": self._total_tokens,
        }
        self._meta_path.write_text(json.dumps(metadata), encoding="utf-8")

    def load(self) -> None:
        # Deserialize index from disk
        if not self._index_path.exists():
            return

        index_data = json.loads(self._index_path.read_text(encoding="utf-8"))
        for term, postings_raw in index_data.items():
            self._index[term] = [
                Posting(
                    doc_id=p["doc_id"],
                    term_frequency=p["tf"],
                    positions=p["positions"],
                )
                for p in postings_raw
            ]

        docs_data = json.loads(self._docs_path.read_text(encoding="utf-8"))
        for doc_id_str, doc_info in docs_data.items():
            doc_id = int(doc_id_str)
            self._documents[doc_id] = DocumentMetadata(
                doc_id=doc_id,
                original_text=doc_info["text"],
                token_count=doc_info["token_count"],
                title=doc_info.get("title", ""),
            )

        meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        self._doc_count = meta["doc_count"]
        self._avg_doc_length = meta["avg_doc_length"]
        self._total_tokens = meta["total_tokens"]


# ---- Usage Example ----

def demo_search() -> None:
    idx = PersistentIndex(index_dir="/tmp/search_index")

    documents = [
        (1, "Introduction to Machine Learning", "Machine learning is a subset of AI"),
        (2, "Deep Learning Fundamentals", "Neural networks form the basis of deep learning"),
        (3, "Natural Language Processing", "NLP applies machine learning to text data"),
        (4, "Computer Vision with CNNs", "Convolutional neural networks excel at image tasks"),
    ]
    for doc_id, title, text in documents:
        idx.add_document(doc_id, f"{title}. {text}", title=title)

    results = idx.search_tfidf("machine learning neural", top_k=3)
    for doc_id, score in results:
        meta = idx._documents[doc_id]
        print(f"  [{score:.3f}] {meta.title}")

    idx.save()
```

## Performance Considerations and Production Trade-offs

**However**, the JSON-based persistence above is only suitable for small indices. Production
search engines like Lucene (which powers Elasticsearch) use sophisticated binary formats
with **skip lists** for fast posting list intersection, **variable-byte encoding** for
compact storage of doc IDs, and **memory-mapped files** for zero-copy access. Building a
Lucene-grade index is a multi-year engineering effort, which is why most teams use
Elasticsearch or Solr rather than building from scratch.

For moderate-scale use cases (under 1 million documents), the Python implementation above
is perfectly adequate. The **best practice** is to start with a simple implementation,
measure performance on your actual data, and only introduce complexity when benchmarks
demand it.

## Summary and Key Takeaways

- **An inverted index maps terms to posting lists** containing document IDs, term
  frequencies, and positions -- this is the fundamental data structure enabling fast search
- **The text processing pipeline** (tokenization, stopword removal, stemming) determines
  search quality; aggressive stemming increases recall but can hurt precision
- **Positional indices enable phrase queries** by storing exact token positions within each
  document, at the cost of roughly 2-3x more storage than non-positional indices
- **TF-IDF scoring** combines term frequency (how often a term appears in a document) with
  inverse document frequency (how rare the term is across the corpus) to rank results
- **Boolean retrieval** (AND/OR operations on posting lists) is the foundation; ranked
  retrieval layers scoring on top for relevance ordering
- **Best practice**: start with the shortest posting list when intersecting for Boolean
  AND queries -- this "short-circuit" optimization can reduce work by orders of magnitude
- **Pitfall**: forgetting to normalize document lengths in scoring -- without length
  normalization, longer documents unfairly dominate results simply because they contain
  more term occurrences
""",
    ),

    # --- 2. BM25 and Modern Relevance Scoring ---
    (
        "search/bm25-relevance-scoring",
        "Explain BM25 and modern relevance scoring algorithms including BM25F for multi-field "
        "search, the mathematical intuition behind k1 and b parameters, learning-to-rank with "
        "feature engineering, LambdaMART, RankNet, evaluation metrics like NDCG and MAP, and "
        "provide a complete Python implementation with field boosting and type hints.",
        r"""
# BM25 and Modern Relevance Scoring: From Theory to Production

## Why BM25 Replaced TF-IDF

BM25 (Best Matching 25) is the **de facto standard** scoring function in information
retrieval, used by Elasticsearch, Solr, and Lucene as their default ranking algorithm.
It was developed as part of the Okapi BM25 family at City University London in the 1990s,
and despite being decades old, it remains remarkably competitive with modern neural
approaches for keyword-based search.

**Because** raw TF-IDF has a fundamental flaw: term frequency grows without bound. If a
document mentions "python" 100 times, it scores 100x higher than a document mentioning it
once -- even though the 100-mention document is probably keyword-stuffed spam, not the most
relevant result. BM25 introduces **saturation** on term frequency: after a certain point,
additional occurrences contribute diminishing returns. This single change dramatically
improves ranking quality.

The BM25 formula is:

**score(D, Q) = SUM over q in Q of: IDF(q) * (tf(q, D) * (k1 + 1)) / (tf(q, D) + k1 * (1 - b + b * |D| / avgdl))**

Where `k1` controls term frequency saturation (typically 1.2), `b` controls document
length normalization (typically 0.75), `|D|` is the document length, and `avgdl` is the
average document length. The **trade-off** between `k1` and `b` determines how your
ranking behaves: higher `k1` means term frequency matters more, higher `b` means length
normalization is more aggressive.

**Common mistake**: Blindly using default parameters (k1=1.2, b=0.75) without tuning for
your specific corpus. For short documents like product titles, you want lower `b` (less
length normalization). For long documents like research papers, the defaults work well.

## Complete BM25 and BM25F Implementation

```python
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Protocol


@dataclass
class FieldConfig:
    # Configuration for a single searchable field
    name: str
    boost: float = 1.0    # Field-level weight multiplier
    k1: float = 1.2       # Term frequency saturation
    b: float = 0.75        # Length normalization factor


@dataclass
class FieldData:
    # Stored data for one field of one document
    tokens: List[str]
    term_freqs: Dict[str, int] = field(default_factory=dict)
    length: int = 0

    def __post_init__(self) -> None:
        self.length = len(self.tokens)
        freq_map: Dict[str, int] = defaultdict(int)
        for tok in self.tokens:
            freq_map[tok] += 1
        self.term_freqs = dict(freq_map)


@dataclass
class IndexedDocument:
    # A multi-field document in the index
    doc_id: str
    fields: Dict[str, FieldData]
    raw_data: Dict[str, str] = field(default_factory=dict)


class BM25FIndex:
    # BM25F index supporting multi-field search with per-field boosting.
    #
    # BM25F extends BM25 by computing a weighted term frequency across
    # multiple fields before applying the BM25 saturation function.
    # This is superior to running separate BM25 queries per field and
    # summing scores, because it models the interaction between fields
    # within the saturation curve.

    def __init__(
        self,
        field_configs: List[FieldConfig],
        tokenize_fn: Optional[object] = None,
    ) -> None:
        self._field_configs: Dict[str, FieldConfig] = {
            fc.name: fc for fc in field_configs
        }
        self._documents: Dict[str, IndexedDocument] = {}
        # term -> set of doc_ids containing this term (across all fields)
        self._doc_freq: Dict[str, int] = defaultdict(int)
        # Per-field average document lengths
        self._field_avg_lengths: Dict[str, float] = {
            fc.name: 0.0 for fc in field_configs
        }
        self._field_total_lengths: Dict[str, int] = {
            fc.name: 0 for fc in field_configs
        }
        self._doc_count: int = 0

    def add_document(
        self,
        doc_id: str,
        fields: Dict[str, List[str]],
        raw_data: Optional[Dict[str, str]] = None,
    ) -> None:
        # Add a pre-tokenized multi-field document
        field_data: Dict[str, FieldData] = {}
        terms_seen: set = set()

        for field_name, tokens in fields.items():
            if field_name not in self._field_configs:
                continue
            fd = FieldData(tokens=tokens)
            field_data[field_name] = fd
            self._field_total_lengths[field_name] += fd.length
            terms_seen.update(fd.term_freqs.keys())

        self._documents[doc_id] = IndexedDocument(
            doc_id=doc_id,
            fields=field_data,
            raw_data=raw_data or {},
        )

        # Update document frequencies
        for term in terms_seen:
            self._doc_freq[term] += 1

        self._doc_count += 1

        # Recompute average field lengths
        for fname in self._field_configs:
            total = self._field_total_lengths[fname]
            self._field_avg_lengths[fname] = (
                total / self._doc_count if self._doc_count > 0 else 0.0
            )

    def _idf(self, term: str) -> float:
        # IDF component with Robertson-Sparck Jones formula
        df = self._doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(
            (self._doc_count - df + 0.5) / (df + 0.5) + 1.0
        )

    def _bm25f_term_score(
        self,
        term: str,
        doc: IndexedDocument,
    ) -> float:
        # Compute BM25F score for a single term in a document.
        # BM25F combines weighted TF across fields, then applies saturation.
        weighted_tf = 0.0
        for fname, config in self._field_configs.items():
            fd = doc.fields.get(fname)
            if fd is None:
                continue
            raw_tf = fd.term_freqs.get(term, 0)
            if raw_tf == 0:
                continue
            avg_len = self._field_avg_lengths[fname]
            if avg_len == 0:
                avg_len = 1.0
            # Per-field length normalization
            norm_tf = raw_tf / (
                1.0 - config.b + config.b * (fd.length / avg_len)
            )
            weighted_tf += config.boost * norm_tf

        # Apply BM25 saturation using average k1 across fields
        avg_k1 = sum(c.k1 for c in self._field_configs.values()) / len(
            self._field_configs
        )
        saturated = (weighted_tf * (avg_k1 + 1.0)) / (weighted_tf + avg_k1)
        return self._idf(term) * saturated

    def search(
        self,
        query_tokens: List[str],
        top_k: int = 10,
    ) -> List[Tuple[str, float, Dict[str, str]]]:
        # Search and rank documents using BM25F scoring
        scores: Dict[str, float] = defaultdict(float)
        for token in query_tokens:
            if token not in self._doc_freq:
                continue
            for doc_id, doc in self._documents.items():
                score = self._bm25f_term_score(token, doc)
                if score > 0:
                    scores[doc_id] += score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results: List[Tuple[str, float, Dict[str, str]]] = []
        for doc_id, score in ranked[:top_k]:
            raw = self._documents[doc_id].raw_data
            results.append((doc_id, score, raw))
        return results
```

The implementation above correctly models BM25F's **key innovation**: combining weighted
term frequencies across fields *before* saturation, rather than computing per-field BM25
scores and summing them. This matters **because** if "python" appears once in the title
(boosted 3x) and twice in the body (boosted 1x), the combined weighted TF is 5.0, which
produces a different saturation curve than scoring fields independently.

## Learning to Rank: Going Beyond BM25

**However**, BM25 uses a fixed formula with a handful of parameters. Modern search systems
use **learning-to-rank (LTR)** to combine dozens or hundreds of features -- BM25 score,
click-through rate, document freshness, PageRank, field match quality, query-document
embedding similarity -- into a learned ranking function.

### Feature Engineering and RankNet

```python
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Callable, Dict, Any

@dataclass
class RankingFeatures:
    # Feature vector for a query-document pair
    bm25_score: float
    bm25_title: float
    bm25_body: float
    exact_title_match: float   # 1.0 if query matches title exactly
    title_coverage: float      # fraction of query terms in title
    doc_freshness: float       # days since publication, normalized
    doc_length_norm: float     # normalized document length
    click_through_rate: float  # historical CTR for this doc
    query_doc_embedding_sim: float  # cosine similarity of embeddings

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.bm25_score,
            self.bm25_title,
            self.bm25_body,
            self.exact_title_match,
            self.title_coverage,
            self.doc_freshness,
            self.doc_length_norm,
            self.click_through_rate,
            self.query_doc_embedding_sim,
        ], dtype=np.float64)


class SimpleRankNet:
    # Simplified RankNet: learns pairwise preferences between documents.
    #
    # RankNet uses a neural network to predict the probability that
    # document A should rank higher than document B. The loss function
    # is a cross-entropy loss on pairwise comparisons.

    def __init__(self, n_features: int, hidden_size: int = 32, lr: float = 0.001) -> None:
        self.lr = lr
        # Simple 2-layer network (weights initialized randomly)
        rng = np.random.default_rng(42)
        self.W1 = rng.standard_normal((n_features, hidden_size)) * 0.1
        self.b1 = np.zeros(hidden_size)
        self.W2 = rng.standard_normal((hidden_size, 1)) * 0.1
        self.b2 = np.zeros(1)

    def _forward(self, x: np.ndarray) -> float:
        # Forward pass: returns relevance score
        h = np.maximum(0, x @ self.W1 + self.b1)  # ReLU activation
        return float((h @ self.W2 + self.b2)[0])

    def predict_scores(
        self, feature_vectors: List[np.ndarray]
    ) -> List[float]:
        # Score a list of documents for ranking
        return [self._forward(fv) for fv in feature_vectors]

    def train_step(
        self,
        x_i: np.ndarray,
        x_j: np.ndarray,
        label: float,
    ) -> float:
        # One pairwise training step.
        # label = 1.0 if x_i should rank higher, 0.0 otherwise
        s_i = self._forward(x_i)
        s_j = self._forward(x_j)
        # RankNet probability: P(i > j) = sigmoid(s_i - s_j)
        diff = s_i - s_j
        prob = 1.0 / (1.0 + np.exp(-diff))
        # Cross-entropy loss
        loss = -label * np.log(prob + 1e-10) - (1 - label) * np.log(1 - prob + 1e-10)
        return float(loss)


# ---- Evaluation Metrics ----

def ndcg_at_k(relevance_scores: List[int], k: int) -> float:
    # Normalized Discounted Cumulative Gain at position k
    # relevance_scores[i] is the relevance label of the i-th ranked doc
    def dcg(scores: List[int], k: int) -> float:
        return sum(
            (2**rel - 1) / math.log2(pos + 2)
            for pos, rel in enumerate(scores[:k])
        )
    actual = dcg(relevance_scores, k)
    ideal = dcg(sorted(relevance_scores, reverse=True), k)
    return actual / ideal if ideal > 0 else 0.0


def mean_average_precision(
    ranked_results: List[List[bool]],
) -> float:
    # MAP across multiple queries.
    # Each inner list is [is_relevant] for ranked results of one query.
    aps: List[float] = []
    for results in ranked_results:
        hits = 0
        precision_sum = 0.0
        for i, is_rel in enumerate(results):
            if is_rel:
                hits += 1
                precision_sum += hits / (i + 1)
        ap = precision_sum / hits if hits > 0 else 0.0
        aps.append(ap)
    return sum(aps) / len(aps) if aps else 0.0
```

### The LTR Training Pipeline

The **best practice** for learning-to-rank is a three-stage pipeline:

1. **Feature extraction**: For each (query, document) pair, compute features like BM25
   scores across fields, click signals, document quality signals, and embedding similarities
2. **Training data generation**: Use human relevance judgments (graded 0-4) or click logs
   with position-bias correction to create pairwise or listwise training examples
3. **Model training**: Train a model (LambdaMART is the industry standard for tabular
   features, or a neural model for feature learning) on pairwise preferences

**Pitfall**: Training on raw click data without correcting for **position bias** produces
a model that reinforces existing ranking rather than learning true relevance. Documents
shown at position 1 get clicked more regardless of relevance. Therefore, use inverse
propensity weighting or counterfactual learning to debias click signals.

## Parameter Tuning: Understanding k1 and b

The intuition behind BM25's parameters:

- **k1 = 0**: Term frequency is completely ignored; only document frequency matters
  (pure Boolean-like behavior). **k1 = infinity**: No saturation; behaves like raw TF-IDF
- **b = 0**: No document length normalization; long documents are not penalized.
  **b = 1**: Full normalization; a 1000-word document must have 10x the term frequency
  of a 100-word document to score equally

**Best practice**: Use grid search or Bayesian optimization over (k1, b) to maximize NDCG
on your held-out relevance judgments. Typical ranges are k1 in [0.5, 2.0] and b in
[0.3, 0.9]. Different fields may benefit from different parameters, which is exactly
what BM25F enables.

## Summary and Key Takeaways

- **BM25 improves on TF-IDF** by introducing term frequency saturation (controlled by k1)
  and explicit document length normalization (controlled by b)
- **BM25F extends BM25 to multi-field documents** by computing weighted term frequencies
  across fields before applying saturation -- this correctly models the interaction between
  field importance and term frequency
- **Learning-to-rank** combines dozens of features (BM25, clicks, freshness, embeddings)
  into a learned ranking function that significantly outperforms any single signal
- **NDCG and MAP** are the standard evaluation metrics; always evaluate on graded relevance
  judgments rather than binary relevant/not-relevant labels
- **Common mistake**: Using default BM25 parameters without corpus-specific tuning; short
  documents like titles need very different (k1, b) values than long documents like articles
- **Pitfall**: Training LTR models on raw click logs without position-bias correction will
  create a feedback loop where the model simply learns to replicate existing ranking
- **Best practice**: Separate your features into query-dependent (BM25, embedding sim) and
  query-independent (PageRank, freshness) categories -- this decomposition helps with
  feature engineering and caching
""",
    ),

    # --- 3. Elasticsearch Deep Dive ---
    (
        "search/elasticsearch-deep-dive",
        "Explain Elasticsearch internals and best practices including mapping design with "
        "dynamic vs explicit mappings, custom analyzers for multi-language search, query DSL "
        "optimization with bool queries and function_score, aggregations pipeline for analytics, "
        "and Python client patterns with bulk indexing, scroll API, and connection pooling. "
        "Provide complete production-ready code examples with type hints.",
        r"""
# Elasticsearch Deep Dive: From Mapping Design to Production Python Patterns

## Why Elasticsearch Architecture Matters

Elasticsearch is built on Apache Lucene and adds distributed coordination, a REST API,
and a powerful query DSL on top. Understanding its internals -- how documents are analyzed,
how shards distribute data, and how queries are executed across a cluster -- is essential
for building search systems that are fast, relevant, and scalable. **Because** Elasticsearch
makes many things easy, developers often skip understanding the internals, leading to poor
mappings, inefficient queries, and index designs that crumble at scale.

**Common mistake**: Using Elasticsearch as a general-purpose database. It excels at search
and analytics but lacks true transactions, has eventual consistency by default, and can
lose acknowledged writes during network partitions. Therefore, always maintain a source-of-
truth database (PostgreSQL, etc.) and treat Elasticsearch as a derived search view.

## Mapping Design: The Foundation of Good Search

Mappings define how documents are indexed -- which fields exist, their types, and which
analyzer processes their text. Getting mappings right is the most impactful optimization
you can make, **because** a bad mapping means no amount of query tuning will produce good
results.

### Explicit Mappings vs Dynamic Mappings

```python
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Generator
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

# ---- Mapping Definition Helpers ----

def build_product_mapping() -> Dict[str, Any]:
    # Explicit mapping for an e-commerce product index.
    #
    # Key design decisions:
    #   - title uses a custom analyzer with edge_ngram for autocomplete
    #   - description uses standard + language-specific analyzers
    #   - category is keyword (exact match) with a text sub-field for search
    #   - price is scaled_float for efficient range queries
    #   - All date fields use strict_date_optional_time format
    return {
        "settings": {
            "number_of_shards": 3,
            "number_of_replicas": 1,
            "analysis": {
                "analyzer": {
                    "autocomplete_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "autocomplete_filter",
                        ],
                    },
                    "autocomplete_search": {
                        # Search-time analyzer: no edge_ngram
                        # to avoid matching partial query terms
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase"],
                    },
                    "multilingual": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "asciifolding",
                            "word_delimiter_graph",
                        ],
                    },
                },
                "filter": {
                    "autocomplete_filter": {
                        "type": "edge_ngram",
                        "min_gram": 2,
                        "max_gram": 15,
                    },
                },
            },
            # Dynamic mapping disabled to prevent field explosion
            "index.mapping.total_fields.limit": 200,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "title": {
                    "type": "text",
                    "analyzer": "autocomplete_analyzer",
                    "search_analyzer": "autocomplete_search",
                    "fields": {
                        "exact": {"type": "keyword"},
                        "multilingual": {
                            "type": "text",
                            "analyzer": "multilingual",
                        },
                    },
                },
                "description": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "english": {
                            "type": "text",
                            "analyzer": "english",
                        },
                    },
                },
                "category": {
                    "type": "keyword",
                    "fields": {
                        "search": {
                            "type": "text",
                            "analyzer": "standard",
                        },
                    },
                },
                "price": {
                    "type": "scaled_float",
                    "scaling_factor": 100,
                },
                "in_stock": {"type": "boolean"},
                "rating": {"type": "float"},
                "created_at": {
                    "type": "date",
                    "format": "strict_date_optional_time||epoch_millis",
                },
                "tags": {"type": "keyword"},
                "brand": {
                    "type": "keyword",
                    "fields": {
                        "search": {"type": "text", "analyzer": "standard"},
                    },
                },
            },
        },
    }
```

**Best practice**: Always use `"dynamic": "strict"` in production. Dynamic mapping is
convenient during prototyping, but in production it leads to **mapping explosion** when
unexpected fields appear in documents. With strict mode, any unmapped field causes an
indexing error, forcing you to be intentional about your schema.

The multi-field pattern (`"fields": {"exact": {"type": "keyword"}}`) is critical
**because** different query types need different field types. A `text` field is analyzed
and tokenized for full-text search, while a `keyword` field is stored as-is for exact
matching, sorting, and aggregations. You almost always want both.

## Query DSL Optimization

### Bool Queries and Function Score

```python
@dataclass
class SearchRequest:
    # Structured search request for the product index
    query: str
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    in_stock_only: bool = False
    min_rating: Optional[float] = None
    brands: Optional[List[str]] = None
    page: int = 1
    page_size: int = 20
    sort_by: str = "relevance"


def build_search_query(req: SearchRequest) -> Dict[str, Any]:
    # Build an optimized Elasticsearch query from search parameters.
    #
    # Structure:
    #   - function_score wraps the entire query for relevance boosting
    #   - bool.must: full-text matching (affects score)
    #   - bool.filter: exact match filters (no scoring overhead)
    #   - bool.should: optional boosting signals

    must_clauses: List[Dict[str, Any]] = []
    filter_clauses: List[Dict[str, Any]] = []
    should_clauses: List[Dict[str, Any]] = []

    # Full-text search across multiple fields with boosting
    if req.query:
        must_clauses.append({
            "multi_match": {
                "query": req.query,
                "fields": [
                    "title^3",           # Title matches boosted 3x
                    "title.multilingual^2",
                    "description",
                    "description.english",
                    "category.search^2",
                    "brand.search",
                    "tags^1.5",
                ],
                "type": "best_fields",
                "tie_breaker": 0.3,
                "fuzziness": "AUTO",
                "prefix_length": 2,
                "minimum_should_match": "75%",
            }
        })

    # Filters: exact matches go in filter context (cacheable, no scoring)
    if req.category:
        filter_clauses.append({"term": {"category": req.category}})
    if req.in_stock_only:
        filter_clauses.append({"term": {"in_stock": True}})
    if req.brands:
        filter_clauses.append({"terms": {"brand": req.brands}})
    if req.min_price is not None or req.max_price is not None:
        range_q: Dict[str, Any] = {}
        if req.min_price is not None:
            range_q["gte"] = req.min_price
        if req.max_price is not None:
            range_q["lte"] = req.max_price
        filter_clauses.append({"range": {"price": range_q}})
    if req.min_rating is not None:
        filter_clauses.append({"range": {"rating": {"gte": req.min_rating}}})

    # Optional boosting: prefer highly-rated products
    should_clauses.append({
        "range": {
            "rating": {"gte": 4.0, "boost": 1.5},
        }
    })

    bool_query: Dict[str, Any] = {}
    if must_clauses:
        bool_query["must"] = must_clauses
    if filter_clauses:
        bool_query["filter"] = filter_clauses
    if should_clauses:
        bool_query["should"] = should_clauses
        bool_query["minimum_should_match"] = 0

    # Wrap in function_score for freshness boosting
    query = {
        "function_score": {
            "query": {"bool": bool_query},
            "functions": [
                {
                    # Exponential decay: newer products score higher
                    "exp": {
                        "created_at": {
                            "origin": "now",
                            "scale": "30d",
                            "offset": "7d",
                            "decay": 0.5,
                        }
                    },
                    "weight": 1.2,
                },
            ],
            "score_mode": "multiply",
            "boost_mode": "multiply",
        }
    }
    return query
```

A critical **trade-off** in query design is `must` vs `filter` context. Clauses in `must`
contribute to the relevance score and cannot be cached. Clauses in `filter` are binary
(match or not), do not affect scoring, and are aggressively cached by Elasticsearch.
**Therefore**, always place exact-match conditions (category, price range, in-stock status)
in `filter` context. This can reduce query latency by 50% or more on repeated queries.

## Aggregations Pipeline

### Analytics Queries

```python
def build_faceted_aggregation(
    category: Optional[str] = None,
) -> Dict[str, Any]:
    # Build aggregations for search facets and analytics.
    #
    # This provides:
    #   - Category distribution (for faceted navigation)
    #   - Price histogram and statistics
    #   - Top brands
    #   - Rating distribution
    #   - Nested: average price per category (pipeline aggregation)

    aggs: Dict[str, Any] = {
        "categories": {
            "terms": {
                "field": "category",
                "size": 50,
                "order": {"_count": "desc"},
            },
            "aggs": {
                "avg_price": {"avg": {"field": "price"}},
                "avg_rating": {"avg": {"field": "rating"}},
            },
        },
        "price_histogram": {
            "histogram": {
                "field": "price",
                "interval": 50,
                "min_doc_count": 1,
            },
        },
        "price_stats": {
            "extended_stats": {"field": "price"},
        },
        "top_brands": {
            "terms": {
                "field": "brand",
                "size": 20,
            },
        },
        "rating_ranges": {
            "range": {
                "field": "rating",
                "ranges": [
                    {"key": "poor", "to": 2.0},
                    {"key": "average", "from": 2.0, "to": 3.5},
                    {"key": "good", "from": 3.5, "to": 4.5},
                    {"key": "excellent", "from": 4.5},
                ],
            },
        },
    }
    return {"size": 0, "aggs": aggs}
```

## Python Client Patterns

### Bulk Indexing and Scroll API

```python
# Production-grade Elasticsearch client wrapper
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import (
    ConnectionError as ESConnectionError,
    NotFoundError,
    RequestError,
)

@dataclass
class ESConfig:
    # Elasticsearch connection configuration
    hosts: List[str] = field(default_factory=lambda: ["http://localhost:9200"])
    timeout: int = 30
    max_retries: int = 3
    retry_on_timeout: bool = True
    http_auth: Optional[Tuple[str, str]] = None
    bulk_chunk_size: int = 500
    scroll_timeout: str = "5m"
    scroll_size: int = 1000


class SearchService:
    # Production Elasticsearch service with bulk ops and scroll

    def __init__(self, config: ESConfig) -> None:
        self.config = config
        self.client = Elasticsearch(
            hosts=config.hosts,
            timeout=config.timeout,
            max_retries=config.max_retries,
            retry_on_timeout=config.retry_on_timeout,
            http_auth=config.http_auth,
        )

    def create_index(
        self,
        index_name: str,
        mapping: Dict[str, Any],
        recreate: bool = False,
    ) -> None:
        # Create index with mapping; optionally delete existing
        if self.client.indices.exists(index=index_name):
            if recreate:
                self.client.indices.delete(index=index_name)
                logger.info(f"Deleted existing index: {index_name}")
            else:
                logger.info(f"Index {index_name} already exists, skipping")
                return
        self.client.indices.create(
            index=index_name,
            body=mapping,
        )
        logger.info(f"Created index: {index_name}")

    def bulk_index(
        self,
        index_name: str,
        documents: Generator[Dict[str, Any], None, None],
        id_field: str = "id",
    ) -> Tuple[int, int]:
        # Bulk index documents with progress tracking.
        # Returns (success_count, error_count).
        def gen_actions() -> Generator[Dict[str, Any], None, None]:
            for doc in documents:
                doc_id = doc.pop(id_field, None)
                action: Dict[str, Any] = {
                    "_index": index_name,
                    "_source": doc,
                }
                if doc_id is not None:
                    action["_id"] = str(doc_id)
                yield action

        success, errors = 0, 0
        for ok, result in helpers.streaming_bulk(
            self.client,
            gen_actions(),
            chunk_size=self.config.bulk_chunk_size,
            raise_on_error=False,
            raise_on_exception=False,
        ):
            if ok:
                success += 1
            else:
                errors += 1
                logger.warning(f"Bulk index error: {result}")

        # Force refresh to make documents searchable immediately
        self.client.indices.refresh(index=index_name)
        logger.info(f"Bulk indexed: {success} success, {errors} errors")
        return success, errors

    def scroll_all(
        self,
        index_name: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        # Iterate over ALL documents matching a query using scroll API.
        # This is memory-efficient for exporting or reindexing large datasets.
        body = query or {"query": {"match_all": {}}}
        body["size"] = self.config.scroll_size

        resp = self.client.search(
            index=index_name,
            body=body,
            scroll=self.config.scroll_timeout,
        )
        scroll_id = resp["_scroll_id"]
        hits = resp["hits"]["hits"]

        try:
            while hits:
                for hit in hits:
                    yield hit["_source"]
                resp = self.client.scroll(
                    scroll_id=scroll_id,
                    scroll=self.config.scroll_timeout,
                )
                scroll_id = resp["_scroll_id"]
                hits = resp["hits"]["hits"]
        finally:
            self.client.clear_scroll(scroll_id=scroll_id)

    def search(
        self,
        index_name: str,
        request: SearchRequest,
    ) -> Dict[str, Any]:
        # Execute a search request and return formatted results
        query = build_search_query(request)
        body: Dict[str, Any] = {
            "query": query,
            "from": (request.page - 1) * request.page_size,
            "size": request.page_size,
            "highlight": {
                "fields": {
                    "title": {"number_of_fragments": 0},
                    "description": {
                        "fragment_size": 150,
                        "number_of_fragments": 3,
                    },
                },
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            },
        }
        resp = self.client.search(index=index_name, body=body)
        return {
            "total": resp["hits"]["total"]["value"],
            "hits": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"],
                    "highlights": hit.get("highlight", {}),
                }
                for hit in resp["hits"]["hits"]
            ],
        }
```

## Production Considerations

**However**, the patterns above only scratch the surface of production Elasticsearch
operations. Key considerations include:

- **Index lifecycle management**: Use ILM policies to roll over time-series indices (logs,
  events) automatically. A **pitfall** is unbounded index growth that degrades query
  performance and fills disks.
- **Shard sizing**: Target 10-50GB per shard. Too many small shards waste overhead; too
  few large shards limit parallelism. **Best practice**: start with 1 shard per 10GB of
  expected data.
- **Replica configuration**: Replicas increase read throughput and fault tolerance but
  double storage. Set replicas to 0 during bulk reindexing, then increase after.

## Summary and Key Takeaways

- **Always use explicit mappings** with `dynamic: strict` in production to prevent mapping
  explosion and ensure predictable indexing behavior
- **Separate index-time and search-time analyzers** -- use edge_ngram at index time for
  autocomplete but standard tokenization at search time to avoid partial query matching
- **Use filter context for exact-match conditions** (category, price range, boolean flags)
  because filters are cacheable and do not compute relevance scores
- **Bulk indexing** with `streaming_bulk` is essential for performance -- single-document
  indexing is 10-100x slower due to per-request overhead
- **Scroll API** is the correct way to iterate over large result sets; do not use deep
  pagination with `from`/`size` beyond 10,000 results
- **Trade-off**: Multi-field mappings increase index size but enable vastly more flexible
  querying -- the storage cost is almost always worthwhile
- **Pitfall**: Forgetting to refresh after bulk indexing -- documents are not searchable
  until a refresh occurs, which by default happens every 1 second but can be delayed under
  heavy write load
""",
    ),

    # --- 4. Semantic Search with Embeddings ---
    (
        "search/semantic-search-embeddings",
        "Explain semantic search with embeddings including dense vs sparse retrieval approaches, "
        "bi-encoder vs cross-encoder architectures for reranking, hybrid search combining BM25 "
        "with vector similarity using reciprocal rank fusion, approximate nearest neighbor with "
        "HNSW and FAISS, and provide a complete Python implementation with sentence-transformers "
        "and type hints for a production-ready semantic search pipeline.",
        r"""
# Semantic Search with Embeddings: Beyond Keyword Matching

## Why Keyword Search Falls Short

Traditional keyword search relies on **lexical matching**: a document must contain the
exact terms (or their stems) that appear in the query. This creates a fundamental problem
called the **vocabulary mismatch** or **lexical gap**. A user searching for "how to fix a
broken laptop screen" will miss a highly relevant document titled "LCD display replacement
guide" because none of the query terms appear in the document. The concepts are identical,
but the words are different.

**Semantic search** solves this by representing both queries and documents as dense vectors
(embeddings) in a continuous vector space where **conceptual similarity maps to geometric
proximity**. "Broken laptop screen" and "LCD display replacement" end up as nearby vectors,
enabling matching based on meaning rather than exact words.

**However**, semantic search has its own weaknesses. It struggles with exact keyword
matching, rare proper nouns, product codes, and precise technical terms. Therefore,
the **best practice** in modern search systems is **hybrid search**: combining BM25
(lexical) and embedding similarity (semantic) to get the strengths of both approaches.

**Common mistake**: Replacing BM25 entirely with vector search. Pure vector search often
performs *worse* than BM25 for queries containing specific, unambiguous terms like "Python
3.12 changelog" or "Boeing 737 MAX specifications." The strongest systems use both signals.

## Dense vs Sparse Retrieval

### The Retrieval Spectrum

Two paradigms exist for embedding-based retrieval:

- **Dense retrieval** (bi-encoders): Map queries and documents to fixed-size dense vectors
  (e.g., 384 or 768 dimensions). Use approximate nearest neighbor (ANN) search for fast
  retrieval. Models: sentence-transformers, E5, BGE, GTE.

- **Sparse retrieval** (learned sparse): Produce sparse vectors aligned with vocabulary
  tokens, like a learned version of BM25. Models: SPLADE, DeepImpact, uniCOIL. These
  maintain the interpretability and exact-match strengths of lexical methods while learning
  term importance weights.

The **trade-off**: dense retrieval excels at capturing semantic similarity across different
phrasings, while sparse retrieval preserves the precision of exact keyword matching. Hybrid
approaches combine both, which is why they consistently outperform either alone on standard
benchmarks like BEIR and MTEB.

## Bi-Encoder vs Cross-Encoder Architecture

### The Retrieval and Reranking Pipeline

```python
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Protocol
import json
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class Document:
    # A document with text content and optional metadata
    doc_id: str
    text: str
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None


@dataclass
class SearchResult:
    # A single search result with scoring details
    doc_id: str
    text: str
    title: str
    score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmbeddingModel(Protocol):
    # Protocol for embedding models
    def encode(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress_bar: bool = False,
    ) -> np.ndarray: ...


class CrossEncoderModel(Protocol):
    # Protocol for cross-encoder reranking models
    def predict(
        self,
        sentence_pairs: List[Tuple[str, str]],
        batch_size: int = 32,
    ) -> np.ndarray: ...


class SemanticSearchEngine:
    # Production semantic search with bi-encoder retrieval,
    # BM25 hybrid fusion, and cross-encoder reranking.
    #
    # Architecture:
    #   1. Bi-encoder: fast approximate retrieval (milliseconds)
    #   2. BM25: parallel lexical retrieval
    #   3. Reciprocal rank fusion: combine both candidate sets
    #   4. Cross-encoder: precise reranking of top candidates

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        cross_encoder: Optional[CrossEncoderModel] = None,
        embedding_dim: int = 384,
    ) -> None:
        self.embedding_model = embedding_model
        self.cross_encoder = cross_encoder
        self.embedding_dim = embedding_dim
        self._documents: Dict[str, Document] = {}
        # Embedding matrix for brute-force search (replace with FAISS in production)
        self._embeddings: Optional[np.ndarray] = None
        self._doc_ids: List[str] = []

    def index_documents(
        self,
        documents: List[Document],
        batch_size: int = 64,
    ) -> None:
        # Encode and index documents for semantic search
        texts = [
            f"{doc.title}. {doc.text}" if doc.title else doc.text
            for doc in documents
        ]

        logger.info(f"Encoding {len(texts)} documents...")
        embeddings = self.embedding_model.encode(
            texts, batch_size=batch_size, show_progress_bar=True
        )

        # Normalize for cosine similarity via dot product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings = embeddings / norms

        for i, doc in enumerate(documents):
            doc.embedding = embeddings[i]
            self._documents[doc.doc_id] = doc

        self._embeddings = embeddings
        self._doc_ids = [doc.doc_id for doc in documents]
        logger.info(f"Indexed {len(documents)} documents, embedding shape: {embeddings.shape}")

    def _vector_search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 100,
    ) -> List[Tuple[str, float]]:
        # Brute-force cosine similarity search.
        # In production, replace this with FAISS or Annoy HNSW index.
        if self._embeddings is None:
            return []
        scores = self._embeddings @ query_embedding
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            (self._doc_ids[idx], float(scores[idx]))
            for idx in top_indices
        ]

    def _reciprocal_rank_fusion(
        self,
        ranked_lists: List[List[Tuple[str, float]]],
        k: int = 60,
    ) -> List[Tuple[str, float]]:
        # Reciprocal Rank Fusion (RRF) to combine multiple ranked lists.
        #
        # RRF score = SUM over lists of: 1 / (k + rank_i)
        #
        # This is the standard hybrid search fusion method because
        # it is parameter-free (k=60 works well universally) and
        # robust to score scale differences between retrieval methods.
        rrf_scores: Dict[str, float] = {}
        for ranked_list in ranked_lists:
            for rank, (doc_id, _score) in enumerate(ranked_list):
                if doc_id not in rrf_scores:
                    rrf_scores[doc_id] = 0.0
                rrf_scores[doc_id] += 1.0 / (k + rank + 1)

        sorted_results = sorted(
            rrf_scores.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_results

    def _cross_encoder_rerank(
        self,
        query: str,
        doc_ids: List[str],
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        # Rerank candidates using a cross-encoder for precise scoring.
        #
        # Cross-encoders process (query, document) pairs jointly through
        # a transformer, enabling deep token-level interaction. This is
        # far more accurate than bi-encoder dot products, but ~100x slower.
        if self.cross_encoder is None or not doc_ids:
            return [(did, 0.0) for did in doc_ids[:top_k]]

        pairs: List[Tuple[str, str]] = []
        for doc_id in doc_ids:
            doc = self._documents[doc_id]
            # Truncate to avoid exceeding model max length
            text = f"{doc.title}. {doc.text}"[:512]
            pairs.append((query, text))

        scores = self.cross_encoder.predict(pairs, batch_size=32)
        scored = list(zip(doc_ids, scores.tolist()))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def search(
        self,
        query: str,
        bm25_results: Optional[List[Tuple[str, float]]] = None,
        top_k: int = 10,
        rerank_candidates: int = 50,
        use_reranking: bool = True,
    ) -> List[SearchResult]:
        # Full hybrid search pipeline:
        #   1. Encode query -> vector search
        #   2. Combine with BM25 via RRF
        #   3. Rerank top candidates with cross-encoder

        # Step 1: Bi-encoder retrieval
        query_emb = self.embedding_model.encode([query])[0]
        query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-10)
        vector_results = self._vector_search(query_emb, top_k=rerank_candidates)

        # Step 2: Hybrid fusion
        ranked_lists = [vector_results]
        if bm25_results:
            ranked_lists.append(bm25_results)
        fused = self._reciprocal_rank_fusion(ranked_lists)
        candidate_ids = [doc_id for doc_id, _ in fused[:rerank_candidates]]

        # Step 3: Cross-encoder reranking
        if use_reranking and self.cross_encoder is not None:
            reranked = self._cross_encoder_rerank(query, candidate_ids, top_k)
        else:
            reranked = fused[:top_k]

        # Build result objects
        results: List[SearchResult] = []
        vector_scores = dict(vector_results)
        bm25_scores = dict(bm25_results) if bm25_results else {}
        for doc_id, score in reranked:
            doc = self._documents.get(doc_id)
            if doc is None:
                continue
            results.append(SearchResult(
                doc_id=doc_id,
                text=doc.text,
                title=doc.title,
                score=score,
                bm25_score=bm25_scores.get(doc_id, 0.0),
                vector_score=vector_scores.get(doc_id, 0.0),
                rerank_score=score if use_reranking else 0.0,
                metadata=doc.metadata,
            ))
        return results
```

The three-stage pipeline (bi-encoder retrieval, hybrid fusion, cross-encoder reranking) is
the **industry standard** architecture used by major search engines and recommendation
systems. The key insight is that each stage operates at a different **accuracy/latency
trade-off** point:

- **Bi-encoder**: ~1ms for 1M documents (with ANN index), moderate accuracy
- **BM25**: ~5ms, high precision for keyword queries
- **Cross-encoder**: ~50ms for 50 candidates, highest accuracy

## FAISS and HNSW: Approximate Nearest Neighbor Search

For production systems with millions of documents, brute-force search is too slow. **FAISS**
(Facebook AI Similarity Search) provides optimized ANN algorithms.

```python
# Production FAISS index wrapper
# Requires: pip install faiss-cpu (or faiss-gpu for GPU support)

class FAISSVectorStore:
    # HNSW-based vector store using FAISS for sub-millisecond ANN search.
    #
    # HNSW (Hierarchical Navigable Small World) builds a multi-layer
    # graph where each node connects to its approximate nearest neighbors.
    # Search navigates this graph greedily, achieving logarithmic
    # query time with >95% recall.

    def __init__(
        self,
        dimension: int,
        m: int = 32,
        ef_construction: int = 200,
        ef_search: int = 128,
    ) -> None:
        # m: number of connections per node (higher = more accurate, more RAM)
        # ef_construction: search depth during build (higher = better graph)
        # ef_search: search depth during query (higher = more accurate)
        import faiss
        self.dimension = dimension
        self.index = faiss.IndexHNSWFlat(dimension, m)
        self.index.hnsw.efConstruction = ef_construction
        self.index.hnsw.efSearch = ef_search
        self._id_map: List[str] = []

    def add(self, doc_ids: List[str], embeddings: np.ndarray) -> None:
        # Add normalized vectors to the index
        assert embeddings.shape[1] == self.dimension
        self.index.add(embeddings.astype(np.float32))
        self._id_map.extend(doc_ids)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        # Find approximate nearest neighbors
        query = query_vector.reshape(1, -1).astype(np.float32)
        distances, indices = self.index.search(query, top_k)
        results: List[Tuple[str, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            results.append((self._id_map[idx], float(dist)))
        return results

    def save(self, path: str) -> None:
        import faiss
        faiss.write_index(self.index, path)

    def load(self, path: str) -> None:
        import faiss
        self.index = faiss.read_index(path)
```

**Pitfall**: Using flat (brute-force) FAISS indices in production. For up to ~100K vectors,
`IndexFlatIP` is fine. Beyond that, you need ANN indices like HNSW or IVF. The **trade-off**
is recall vs speed: HNSW with M=32 typically achieves 95%+ recall at 100x the speed of
brute force, but uses ~2x the RAM.

## Choosing Embedding Models

Model selection has enormous impact on search quality. **Best practice** is to evaluate
on your domain data, but here are general guidelines:

- **sentence-transformers/all-MiniLM-L6-v2**: Fast, 384 dims, good baseline
- **BAAI/bge-small-en-v1.5**: Better quality, 384 dims, competitive with larger models
- **intfloat/e5-large-v2**: High quality, 1024 dims, strong zero-shot performance
- **Cross-encoders**: ms-marco-MiniLM-L-6-v2 for reranking (not for retrieval)

## Summary and Key Takeaways

- **Semantic search captures meaning** by encoding text as dense vectors, solving the
  vocabulary mismatch problem that plagues keyword-only search
- **Hybrid search (BM25 + vectors)** consistently outperforms either approach alone;
  reciprocal rank fusion is the standard combination method because it requires no
  parameter tuning
- **Bi-encoders are fast but approximate**; cross-encoders are accurate but slow --
  therefore, use bi-encoders for retrieval (thousands of candidates) and cross-encoders
  for reranking (top 50-100 candidates)
- **FAISS HNSW** provides sub-millisecond ANN search for millions of vectors with >95%
  recall, making dense retrieval practical at scale
- **Common mistake**: Fine-tuning embedding models on too little data or without hard
  negatives. Models trained with only random negatives learn to distinguish topics but not
  subtle relevance differences within a topic
- **Best practice**: Always normalize embeddings to unit length and use dot product (not
  cosine similarity) for FAISS -- this is mathematically equivalent but computationally
  cheaper
- **Pitfall**: Embedding long documents directly. Most models have a 512-token limit;
  chunk documents into overlapping passages (e.g., 256 tokens with 64-token overlap) and
  index each chunk separately
""",
    ),

    # --- 5. Autocomplete and Typeahead ---
    (
        "search/autocomplete-typeahead-systems",
        "Explain how to build a production autocomplete and typeahead system including trie-based "
        "suggestion data structures, prefix search with Elasticsearch completion suggesters, "
        "fuzzy matching with edit distance, popularity-weighted ranking with decay functions, "
        "and provide a complete Python implementation of a weighted trie with fuzzy matching "
        "and type hints suitable for real-time suggestion serving.",
        r"""
# Autocomplete and Typeahead Systems: From Tries to Production

## Why Autocomplete Is Harder Than It Looks

Autocomplete appears simple -- the user types a prefix, you show matching completions.
But building a **production-quality** typeahead system involves solving several hard
problems simultaneously: sub-10ms latency requirements (users notice anything slower),
fuzzy matching for typos, popularity-weighted ranking, personalization, and handling
millions of suggestion candidates efficiently.

**Because** autocomplete fires on every keystroke (or after a small debounce), it
generates 5-10x more queries than regular search. A system serving 1000 search queries
per second might handle 5000-10000 autocomplete requests per second. Therefore, the data
structure and serving architecture must be optimized for extreme read throughput with
minimal memory footprint.

**Common mistake**: Implementing autocomplete as a prefix query against a full-text search
index. While this works, it is typically 10-100x slower than a dedicated autocomplete data
structure, **because** full-text indices are optimized for term-level lookups, not prefix
iteration. Elasticsearch's completion suggester uses a dedicated FST (finite state
transducer) structure precisely to avoid this overhead.

## Trie Data Structures for Prefix Search

A **trie** (prefix tree) is the natural data structure for autocomplete. Each node
represents a character, and paths from root to leaf spell out complete suggestions. Prefix
search simply walks the trie to the prefix node and collects all descendants.

### Weighted Trie with Fuzzy Matching

```python
from __future__ import annotations

import heapq
import time
import math
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, Iterator
from pathlib import Path


@dataclass
class TrieNode:
    # A single node in the weighted trie
    children: Dict[str, TrieNode] = field(default_factory=dict)
    is_terminal: bool = False
    # The complete suggestion text (only set for terminal nodes)
    suggestion: str = ""
    # Popularity score for ranking (higher = more popular)
    weight: float = 0.0
    # Maximum weight among all descendants (for pruned search)
    max_descendant_weight: float = 0.0
    # Frequency count for popularity tracking
    frequency: int = 0


class WeightedTrie:
    # Trie with popularity-weighted ranking and fuzzy matching.
    #
    # Key features:
    #   - O(prefix_len) prefix lookup
    #   - Top-k results by popularity using max-heap pruning
    #   - Fuzzy matching with configurable edit distance
    #   - Time-decayed popularity scoring

    def __init__(self, decay_half_life_days: float = 30.0) -> None:
        self.root = TrieNode()
        self._size: int = 0
        self._decay_half_life = decay_half_life_days * 86400  # convert to seconds
        self._creation_time: float = time.time()

    def insert(
        self,
        text: str,
        weight: float = 1.0,
        timestamp: Optional[float] = None,
    ) -> None:
        # Insert or update a suggestion with its popularity weight
        normalized = text.lower().strip()
        if not normalized:
            return

        node = self.root
        for char in normalized:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]

        if not node.is_terminal:
            self._size += 1
        node.is_terminal = True
        node.suggestion = text  # preserve original casing
        node.frequency += 1

        # Apply time decay to the weight
        if timestamp is not None:
            age = time.time() - timestamp
            decay = math.exp(-0.693 * age / self._decay_half_life)
            weight *= decay

        node.weight = max(node.weight, weight)
        # Update max_descendant_weight up the path
        self._update_max_weights(normalized)

    def _update_max_weights(self, text: str) -> None:
        # Walk the path and update max_descendant_weight at each node
        node = self.root
        path_nodes: List[TrieNode] = [node]
        for char in text:
            node = node.children[char]
            path_nodes.append(node)

        # Bottom-up update
        for n in reversed(path_nodes):
            max_w = n.weight if n.is_terminal else 0.0
            for child in n.children.values():
                max_w = max(max_w, child.max_descendant_weight)
                if child.is_terminal:
                    max_w = max(max_w, child.weight)
            n.max_descendant_weight = max_w

    def prefix_search(
        self,
        prefix: str,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        # Find top-k suggestions matching a prefix, ranked by weight.
        # Uses a max-heap with pruning via max_descendant_weight.
        normalized = prefix.lower().strip()
        node = self.root
        for char in normalized:
            if char not in node.children:
                return []
            node = node.children[char]

        # Collect results using a priority queue
        # Heap entries: (-weight, suggestion)
        results: List[Tuple[float, str]] = []
        self._collect_top_k(node, results, top_k)

        # Sort by weight descending
        results.sort(reverse=True)
        return [(text, weight) for weight, text in results[:top_k]]

    def _collect_top_k(
        self,
        node: TrieNode,
        results: List[Tuple[float, str]],
        k: int,
    ) -> None:
        # DFS collection with pruning based on max_descendant_weight
        if node.is_terminal:
            if len(results) < k:
                heapq.heappush(results, (node.weight, node.suggestion))
            elif node.weight > results[0][0]:
                heapq.heapreplace(results, (node.weight, node.suggestion))

        # Sort children by max_descendant_weight for best-first traversal
        sorted_children = sorted(
            node.children.values(),
            key=lambda n: n.max_descendant_weight,
            reverse=True,
        )
        for child in sorted_children:
            # Prune: if this subtree can not beat the worst result in top-k, skip
            if len(results) >= k and child.max_descendant_weight <= results[0][0]:
                break
            self._collect_top_k(child, results, k)

    def fuzzy_search(
        self,
        query: str,
        max_edit_distance: int = 2,
        top_k: int = 10,
    ) -> List[Tuple[str, float, int]]:
        # Fuzzy prefix search allowing up to max_edit_distance typos.
        # Returns (suggestion, weight, edit_distance) tuples.
        #
        # Uses a modified DFS that tracks remaining edit budget at each node.
        # Operations: insertion, deletion, substitution (not transposition).
        normalized = query.lower().strip()
        results: List[Tuple[str, float, int]] = []
        self._fuzzy_dfs(
            node=self.root,
            query=normalized,
            query_pos=0,
            edits_remaining=max_edit_distance,
            results=results,
        )
        # Sort by (edit_distance ASC, weight DESC)
        results.sort(key=lambda x: (x[2], -x[1]))
        return results[:top_k]

    def _fuzzy_dfs(
        self,
        node: TrieNode,
        query: str,
        query_pos: int,
        edits_remaining: int,
        results: List[Tuple[str, float, int]],
    ) -> None:
        # Recursive fuzzy search with edit distance tracking
        edit_distance_used = (len(query) - query_pos) if query_pos <= len(query) else 0

        # If we have consumed the entire query, collect all terminals in subtree
        if query_pos >= len(query):
            if node.is_terminal:
                ed = len(query) - query_pos + (0 if query_pos >= len(query) else 0)
                total_ed = (len(query) if query_pos == 0 else 0)
                # For prefix matches beyond the query, edit distance is 0
                results.append((node.suggestion, node.weight, len(query) - len(query)))
            # Continue collecting prefix completions
            if edits_remaining >= 0:
                for child in node.children.values():
                    self._fuzzy_dfs(child, query, query_pos, edits_remaining, results)
            return

        if edits_remaining < 0:
            return

        current_char = query[query_pos]

        for char, child in node.children.items():
            if char == current_char:
                # Exact match: advance both, no edit cost
                self._fuzzy_dfs(child, query, query_pos + 1, edits_remaining, results)
            else:
                # Substitution: advance both, cost 1 edit
                self._fuzzy_dfs(child, query, query_pos + 1, edits_remaining - 1, results)
                # Insertion: advance trie only (extra char in trie), cost 1 edit
                self._fuzzy_dfs(child, query, query_pos, edits_remaining - 1, results)

        # Deletion: skip query char (char missing in trie), cost 1 edit
        self._fuzzy_dfs(node, query, query_pos + 1, edits_remaining - 1, results)
```

The **max_descendant_weight pruning** optimization is critical for performance. Without it,
a prefix search for "a" on a large trie visits every node that starts with "a." With
pruning, we stop exploring subtrees whose best possible result cannot beat what we already
have, reducing search from O(N) to O(k * log(N)) in practice.

## Elasticsearch Completion Suggester

For production deployments, Elasticsearch provides a dedicated **completion suggester**
backed by an FST (finite state transducer) that lives entirely in memory for maximum speed.

```python
# Elasticsearch completion suggester setup and querying

from typing import Any, Dict, List, Optional


def build_suggestion_mapping() -> Dict[str, Any]:
    # Mapping for an autocomplete index using the completion suggester.
    #
    # The completion type builds an in-memory FST (finite state transducer)
    # that is optimized for prefix lookups. This is ~10x faster than
    # querying a text field with prefix queries.
    return {
        "mappings": {
            "properties": {
                "suggest": {
                    "type": "completion",
                    "analyzer": "simple",
                    "preserve_separators": True,
                    "preserve_position_increments": True,
                    "max_input_length": 50,
                    "contexts": [
                        {
                            # Category context for filtered suggestions
                            "name": "category",
                            "type": "category",
                        },
                        {
                            # Geo context for location-aware suggestions
                            "name": "location",
                            "type": "geo",
                            "precision": 4,
                        },
                    ],
                },
                "title": {"type": "text"},
                "popularity": {"type": "float"},
                "category": {"type": "keyword"},
            },
        },
    }


def index_suggestion(
    title: str,
    category: str,
    popularity: float,
    aliases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # Build a document for the completion suggester.
    # Multiple input strings can map to the same suggestion.
    inputs = [title.lower()]
    if aliases:
        inputs.extend(a.lower() for a in aliases)
    # Also add individual words as inputs for mid-word matching
    words = title.lower().split()
    if len(words) > 1:
        inputs.extend(words)

    return {
        "suggest": {
            "input": inputs,
            "weight": int(popularity * 100),
            "contexts": {
                "category": [category],
            },
        },
        "title": title,
        "popularity": popularity,
        "category": category,
    }


def build_suggestion_query(
    prefix: str,
    category: Optional[str] = None,
    size: int = 10,
    fuzzy: bool = True,
) -> Dict[str, Any]:
    # Build a suggestion query with optional fuzzy matching and context filtering
    suggest_config: Dict[str, Any] = {
        "prefix": prefix.lower(),
        "completion": {
            "field": "suggest",
            "size": size,
            "skip_duplicates": True,
        },
    }
    if fuzzy:
        suggest_config["completion"]["fuzzy"] = {
            "fuzziness": "AUTO",
            "min_length": 3,
            "prefix_length": 1,
            "transpositions": True,
        }
    if category:
        suggest_config["completion"]["contexts"] = {
            "category": [{"context": category}],
        }

    return {
        "suggest": {
            "product_suggest": suggest_config,
        },
    }
```

## Production Architecture Patterns

### Multi-Layer Suggestion System

**Best practice** is a multi-layer architecture that combines multiple suggestion sources:

```python
@dataclass
class SuggestionCandidate:
    # A candidate suggestion from any source
    text: str
    score: float
    source: str        # "popular", "recent", "personal", "trending"
    category: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiSourceSuggester:
    # Combines suggestions from multiple sources with weighted blending.
    #
    # Sources (in priority order):
    #   1. User's recent searches (personalization)
    #   2. Trending queries (freshness)
    #   3. Popular queries (global popularity)
    #   4. Product/entity catalog (structured data)

    def __init__(
        self,
        popular_trie: WeightedTrie,
        trending_trie: WeightedTrie,
    ) -> None:
        self.popular_trie = popular_trie
        self.trending_trie = trending_trie
        # Per-user recent queries (in production, use Redis)
        self._user_history: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    def record_search(
        self, user_id: str, query: str, timestamp: Optional[float] = None
    ) -> None:
        # Record a user's search for personalization
        ts = timestamp or time.time()
        history = self._user_history[user_id]
        history.append((query, ts))
        # Keep only last 100 searches
        if len(history) > 100:
            self._user_history[user_id] = history[-100:]

    def suggest(
        self,
        prefix: str,
        user_id: Optional[str] = None,
        top_k: int = 10,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[SuggestionCandidate]:
        # Get blended suggestions from all sources
        w = weights or {
            "personal": 3.0,
            "trending": 2.0,
            "popular": 1.0,
        }
        all_candidates: List[SuggestionCandidate] = []

        # Source 1: Personal history (prefix match against recent queries)
        if user_id and user_id in self._user_history:
            prefix_lower = prefix.lower()
            for query, ts in reversed(self._user_history[user_id]):
                if query.lower().startswith(prefix_lower):
                    age = time.time() - ts
                    recency_score = math.exp(-age / (7 * 86400))  # 7-day half-life
                    all_candidates.append(SuggestionCandidate(
                        text=query,
                        score=recency_score * w["personal"],
                        source="personal",
                    ))

        # Source 2: Trending queries
        for text, score in self.trending_trie.prefix_search(prefix, top_k=top_k):
            all_candidates.append(SuggestionCandidate(
                text=text,
                score=score * w["trending"],
                source="trending",
            ))

        # Source 3: Popular queries
        for text, score in self.popular_trie.prefix_search(prefix, top_k=top_k):
            all_candidates.append(SuggestionCandidate(
                text=text,
                score=score * w["popular"],
                source="popular",
            ))

        # Deduplicate by lowercased text, keeping highest score
        seen: Dict[str, SuggestionCandidate] = {}
        for candidate in all_candidates:
            key = candidate.text.lower()
            if key not in seen or candidate.score > seen[key].score:
                seen[key] = candidate

        # Sort by score descending
        results = sorted(seen.values(), key=lambda c: c.score, reverse=True)
        return results[:top_k]
```

**However**, combining multiple suggestion sources introduces a subtle **pitfall**: if the
weighting is not carefully tuned, personal suggestions can dominate even when the user is
searching for something new, or trending suggestions can push out highly relevant popular
queries. The **trade-off** is between personalization (showing what *this* user likely
wants) and exploration (showing globally relevant suggestions the user might not discover
otherwise). **Best practice** is to reserve the first 1-2 slots for personal matches
and fill the rest from global sources.

## Performance Optimization

Key performance considerations for production autocomplete:

- **Debouncing**: Do not fire a request on every keystroke. Wait 100-200ms after the last
  keystroke before sending the request. This reduces backend load by 60-80%.
- **Request cancellation**: Cancel in-flight requests when the user types another character.
  Stale responses arriving late cause UI flicker.
- **Client-side caching**: Cache prefix responses in the browser. If the user types "mac"
  and the response arrives, the results for "mac" are already available when the user
  types "macb" (as a filtered subset).
- **Precomputation**: For the most popular prefixes (top 1000), precompute suggestions
  and store them in Redis or a CDN for single-digit millisecond latency.

## Summary and Key Takeaways

- **Tries are the natural data structure** for autocomplete, providing O(prefix_length)
  lookup and efficient prefix iteration
- **Max-descendant-weight pruning** transforms naive O(N) collection into practical O(k
  log N) top-k retrieval by skipping subtrees that cannot improve the result set
- **Fuzzy matching with edit distance** handles typos by exploring character substitutions,
  insertions, and deletions during trie traversal -- limit to edit distance 2 for
  acceptable latency
- **Elasticsearch completion suggesters** use FSTs for in-memory prefix lookup that is
  10x faster than text field prefix queries, with built-in fuzzy matching and context
  filtering
- **Best practice**: Use a multi-source architecture combining personal history, trending
  queries, and popular queries for the most relevant suggestions
- **Pitfall**: Firing autocomplete requests on every keystroke without debouncing -- this
  generates 5-10x unnecessary load; implement 100-200ms debounce on the client
- **Trade-off**: Fuzzy matching increases recall (catching typos) but also increases false
  positives and latency; restrict fuzziness to edit distance 1-2 and only activate after
  3+ characters are typed
""",
    ),
]
