"""Search system design — indexing pipeline, autocomplete, ranking algorithms, and relevance evaluation."""

PAIRS = [
    (
        "system-design/search-indexing-pipeline",
        "Design a search indexing pipeline covering crawling, parsing, indexing, and ranking for a content search system.",
        '''Search indexing pipeline — crawl, parse, index, and rank:

```python
# --- indexing_pipeline.py --- Document indexing pipeline ---

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional, Generator
from enum import Enum

logger = logging.getLogger(__name__)


class DocumentStatus(Enum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    PARSED = "parsed"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass
class RawDocument:
    """Document as fetched from source."""
    url: str
    content: str
    content_type: str          # "text/html", "application/pdf"
    fetched_at: datetime
    http_status: int
    headers: dict[str, str]
    content_hash: str = ""

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class ParsedDocument:
    """Document after content extraction and normalization."""
    doc_id: str
    url: str
    title: str
    body: str                   # extracted clean text
    headings: list[str]
    links: list[str]
    images: list[dict]
    metadata: dict[str, Any]
    language: str
    word_count: int
    content_hash: str
    parsed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IndexDocument:
    """Document ready for search index insertion."""
    doc_id: str
    url: str
    title: str
    body: str
    headings: list[str]
    tokens: list[str]           # analyzed/stemmed tokens
    title_tokens: list[str]
    metadata: dict[str, Any]
    language: str
    word_count: int
    quality_score: float        # 0.0 to 1.0
    boost: float                # ranking boost factor
    indexed_at: datetime = field(default_factory=datetime.utcnow)


class ContentParser:
    """Extract structured text from raw HTML/documents."""

    def parse(self, raw: RawDocument) -> ParsedDocument:
        """Parse raw document into structured content."""
        if "text/html" in raw.content_type:
            return self._parse_html(raw)
        elif "application/pdf" in raw.content_type:
            return self._parse_pdf(raw)
        else:
            return self._parse_plain_text(raw)

    def _parse_html(self, raw: RawDocument) -> ParsedDocument:
        """Extract content from HTML using BeautifulSoup."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw.content, "html.parser")

        # Remove script, style, nav, footer elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Extract headings
        headings = []
        for h in soup.find_all(["h1", "h2", "h3"]):
            headings.append(h.get_text(strip=True))

        # Extract main content
        body = soup.get_text(separator=" ", strip=True)
        body = re.sub(r"\s+", " ", body).strip()

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            links.append(a["href"])

        # Extract images
        images = []
        for img in soup.find_all("img", src=True):
            images.append({
                "src": img["src"],
                "alt": img.get("alt", ""),
            })

        # Extract metadata
        metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name", meta.get("property", ""))
            content = meta.get("content", "")
            if name and content:
                metadata[name] = content

        doc_id = hashlib.md5(raw.url.encode()).hexdigest()
        return ParsedDocument(
            doc_id=doc_id,
            url=raw.url,
            title=title,
            body=body,
            headings=headings,
            links=links,
            images=images,
            metadata=metadata,
            language=metadata.get("language", "en"),
            word_count=len(body.split()),
            content_hash=raw.content_hash,
        )

    def _parse_pdf(self, raw: RawDocument) -> ParsedDocument:
        """Extract text from PDF."""
        # In production, use pdfplumber, PyMuPDF, or Apache Tika
        doc_id = hashlib.md5(raw.url.encode()).hexdigest()
        return ParsedDocument(
            doc_id=doc_id,
            url=raw.url,
            title=raw.url.split("/")[-1],
            body="[PDF content extraction]",
            headings=[],
            links=[],
            images=[],
            metadata={},
            language="en",
            word_count=0,
            content_hash=raw.content_hash,
        )

    def _parse_plain_text(self, raw: RawDocument) -> ParsedDocument:
        doc_id = hashlib.md5(raw.url.encode()).hexdigest()
        return ParsedDocument(
            doc_id=doc_id,
            url=raw.url,
            title=raw.url.split("/")[-1],
            body=raw.content,
            headings=[],
            links=[],
            images=[],
            metadata={},
            language="en",
            word_count=len(raw.content.split()),
            content_hash=raw.content_hash,
        )


class TextAnalyzer:
    """Tokenize and normalize text for indexing."""

    def __init__(self, language: str = "en"):
        self.language = language
        self._stop_words = self._load_stop_words(language)

    def analyze(self, text: str) -> list[str]:
        """Full analysis pipeline: tokenize -> lowercase -> stop words -> stem."""
        tokens = self._tokenize(text)
        tokens = [t.lower() for t in tokens]
        tokens = [t for t in tokens if t not in self._stop_words]
        tokens = [self._stem(t) for t in tokens]
        tokens = [t for t in tokens if len(t) > 1]
        return tokens

    def _tokenize(self, text: str) -> list[str]:
        """Split text into word tokens."""
        return re.findall(r"\b\w+\b", text)

    def _stem(self, word: str) -> str:
        """Simple suffix-stripping stemmer (use Snowball in production)."""
        # Porter stemmer would be used in production
        suffixes = ["ing", "tion", "ness", "ment", "able", "ible", "ful", "less", "ous"]
        for suffix in suffixes:
            if word.endswith(suffix) and len(word) > len(suffix) + 2:
                return word[:-len(suffix)]
        if word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
            return word[:-1]
        return word

    def _load_stop_words(self, language: str) -> set[str]:
        return {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "and", "or", "but", "not", "no", "nor", "if", "then", "else",
            "it", "its", "this", "that", "these", "those", "i", "we", "you",
            "he", "she", "they", "me", "him", "her", "us", "them",
        }
```

```python
# --- pipeline.py --- Orchestrate the indexing pipeline ---

import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator

from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)


class IndexingPipeline:
    """Orchestrate the full indexing pipeline."""

    def __init__(
        self,
        parser: ContentParser,
        analyzer: TextAnalyzer,
        es_client: AsyncElasticsearch,
        index_name: str = "documents",
    ):
        self.parser = parser
        self.analyzer = analyzer
        self.es = es_client
        self.index_name = index_name

    async def create_index(self) -> None:
        """Create Elasticsearch index with custom mappings."""
        mapping = {
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "analysis": {
                    "analyzer": {
                        "content_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "stop",
                                "snowball",
                                "asciifolding",
                            ],
                        },
                        "autocomplete_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "edge_ngram_filter",
                            ],
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
                    "url": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "content_analyzer",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_analyzer",
                                "search_analyzer": "standard",
                            },
                            "exact": {"type": "keyword"},
                        },
                    },
                    "body": {
                        "type": "text",
                        "analyzer": "content_analyzer",
                    },
                    "headings": {
                        "type": "text",
                        "analyzer": "content_analyzer",
                        "boost": 1.5,
                    },
                    "language": {"type": "keyword"},
                    "word_count": {"type": "integer"},
                    "quality_score": {"type": "float"},
                    "indexed_at": {"type": "date"},
                    "metadata": {"type": "object", "enabled": False},
                },
            },
        }

        exists = await self.es.indices.exists(index=self.index_name)
        if not exists:
            await self.es.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Created index: {self.index_name}")

    async def index_document(self, raw: RawDocument) -> str:
        """Process and index a single document."""
        # Step 1: Parse
        parsed = self.parser.parse(raw)

        # Step 2: Analyze (tokenize, stem)
        tokens = self.analyzer.analyze(parsed.body)
        title_tokens = self.analyzer.analyze(parsed.title)

        # Step 3: Score quality
        quality_score = self._compute_quality_score(parsed)

        # Step 4: Build index document
        doc = {
            "url": parsed.url,
            "title": parsed.title,
            "body": parsed.body,
            "headings": parsed.headings,
            "language": parsed.language,
            "word_count": parsed.word_count,
            "quality_score": quality_score,
            "metadata": parsed.metadata,
            "indexed_at": datetime.utcnow().isoformat(),
        }

        # Step 5: Index in Elasticsearch
        await self.es.index(
            index=self.index_name,
            id=parsed.doc_id,
            body=doc,
        )

        logger.info(f"Indexed: {parsed.url} (quality: {quality_score:.2f})")
        return parsed.doc_id

    async def bulk_index(
        self, documents: list[RawDocument], batch_size: int = 100
    ) -> dict:
        """Bulk index documents for throughput."""
        from elasticsearch.helpers import async_bulk

        stats = {"indexed": 0, "failed": 0, "skipped": 0}

        async def _generate_actions():
            for raw in documents:
                try:
                    parsed = self.parser.parse(raw)
                    quality = self._compute_quality_score(parsed)

                    if quality < 0.1:
                        stats["skipped"] += 1
                        continue

                    yield {
                        "_index": self.index_name,
                        "_id": parsed.doc_id,
                        "_source": {
                            "url": parsed.url,
                            "title": parsed.title,
                            "body": parsed.body,
                            "headings": parsed.headings,
                            "language": parsed.language,
                            "word_count": parsed.word_count,
                            "quality_score": quality,
                            "indexed_at": datetime.utcnow().isoformat(),
                        },
                    }
                except Exception as e:
                    logger.warning(f"Parse failed for {raw.url}: {e}")
                    stats["failed"] += 1

        success, errors = await async_bulk(
            self.es,
            _generate_actions(),
            chunk_size=batch_size,
            raise_on_error=False,
        )

        stats["indexed"] = success
        stats["failed"] += len(errors) if errors else 0
        logger.info(f"Bulk indexed: {stats}")
        return stats

    def _compute_quality_score(self, doc: ParsedDocument) -> float:
        """Heuristic quality score based on content signals."""
        score = 0.5  # base

        # Title quality
        if doc.title and len(doc.title) > 10:
            score += 0.1
        if doc.title and len(doc.title) > 30:
            score += 0.05

        # Content length (prefer substantial content)
        if doc.word_count > 100:
            score += 0.1
        if doc.word_count > 500:
            score += 0.1
        if doc.word_count > 5000:
            score -= 0.05  # extremely long might be low quality

        # Structure (headings indicate organized content)
        if len(doc.headings) >= 2:
            score += 0.1

        # Metadata presence
        if doc.metadata.get("description"):
            score += 0.05

        return min(1.0, max(0.0, score))
```

```
Indexing Pipeline Architecture:

  [Data Sources]                    [Processing]                [Storage]
  +-----------+                   +-------------+           +------------------+
  | Web Pages |---> Crawler ----> | Parser      | --------> | Elasticsearch    |
  | Database  |---> CDC --------> | Analyzer    |           | (inverted index) |
  | Files     |---> Watcher ----> | Quality     |           +------------------+
  | APIs      |---> Poller -----> | Scorer      |                  |
  +-----------+                   +-------------+           +------------------+
                                        |                   | Search API       |
                                   [Queue]                  | (query, rank,    |
                                   Kafka / SQS              |  return results) |
                                        |                   +------------------+
                                   [Monitoring]
                                   - Index lag
                                   - Parse failures
                                   - Quality distribution

  Pipeline stages:
  1. CRAWL:  Fetch content from sources (respect robots.txt, rate limits)
  2. PARSE:  Extract text, metadata, structure from raw content
  3. ANALYZE: Tokenize, stem, remove stop words, detect language
  4. SCORE:  Compute quality signals (freshness, length, structure)
  5. INDEX:  Write to Elasticsearch with proper mappings and analyzers
  6. REFRESH: Periodic re-indexing to catch updates and remove stale docs
```

| Pipeline Stage | Tool/Library | Purpose |
|---------------|-------------|---------|
| Crawl | Scrapy, requests, Playwright | Fetch content from sources |
| Parse HTML | BeautifulSoup, lxml | Extract text and metadata |
| Parse PDF | pdfplumber, PyMuPDF | Extract text from documents |
| Analyze | NLTK, SpaCy, Snowball | Tokenize, stem, NER |
| Index | Elasticsearch, OpenSearch | Store inverted index |
| Queue | Kafka, SQS, Celery | Decouple stages for throughput |
| Monitor | Prometheus, Grafana | Track lag, errors, throughput |

Key patterns:
1. Separate crawl from index with a message queue for fault tolerance and scalability
2. Use content hashing to detect duplicates and avoid re-indexing unchanged documents
3. Compute quality scores during indexing to boost high-quality results at query time
4. Use custom Elasticsearch analyzers (edge ngram for autocomplete, snowball for stemming)
5. Bulk index in batches (100-500 docs) for throughput — avoid single-document inserts'''
    ),
    (
        "system-design/autocomplete-typeahead",
        "Design an autocomplete and typeahead system with prefix matching, popularity ranking, and personalization.",
        '''Autocomplete and typeahead system design:

```python
# --- autocomplete.py --- Autocomplete service ---

from __future__ import annotations

import time
import logging
from typing import Optional
from dataclasses import dataclass, field

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class Suggestion:
    """A single autocomplete suggestion."""
    text: str
    score: float           # popularity/relevance score
    category: Optional[str] = None   # "product", "brand", "category"
    metadata: dict = field(default_factory=dict)


class AutocompleteService:
    """Fast prefix-based autocomplete using Redis sorted sets.

    Architecture:
    - Redis sorted set per prefix for O(log N) lookups
    - Periodic rebuild from search analytics
    - Personalization layer on top
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "ac:",
        max_suggestions: int = 10,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.max_suggestions = max_suggestions

    async def suggest(
        self,
        query: str,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[Suggestion]:
        """Get autocomplete suggestions for a query prefix.

        1. Normalize query
        2. Fetch from Redis sorted set
        3. Apply personalization boost
        4. Return top N suggestions
        """
        query = self._normalize(query)
        if len(query) < 2:
            return []

        # Fetch from Redis
        key = f"{self.prefix}{query}"
        raw_results = await self.redis.zrevrange(
            key, 0, limit * 3,  # fetch extra for filtering
            withscores=True,
        )

        suggestions = []
        for text, score in raw_results:
            text_str = text.decode() if isinstance(text, bytes) else text
            suggestion = Suggestion(
                text=text_str,
                score=float(score),
                category=await self._get_category(text_str),
            )
            suggestions.append(suggestion)

        # Apply personalization
        if user_id:
            suggestions = await self._personalize(suggestions, user_id)

        # Filter by category
        if category:
            suggestions = [s for s in suggestions if s.category == category]

        # Sort by final score and limit
        suggestions.sort(key=lambda s: s.score, reverse=True)
        return suggestions[:limit]

    async def build_index(self, terms: list[tuple[str, float]]) -> int:
        """Build autocomplete index from (term, score) pairs.

        For each term, index all prefixes with the term's score.
        E.g., "python" -> "py", "pyt", "pyth", "pytho", "python"
        """
        pipeline = self.redis.pipeline()
        indexed = 0

        for term, score in terms:
            normalized = self._normalize(term)
            if len(normalized) < 2:
                continue

            # Index all prefixes of length 2+
            for i in range(2, len(normalized) + 1):
                prefix_key = f"{self.prefix}{normalized[:i]}"
                pipeline.zadd(prefix_key, {term: score})
                # Set TTL to auto-expire stale entries
                pipeline.expire(prefix_key, 86400 * 7)  # 7 days

            indexed += 1

            # Execute in batches
            if indexed % 1000 == 0:
                await pipeline.execute()
                pipeline = self.redis.pipeline()

        await pipeline.execute()
        logger.info(f"Built autocomplete index: {indexed} terms")
        return indexed

    async def record_selection(
        self, query: str, selected_term: str, user_id: Optional[str] = None
    ) -> None:
        """Record when a user selects a suggestion (for ranking)."""
        normalized = self._normalize(query)

        # Boost the selected term's score
        for i in range(2, len(normalized) + 1):
            prefix_key = f"{self.prefix}{normalized[:i]}"
            await self.redis.zincrby(prefix_key, 1.0, selected_term)

        # Record personal selection history
        if user_id:
            await self.redis.zadd(
                f"ac:personal:{user_id}",
                {selected_term: time.time()},
            )
            await self.redis.expire(f"ac:personal:{user_id}", 86400 * 30)

    async def _personalize(
        self, suggestions: list[Suggestion], user_id: str
    ) -> list[Suggestion]:
        """Boost suggestions based on user's history."""
        personal_key = f"ac:personal:{user_id}"
        personal_history = await self.redis.zrevrange(
            personal_key, 0, 50, withscores=True
        )

        personal_terms = {
            (t.decode() if isinstance(t, bytes) else t): s
            for t, s in personal_history
        }

        for suggestion in suggestions:
            if suggestion.text in personal_terms:
                suggestion.score *= 1.5  # 50% boost for personal history

        return suggestions

    async def _get_category(self, term: str) -> Optional[str]:
        """Look up category for a term."""
        cat = await self.redis.hget("ac:categories", term)
        return cat.decode() if cat else None

    def _normalize(self, text: str) -> str:
        """Normalize query for consistent prefix matching."""
        import unicodedata
        text = text.strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if c.isalnum() or c == " ")
        return text
```

```python
# --- trie_autocomplete.py --- Trie-based in-memory autocomplete ---

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import heapq


@dataclass
class TrieNode:
    """Node in the autocomplete trie."""
    children: dict[str, TrieNode] = field(default_factory=dict)
    is_end: bool = False
    term: str = ""
    score: float = 0.0


class TrieAutocomplete:
    """In-memory trie for sub-millisecond autocomplete.

    Suitable for:
    - Product names (up to ~1M entries)
    - User names
    - Tags and categories

    Not suitable for:
    - Full-text search (use Elasticsearch)
    - Billions of entries (too much memory)
    """

    def __init__(self):
        self.root = TrieNode()
        self.size = 0

    def insert(self, term: str, score: float = 1.0) -> None:
        """Insert a term with its popularity score."""
        normalized = term.strip().lower()
        node = self.root

        for char in normalized:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]

        node.is_end = True
        node.term = term  # preserve original casing
        node.score = score
        self.size += 1

    def search(self, prefix: str, limit: int = 10) -> list[Suggestion]:
        """Find top-K completions for a prefix."""
        normalized = prefix.strip().lower()

        # Navigate to the prefix node
        node = self.root
        for char in normalized:
            if char not in node.children:
                return []
            node = node.children[char]

        # Collect all completions under this prefix
        candidates: list[Suggestion] = []
        self._collect(node, candidates)

        # Return top-K by score
        candidates.sort(key=lambda s: s.score, reverse=True)
        return candidates[:limit]

    def _collect(self, node: TrieNode, results: list[Suggestion]) -> None:
        """DFS to collect all terms under a node."""
        if node.is_end:
            results.append(Suggestion(text=node.term, score=node.score))

        for child_node in node.children.values():
            self._collect(child_node, results)

    def delete(self, term: str) -> bool:
        """Remove a term from the trie."""
        normalized = term.strip().lower()
        node = self.root

        for char in normalized:
            if char not in node.children:
                return False
            node = node.children[char]

        if node.is_end:
            node.is_end = False
            node.term = ""
            node.score = 0.0
            self.size -= 1
            return True
        return False

    def update_score(self, term: str, score: float) -> None:
        """Update the popularity score for a term."""
        normalized = term.strip().lower()
        node = self.root

        for char in normalized:
            if char not in node.children:
                return
            node = node.children[char]

        if node.is_end:
            node.score = score
```

```python
# --- es_autocomplete.py --- Elasticsearch-based autocomplete ---

from elasticsearch import AsyncElasticsearch


class ElasticsearchAutocomplete:
    """Autocomplete using Elasticsearch completion suggester.

    Best for: large-scale autocomplete with complex filtering.
    """

    def __init__(self, es: AsyncElasticsearch, index: str = "suggestions"):
        self.es = es
        self.index = index

    async def create_index(self) -> None:
        """Create index with completion field."""
        mapping = {
            "mappings": {
                "properties": {
                    "suggest": {
                        "type": "completion",
                        "analyzer": "simple",
                        "preserve_separators": True,
                        "preserve_position_increments": True,
                        "max_input_length": 50,
                        "contexts": [
                            {"name": "category", "type": "category"},
                        ],
                    },
                    "title": {"type": "text"},
                    "popularity": {"type": "integer"},
                    "category": {"type": "keyword"},
                },
            },
        }
        await self.es.indices.create(index=self.index, body=mapping)

    async def index_suggestion(
        self,
        doc_id: str,
        title: str,
        category: str,
        popularity: int,
    ) -> None:
        """Index a suggestion with category context."""
        await self.es.index(
            index=self.index,
            id=doc_id,
            body={
                "suggest": {
                    "input": [title],
                    "weight": popularity,
                    "contexts": {"category": [category]},
                },
                "title": title,
                "popularity": popularity,
                "category": category,
            },
        )

    async def suggest(
        self,
        query: str,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get completion suggestions."""
        suggest_body = {
            "suggest": {
                "title-suggest": {
                    "prefix": query,
                    "completion": {
                        "field": "suggest",
                        "size": limit,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO",  # typo tolerance
                        },
                    },
                },
            },
        }

        if category:
            suggest_body["suggest"]["title-suggest"]["completion"]["contexts"] = {
                "category": [category],
            }

        result = await self.es.search(index=self.index, body=suggest_body)
        suggestions = result["suggest"]["title-suggest"][0]["options"]

        return [
            {
                "text": s["text"],
                "score": s["_score"],
                "category": s["_source"].get("category"),
            }
            for s in suggestions
        ]
```

| Approach | Latency | Scale | Features | Best for |
|----------|---------|-------|----------|----------|
| Redis sorted set | ~1ms | Millions of terms | Prefix match, scoring | API suggestions |
| Trie (in-memory) | <0.1ms | ~1M terms | Prefix match, fast | Small datasets |
| ES completion | ~5ms | Billions | Fuzzy, context, filters | E-commerce search |
| ES edge_ngram | ~10ms | Billions | Substring match | Full-text search |
| Prefix hash table | ~0.5ms | Millions | Exact prefix only | Simple use cases |

Key patterns:
1. Index all prefixes of each term (min length 2) into Redis sorted sets for fast lookup
2. Use popularity/frequency as the score for sorted sets to rank suggestions
3. Record user selections to boost popular completions (feedback loop)
4. Add personalization by boosting terms from the user's search history
5. For typo tolerance, use Elasticsearch completion suggester with `fuzziness: "AUTO"`'''
    ),
    (
        "system-design/search-ranking",
        "Explain search ranking algorithms including TF-IDF, BM25, and learning to rank with practical implementation.",
        '''Search ranking algorithms — TF-IDF, BM25, and learning to rank:

```python
# --- ranking.py --- Search ranking implementations ---

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    doc_id: str
    title: str
    snippet: str
    url: str
    score: float
    explanation: dict = field(default_factory=dict)


class TfIdfRanker:
    """Classic TF-IDF ranking.

    TF(t,d) = freq(t in d) / total_terms(d)
    IDF(t) = log(N / df(t))
    Score = sum(TF * IDF) for each query term
    """

    def __init__(self, corpus_stats: CorpusStats):
        self.stats = corpus_stats

    def score(
        self, query_terms: list[str], doc_terms: list[str], doc_id: str
    ) -> float:
        """Compute TF-IDF score for a document against query terms."""
        total_docs = self.stats.total_documents
        doc_length = len(doc_terms)
        if doc_length == 0:
            return 0.0

        score = 0.0
        term_freq = {}
        for t in doc_terms:
            term_freq[t] = term_freq.get(t, 0) + 1

        for term in query_terms:
            tf = term_freq.get(term, 0) / doc_length
            df = self.stats.document_frequency(term)
            idf = math.log((total_docs + 1) / (df + 1)) + 1  # smoothed IDF

            score += tf * idf

        return score


class BM25Ranker:
    """Okapi BM25 ranking — industry standard for full-text search.

    Improvements over TF-IDF:
    - Term frequency saturation (diminishing returns for repeated terms)
    - Document length normalization
    - Tunable parameters k1 and b

    BM25(q, d) = sum[ IDF(t) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl/avgdl)) ]
    """

    def __init__(
        self,
        corpus_stats: CorpusStats,
        k1: float = 1.2,    # term frequency saturation
        b: float = 0.75,    # document length normalization
    ):
        self.stats = corpus_stats
        self.k1 = k1
        self.b = b

    def score(
        self, query_terms: list[str], doc_terms: list[str], doc_id: str
    ) -> tuple[float, dict]:
        """Compute BM25 score with explanation."""
        total_docs = self.stats.total_documents
        avg_doc_length = self.stats.average_document_length
        doc_length = len(doc_terms)

        if doc_length == 0:
            return 0.0, {}

        # Count term frequencies in document
        term_freq: dict[str, int] = {}
        for t in doc_terms:
            term_freq[t] = term_freq.get(t, 0) + 1

        total_score = 0.0
        explanation: dict[str, float] = {}

        for term in query_terms:
            tf = term_freq.get(term, 0)
            df = self.stats.document_frequency(term)

            # IDF with smoothing (prevents negative IDF)
            idf = math.log(
                (total_docs - df + 0.5) / (df + 0.5) + 1.0
            )

            # BM25 TF component with saturation and length normalization
            tf_component = (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * doc_length / avg_doc_length)
            )

            term_score = idf * tf_component
            total_score += term_score
            explanation[term] = round(term_score, 4)

        return total_score, explanation

    def multi_field_score(
        self,
        query_terms: list[str],
        doc: dict,
        field_weights: dict[str, float],
    ) -> float:
        """Score across multiple fields with weights.

        E.g., title match is worth more than body match.
        """
        total_score = 0.0

        for field_name, weight in field_weights.items():
            field_terms = doc.get(f"{field_name}_tokens", [])
            field_score, _ = self.score(query_terms, field_terms, doc["id"])
            total_score += field_score * weight

        return total_score


@dataclass
class CorpusStats:
    """Statistics about the document corpus for IDF computation."""
    total_documents: int
    average_document_length: float
    _df_cache: dict[str, int] = field(default_factory=dict)

    def document_frequency(self, term: str) -> int:
        """Number of documents containing this term."""
        return self._df_cache.get(term, 0)

    def set_df(self, term: str, count: int) -> None:
        self._df_cache[term] = count
```

```python
# --- learning_to_rank.py --- ML-based re-ranking ---

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RankingFeatures:
    """Features extracted for a (query, document) pair."""
    # Text relevance features
    bm25_title: float = 0.0
    bm25_body: float = 0.0
    bm25_headings: float = 0.0
    title_exact_match: float = 0.0
    query_coverage: float = 0.0      # % of query terms found in doc

    # Document quality features
    quality_score: float = 0.0
    word_count: float = 0.0
    heading_count: float = 0.0
    freshness_days: float = 0.0      # days since last update

    # Popularity features
    click_count: float = 0.0
    view_count: float = 0.0
    click_through_rate: float = 0.0

    # User features
    user_viewed_before: float = 0.0
    user_category_affinity: float = 0.0

    def to_array(self) -> np.ndarray:
        """Convert to feature vector for ML model."""
        return np.array([
            self.bm25_title,
            self.bm25_body,
            self.bm25_headings,
            self.title_exact_match,
            self.query_coverage,
            self.quality_score,
            np.log1p(self.word_count),
            self.heading_count,
            1.0 / (1.0 + self.freshness_days),  # decay
            np.log1p(self.click_count),
            np.log1p(self.view_count),
            self.click_through_rate,
            self.user_viewed_before,
            self.user_category_affinity,
        ])


class FeatureExtractor:
    """Extract ranking features from (query, document) pairs."""

    def __init__(self, bm25: BM25Ranker, click_store, user_store):
        self.bm25 = bm25
        self.clicks = click_store
        self.users = user_store

    async def extract(
        self,
        query_terms: list[str],
        doc: dict,
        user_id: Optional[str] = None,
    ) -> RankingFeatures:
        """Extract all ranking features."""
        features = RankingFeatures()

        # BM25 scores across fields
        features.bm25_title, _ = self.bm25.score(
            query_terms, doc.get("title_tokens", []), doc["id"]
        )
        features.bm25_body, _ = self.bm25.score(
            query_terms, doc.get("body_tokens", []), doc["id"]
        )
        features.bm25_headings, _ = self.bm25.score(
            query_terms, doc.get("heading_tokens", []), doc["id"]
        )

        # Exact match
        title_lower = doc.get("title", "").lower()
        query_str = " ".join(query_terms)
        features.title_exact_match = 1.0 if query_str in title_lower else 0.0

        # Query coverage
        doc_terms = set(doc.get("body_tokens", []))
        matched = sum(1 for t in query_terms if t in doc_terms)
        features.query_coverage = matched / len(query_terms) if query_terms else 0

        # Document features
        features.quality_score = doc.get("quality_score", 0.5)
        features.word_count = doc.get("word_count", 0)
        features.heading_count = len(doc.get("headings", []))

        # Popularity
        click_data = await self.clicks.get_stats(doc["id"])
        if click_data:
            features.click_count = click_data["clicks"]
            features.view_count = click_data["views"]
            features.click_through_rate = (
                click_data["clicks"] / max(click_data["views"], 1)
            )

        # Personalization
        if user_id:
            features.user_viewed_before = (
                1.0 if await self.users.has_viewed(user_id, doc["id"]) else 0.0
            )

        return features


class LearningToRankModel:
    """Re-rank search results using a trained ML model.

    Pipeline:
    1. Initial retrieval (BM25 top 1000)
    2. Feature extraction for each result
    3. ML model scores each result
    4. Re-rank by model score, return top K
    """

    def __init__(self, model_path: str):
        # In production, use LightGBM, XGBoost, or a neural ranker
        import lightgbm as lgb
        self.model = lgb.Booster(model_file=model_path)

    def predict(self, features: list[RankingFeatures]) -> list[float]:
        """Predict relevance scores for a batch of features."""
        feature_matrix = np.vstack([f.to_array() for f in features])
        scores = self.model.predict(feature_matrix)
        return scores.tolist()

    async def rerank(
        self,
        query_terms: list[str],
        initial_results: list[dict],
        feature_extractor: FeatureExtractor,
        user_id: Optional[str] = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        """Re-rank initial retrieval results using ML model."""
        # Extract features for all candidates
        features_list = []
        for doc in initial_results:
            features = await feature_extractor.extract(
                query_terms, doc, user_id
            )
            features_list.append(features)

        # Predict scores
        scores = self.predict(features_list)

        # Combine with results
        scored_results = list(zip(initial_results, scores))
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(
                doc_id=doc["id"],
                title=doc["title"],
                snippet=doc.get("body", "")[:200],
                url=doc["url"],
                score=score,
            )
            for doc, score in scored_results[:top_k]
        ]
```

```python
# --- combined_ranker.py --- Multi-stage ranking pipeline ---

class SearchRankingPipeline:
    """Multi-stage ranking pipeline used in production search.

    Stage 1 (Retrieval):     BM25 top 1000 from inverted index     (~10ms)
    Stage 2 (Scoring):       Multi-field BM25 with boosts           (~5ms)
    Stage 3 (Re-ranking):    ML model with all features             (~20ms)
    Stage 4 (Business):      Apply business rules and filters       (~1ms)
    """

    def __init__(
        self,
        es_client,
        bm25_ranker: BM25Ranker,
        ltr_model: LearningToRankModel,
        feature_extractor: FeatureExtractor,
    ):
        self.es = es_client
        self.bm25 = bm25_ranker
        self.ltr = ltr_model
        self.features = feature_extractor

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        """Execute full ranking pipeline."""
        # Stage 1: Initial retrieval (BM25)
        es_query = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title": {"query": query, "boost": 3.0}}},
                        {"match": {"headings": {"query": query, "boost": 2.0}}},
                        {"match": {"body": {"query": query, "boost": 1.0}}},
                    ],
                },
            },
            "size": 200,  # retrieve top 200 candidates
        }

        if filters:
            es_query["query"]["bool"]["filter"] = [
                {"term": {k: v}} for k, v in filters.items()
            ]

        es_results = await self.es.search(index="documents", body=es_query)
        candidates = [hit["_source"] | {"id": hit["_id"]} for hit in es_results["hits"]["hits"]]

        if not candidates:
            return {"results": [], "total": 0}

        # Stage 2-3: Re-rank with LTR model
        from text_analyzer import TextAnalyzer
        analyzer = TextAnalyzer()
        query_terms = analyzer.analyze(query)

        results = await self.ltr.rerank(
            query_terms, candidates, self.features,
            user_id=user_id, top_k=100,
        )

        # Stage 4: Business rules
        results = self._apply_business_rules(results)

        # Pagination
        start = (page - 1) * page_size
        page_results = results[start:start + page_size]

        return {
            "results": page_results,
            "total": len(results),
            "page": page,
            "page_size": page_size,
        }

    def _apply_business_rules(self, results: list[SearchResult]) -> list[SearchResult]:
        """Apply business rules after ML ranking."""
        # Deduplicate by domain
        seen_domains = set()
        deduped = []
        for r in results:
            domain = r.url.split("/")[2] if "/" in r.url else r.url
            if domain not in seen_domains or len(deduped) < 3:
                deduped.append(r)
                seen_domains.add(domain)
        return deduped
```

| Algorithm | Strengths | Weaknesses | When to use |
|-----------|-----------|------------|-------------|
| TF-IDF | Simple, interpretable | No length normalization, no saturation | Baseline, document similarity |
| BM25 | Length-normalized, saturating TF | No ML features, static | Primary retrieval stage |
| LTR (pointwise) | Uses many features, trainable | Doesn't model pairwise preferences | Medium complexity |
| LTR (pairwise) | Models relative preferences | Harder to train | High-quality ranking |
| LTR (listwise) | Optimizes list-level metrics | Most complex | Production search engines |
| Neural ranker | Semantic understanding | Expensive at inference time | Re-ranking top K results |

Key patterns:
1. Use multi-stage ranking: BM25 retrieval -> ML re-ranking for cost/quality balance
2. BM25 with k1=1.2 and b=0.75 is the default for most search engines
3. Extract features from multiple signals: text relevance, quality, popularity, personalization
4. Train LTR models on click-through data with NDCG as the optimization target
5. Apply business rules (dedup, freshness boost, pinned results) as the final stage'''
    ),
    (
        "system-design/search-relevance-evaluation",
        "Show how to evaluate search relevance using NDCG, MAP, precision/recall, and A/B testing for search quality.",
        '''Search relevance evaluation with NDCG, MAP, precision, and A/B testing:

```python
# --- evaluation.py --- Search relevance metrics ---

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class JudgedResult:
    """A search result with a human relevance judgment."""
    doc_id: str
    rank: int                  # position in result list (1-based)
    relevance: int             # 0=irrelevant, 1=marginal, 2=relevant, 3=highly relevant
    clicked: bool = False      # implicit signal


class SearchMetrics:
    """Compute information retrieval metrics."""

    @staticmethod
    def precision_at_k(results: list[JudgedResult], k: int) -> float:
        """Precision@K: fraction of top-K results that are relevant.

        P@K = |relevant in top K| / K
        """
        top_k = [r for r in results if r.rank <= k]
        if not top_k:
            return 0.0
        relevant = sum(1 for r in top_k if r.relevance > 0)
        return relevant / k

    @staticmethod
    def recall_at_k(
        results: list[JudgedResult], k: int, total_relevant: int
    ) -> float:
        """Recall@K: fraction of all relevant docs found in top K.

        R@K = |relevant in top K| / |total relevant|
        """
        if total_relevant == 0:
            return 0.0
        top_k = [r for r in results if r.rank <= k]
        found_relevant = sum(1 for r in top_k if r.relevance > 0)
        return found_relevant / total_relevant

    @staticmethod
    def average_precision(results: list[JudgedResult]) -> float:
        """Average Precision (AP): precision averaged at each relevant rank.

        AP = (1/R) * sum(P@k * rel(k)) for all k
        """
        sorted_results = sorted(results, key=lambda r: r.rank)
        total_relevant = sum(1 for r in results if r.relevance > 0)

        if total_relevant == 0:
            return 0.0

        running_relevant = 0
        precision_sum = 0.0

        for r in sorted_results:
            if r.relevance > 0:
                running_relevant += 1
                precision_at_rank = running_relevant / r.rank
                precision_sum += precision_at_rank

        return precision_sum / total_relevant

    @staticmethod
    def mean_average_precision(queries: list[list[JudgedResult]]) -> float:
        """MAP: Average of AP across all queries.

        MAP = (1/Q) * sum(AP(q)) for all queries q
        """
        if not queries:
            return 0.0
        aps = [SearchMetrics.average_precision(q) for q in queries]
        return sum(aps) / len(aps)

    @staticmethod
    def dcg_at_k(results: list[JudgedResult], k: int) -> float:
        """Discounted Cumulative Gain at K.

        DCG@K = sum(rel(i) / log2(i+1)) for i = 1 to K

        Lower-ranked relevant results contribute less (discounted by log).
        """
        top_k = sorted(
            [r for r in results if r.rank <= k],
            key=lambda r: r.rank,
        )
        dcg = 0.0
        for r in top_k:
            dcg += r.relevance / math.log2(r.rank + 1)
        return dcg

    @staticmethod
    def ndcg_at_k(results: list[JudgedResult], k: int) -> float:
        """Normalized DCG at K — DCG divided by ideal DCG.

        NDCG@K = DCG@K / IDCG@K

        IDCG is the DCG of the perfect ranking (sorted by relevance).
        NDCG ranges from 0 to 1, where 1 is perfect ranking.
        """
        dcg = SearchMetrics.dcg_at_k(results, k)

        # Ideal ranking: sort by relevance descending
        ideal_results = sorted(results, key=lambda r: r.relevance, reverse=True)
        for i, r in enumerate(ideal_results):
            r.rank = i + 1  # re-rank for ideal

        idcg = SearchMetrics.dcg_at_k(ideal_results, k)

        if idcg == 0:
            return 0.0
        return dcg / idcg

    @staticmethod
    def mean_reciprocal_rank(queries: list[list[JudgedResult]]) -> float:
        """MRR: average reciprocal rank of the first relevant result.

        MRR = (1/Q) * sum(1/rank_first_relevant) for all queries
        """
        if not queries:
            return 0.0

        rr_sum = 0.0
        for results in queries:
            sorted_results = sorted(results, key=lambda r: r.rank)
            for r in sorted_results:
                if r.relevance > 0:
                    rr_sum += 1.0 / r.rank
                    break

        return rr_sum / len(queries)
```

```python
# --- evaluation_framework.py --- Search quality evaluation system ---

from dataclasses import dataclass
from typing import Optional
import json
from datetime import datetime


@dataclass
class SearchEvaluation:
    """Evaluate search quality across a test set of queries."""

    def __init__(self, search_service, judge_store):
        self.search = search_service
        self.judges = judge_store

    async def evaluate(
        self, test_queries: list[str], k_values: list[int] = [1, 5, 10, 20]
    ) -> dict:
        """Run evaluation across all test queries."""
        all_results: dict[str, list] = {
            f"ndcg@{k}": [] for k in k_values
        }
        all_results.update({
            f"precision@{k}": [] for k in k_values
        })
        all_results["map"] = []
        all_query_results = []

        for query in test_queries:
            # Get search results
            response = await self.search.search(query, page_size=max(k_values))
            results = response["results"]

            # Get human judgments
            judgments = await self.judges.get_judgments(query)

            # Map results to judged results
            judged = []
            for i, result in enumerate(results):
                relevance = judgments.get(result.doc_id, 0)
                judged.append(JudgedResult(
                    doc_id=result.doc_id,
                    rank=i + 1,
                    relevance=relevance,
                ))

            # Compute metrics
            for k in k_values:
                all_results[f"ndcg@{k}"].append(
                    SearchMetrics.ndcg_at_k(judged, k)
                )
                all_results[f"precision@{k}"].append(
                    SearchMetrics.precision_at_k(judged, k)
                )

            all_results["map"].append(
                SearchMetrics.average_precision(judged)
            )
            all_query_results.append(judged)

        # Aggregate
        metrics = {}
        for metric_name, values in all_results.items():
            if values:
                metrics[metric_name] = {
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "median": sorted(values)[len(values) // 2],
                }

        metrics["mrr"] = SearchMetrics.mean_reciprocal_rank(all_query_results)
        metrics["query_count"] = len(test_queries)
        metrics["timestamp"] = datetime.utcnow().isoformat()

        return metrics

    def format_report(self, metrics: dict) -> str:
        """Format evaluation report."""
        lines = [
            "Search Relevance Evaluation Report",
            "=" * 50,
            f"Queries evaluated: {metrics['query_count']}",
            f"Timestamp: {metrics['timestamp']}",
            "",
            f"{'Metric':<20} {'Mean':>8} {'Min':>8} {'Max':>8}",
            f"{'-'*48}",
        ]

        for key in sorted(metrics.keys()):
            if isinstance(metrics[key], dict):
                m = metrics[key]
                lines.append(
                    f"{key:<20} {m['mean']:>8.4f} {m['min']:>8.4f} {m['max']:>8.4f}"
                )

        if "mrr" in metrics:
            lines.append(f"{'mrr':<20} {metrics['mrr']:>8.4f}")

        return "\n".join(lines)
```

```python
# --- ab_testing.py --- A/B testing for search quality ---

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SearchVariant(Enum):
    CONTROL = "control"        # current production ranking
    TREATMENT = "treatment"    # new ranking algorithm


@dataclass
class SearchExperiment:
    """A/B test configuration for search ranking."""
    id: str
    name: str
    description: str
    traffic_pct: float           # % of traffic to treatment (0-100)
    start_date: datetime
    end_date: Optional[datetime]
    metrics: list[str]           # ["ndcg@10", "ctr", "zero_result_rate"]
    status: str = "running"      # running, completed, rolled_back


class SearchABTest:
    """Route users to control/treatment search variants."""

    def __init__(self, experiment: SearchExperiment):
        self.experiment = experiment

    def assign_variant(self, user_id: str) -> SearchVariant:
        """Deterministically assign user to variant."""
        hash_input = f"{self.experiment.id}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        bucket = hash_value % 100

        if bucket < self.experiment.traffic_pct:
            return SearchVariant.TREATMENT
        return SearchVariant.CONTROL


@dataclass
class SearchClickLog:
    """Log entry for search interactions (used for offline evaluation)."""
    query: str
    user_id: str
    variant: str
    results_shown: list[str]      # doc_ids in display order
    clicked_results: list[str]    # doc_ids that were clicked
    result_count: int
    latency_ms: float
    timestamp: datetime


class OnlineMetrics:
    """Compute online search quality metrics from click logs."""

    @staticmethod
    def click_through_rate(logs: list[SearchClickLog]) -> float:
        """CTR: fraction of queries where at least one result was clicked."""
        if not logs:
            return 0.0
        clicked = sum(1 for log in logs if log.clicked_results)
        return clicked / len(logs)

    @staticmethod
    def zero_result_rate(logs: list[SearchClickLog]) -> float:
        """Fraction of queries that returned zero results."""
        if not logs:
            return 0.0
        zero = sum(1 for log in logs if log.result_count == 0)
        return zero / len(logs)

    @staticmethod
    def mean_reciprocal_rank_from_clicks(logs: list[SearchClickLog]) -> float:
        """MRR from click data (first click position)."""
        if not logs:
            return 0.0
        rr_sum = 0.0
        for log in logs:
            if log.clicked_results:
                first_click = log.clicked_results[0]
                try:
                    rank = log.results_shown.index(first_click) + 1
                    rr_sum += 1.0 / rank
                except ValueError:
                    pass
        return rr_sum / len(logs)

    @staticmethod
    def abandonment_rate(logs: list[SearchClickLog]) -> float:
        """Fraction of queries where user didn't click and didn't refine."""
        if not logs:
            return 0.0
        abandoned = sum(
            1 for log in logs
            if not log.clicked_results and log.result_count > 0
        )
        return abandoned / len(logs)

    @staticmethod
    def compare_variants(
        control_logs: list[SearchClickLog],
        treatment_logs: list[SearchClickLog],
    ) -> dict:
        """Compare metrics between A/B variants."""
        return {
            "control": {
                "queries": len(control_logs),
                "ctr": OnlineMetrics.click_through_rate(control_logs),
                "zero_result_rate": OnlineMetrics.zero_result_rate(control_logs),
                "mrr": OnlineMetrics.mean_reciprocal_rank_from_clicks(control_logs),
                "abandonment": OnlineMetrics.abandonment_rate(control_logs),
            },
            "treatment": {
                "queries": len(treatment_logs),
                "ctr": OnlineMetrics.click_through_rate(treatment_logs),
                "zero_result_rate": OnlineMetrics.zero_result_rate(treatment_logs),
                "mrr": OnlineMetrics.mean_reciprocal_rank_from_clicks(treatment_logs),
                "abandonment": OnlineMetrics.abandonment_rate(treatment_logs),
            },
        }
```

| Metric | Formula | Measures | Range |
|--------|---------|----------|-------|
| Precision@K | relevant_in_top_K / K | Fraction of results that are relevant | 0 to 1 |
| Recall@K | relevant_in_top_K / total_relevant | Fraction of relevant docs found | 0 to 1 |
| MAP | mean of AP across queries | Average precision over all recall levels | 0 to 1 |
| DCG@K | sum(rel_i / log2(i+1)) | Gain discounted by position | 0 to inf |
| NDCG@K | DCG@K / IDCG@K | Normalized ranking quality | 0 to 1 |
| MRR | mean(1/rank_first_relevant) | How quickly the first relevant result appears | 0 to 1 |
| CTR | queries_with_click / total_queries | User engagement with results | 0 to 1 |

Key patterns:
1. Use NDCG@10 as the primary offline metric — it handles graded relevance and position bias
2. Combine offline (NDCG, MAP) and online (CTR, abandonment) metrics for complete evaluation
3. Build a judged query set (200+ queries) with human relevance labels for offline evaluation
4. A/B test ranking changes with deterministic user-to-variant assignment (hash-based)
5. Track zero-result rate and abandonment rate as search quality health metrics'''
    ),
]
