PAIRS = [
    ("projects/search-engine", r'''<think>
An inverted index maps tokens to document IDs, enabling fast full-text search.
I need to implement tokenization, index building, and query evaluation.
TF-IDF scoring will rank results by relevance.
</think>
Build a search engine with an inverted index, tokenization, and TF-IDF scoring.''', r'''import math
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class Document:
    """A searchable document."""
    doc_id: str
    content: str
    title: str = ""
    metadata: Dict = field(default_factory=dict)


class Tokenizer:
    """Tokenizes text into searchable terms."""

    STOP_WORDS = {
        "a", "an", "the", "is", "it", "in", "to", "of", "and", "or",
        "for", "on", "at", "by", "with", "from", "that", "this", "are",
        "was", "be", "has", "have", "had", "not", "but", "what", "all",
    }

    def tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z0-9]+", text)
        return [t for t in tokens if t not in self.STOP_WORDS and len(t) > 1]

    def tokenize_with_positions(self, text: str) -> List[Tuple[str, int]]:
        text = text.lower()
        result = []
        for i, match in enumerate(re.finditer(r"[a-z0-9]+", text)):
            token = match.group()
            if token not in self.STOP_WORDS and len(token) > 1:
                result.append((token, i))
        return result


class InvertedIndex:
    """Inverted index mapping terms to document postings."""

    def __init__(self):
        self._index: Dict[str, Dict[str, List[int]]] = defaultdict(dict)
        self._doc_lengths: Dict[str, int] = {}
        self._doc_count = 0
        self._tokenizer = Tokenizer()

    def add_document(self, doc: Document) -> None:
        """Index a document."""
        tokens = self._tokenizer.tokenize_with_positions(doc.content)
        if doc.title:
            title_tokens = self._tokenizer.tokenize_with_positions(doc.title)
            tokens.extend(title_tokens)

        self._doc_lengths[doc.doc_id] = len(tokens)
        self._doc_count += 1

        for token, position in tokens:
            if doc.doc_id not in self._index[token]:
                self._index[token][doc.doc_id] = []
            self._index[token][doc.doc_id].append(position)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the index."""
        for term in list(self._index.keys()):
            self._index[term].pop(doc_id, None)
            if not self._index[term]:
                del self._index[term]
        self._doc_lengths.pop(doc_id, None)
        self._doc_count -= 1

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Search and return (doc_id, score) tuples ranked by TF-IDF."""
        query_tokens = self._tokenizer.tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[str, float] = defaultdict(float)

        for token in query_tokens:
            postings = self._index.get(token, {})
            if not postings:
                continue

            # IDF: log(N / df)
            df = len(postings)
            idf = math.log(self._doc_count / df) if df > 0 else 0

            for doc_id, positions in postings.items():
                # TF: frequency / document length
                tf = len(positions) / max(1, self._doc_lengths.get(doc_id, 1))
                scores[doc_id] += tf * idf

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    def get_term_frequency(self, term: str) -> int:
        """Get the number of documents containing a term."""
        return len(self._index.get(term, {}))

    @property
    def stats(self) -> dict:
        return {
            "documents": self._doc_count,
            "unique_terms": len(self._index),
            "avg_doc_length": sum(self._doc_lengths.values()) / max(1, self._doc_count),
        }
'''),
    ("projects/search-engine", r'''Implement fuzzy matching for the search engine using edit distance and n-gram similarity.''', r'''from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def damerau_levenshtein(s1: str, s2: str) -> int:
    """Edit distance with transposition support."""
    len1, len2 = len(s1), len(s2)
    d = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    for i in range(len1 + 1):
        d[i][0] = i
    for j in range(len2 + 1):
        d[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )
            if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)

    return d[len1][len2]


class NGramIndex:
    """Index based on character n-grams for fuzzy matching."""

    def __init__(self, n: int = 3):
        self._n = n
        self._index: Dict[str, Set[str]] = defaultdict(set)
        self._terms: Set[str] = set()

    def _get_ngrams(self, term: str) -> List[str]:
        """Generate n-grams for a term, including padding."""
        padded = "$" * (self._n - 1) + term + "$" * (self._n - 1)
        return [padded[i:i + self._n] for i in range(len(padded) - self._n + 1)]

    def add_term(self, term: str) -> None:
        """Add a term to the n-gram index."""
        self._terms.add(term)
        for ngram in self._get_ngrams(term):
            self._index[ngram].add(term)

    def add_terms(self, terms: List[str]) -> None:
        for term in terms:
            self.add_term(term)

    def find_similar(self, query: str, threshold: float = 0.3, limit: int = 10) -> List[Tuple[str, float]]:
        """Find terms similar to the query using n-gram overlap."""
        query_ngrams = set(self._get_ngrams(query))
        candidates: Dict[str, int] = defaultdict(int)

        for ngram in query_ngrams:
            for term in self._index.get(ngram, set()):
                candidates[term] += 1

        results = []
        for term, shared_count in candidates.items():
            term_ngrams = set(self._get_ngrams(term))
            union_size = len(query_ngrams | term_ngrams)
            similarity = shared_count / union_size if union_size > 0 else 0

            if similarity >= threshold:
                results.append((term, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]


class FuzzySearcher:
    """Combines exact matching with fuzzy matching for search suggestions."""

    def __init__(self, max_edit_distance: int = 2):
        self._max_distance = max_edit_distance
        self._ngram_index = NGramIndex(n=3)
        self._terms: Dict[str, int] = {}  # term -> document frequency

    def build(self, terms: List[str]) -> None:
        """Build the fuzzy search index from a list of terms."""
        for term in terms:
            term_lower = term.lower()
            self._terms[term_lower] = self._terms.get(term_lower, 0) + 1
            self._ngram_index.add_term(term_lower)

    def suggest(self, query: str, limit: int = 5) -> List[dict]:
        """Get spelling suggestions for a query term."""
        query_lower = query.lower()

        # Exact match
        if query_lower in self._terms:
            return [{"term": query_lower, "distance": 0, "score": 1.0}]

        # N-gram candidates
        candidates = self._ngram_index.find_similar(query_lower, threshold=0.2, limit=50)

        results = []
        for term, ngram_sim in candidates:
            dist = damerau_levenshtein(query_lower, term)
            if dist <= self._max_distance:
                # Combine n-gram similarity with edit distance
                score = ngram_sim * (1.0 / (1.0 + dist))
                results.append({
                    "term": term,
                    "distance": dist,
                    "score": score,
                    "frequency": self._terms.get(term, 0),
                })

        results.sort(key=lambda x: (-x["score"], -x["frequency"]))
        return results[:limit]

    def correct_query(self, query: str) -> str:
        """Auto-correct a query by replacing misspelled terms."""
        terms = query.lower().split()
        corrected = []
        for term in terms:
            if term in self._terms:
                corrected.append(term)
            else:
                suggestions = self.suggest(term, limit=1)
                if suggestions and suggestions[0]["distance"] <= 1:
                    corrected.append(suggestions[0]["term"])
                else:
                    corrected.append(term)
        return " ".join(corrected)
'''),
    ("projects/search-engine", r'''Implement faceted search with category filtering, aggregations, and range filters.''', r'''from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple


class Facet:
    """Represents a facet for filtering and aggregation."""

    def __init__(self, name: str, field_type: str = "keyword"):
        self.name = name
        self.field_type = field_type  # keyword, numeric, date
        self._values: Dict[str, Set[str]] = defaultdict(set)  # value -> doc_ids
        self._doc_values: Dict[str, Any] = {}  # doc_id -> value

    def add(self, doc_id: str, value: Any) -> None:
        """Index a facet value for a document."""
        str_value = str(value)
        self._values[str_value].add(doc_id)
        self._doc_values[doc_id] = value

    def get_counts(self, doc_ids: Optional[Set[str]] = None) -> List[dict]:
        """Get facet value counts, optionally filtered to a doc set."""
        counts = []
        for value, ids in self._values.items():
            if doc_ids is not None:
                count = len(ids & doc_ids)
            else:
                count = len(ids)
            if count > 0:
                counts.append({"value": value, "count": count})
        counts.sort(key=lambda x: x["count"], reverse=True)
        return counts

    def filter(self, values: List[str]) -> Set[str]:
        """Get doc IDs matching any of the given values."""
        result = set()
        for value in values:
            result.update(self._values.get(value, set()))
        return result

    def filter_range(self, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Set[str]:
        """Filter by numeric range."""
        result = set()
        for doc_id, value in self._doc_values.items():
            try:
                num_val = float(value)
                if min_val is not None and num_val < min_val:
                    continue
                if max_val is not None and num_val > max_val:
                    continue
                result.add(doc_id)
            except (ValueError, TypeError):
                continue
        return result


class FacetedSearch:
    """Search engine with faceted filtering and aggregations."""

    def __init__(self, index):
        self._index = index
        self._facets: Dict[str, Facet] = {}
        self._documents: Dict[str, dict] = {}

    def define_facet(self, name: str, field_type: str = "keyword") -> None:
        """Define a new facet."""
        self._facets[name] = Facet(name, field_type)

    def index_document(self, doc_id: str, content: str, facet_values: Dict[str, Any], metadata: Optional[dict] = None) -> None:
        """Index a document with facet values."""
        from . import Document
        doc = Document(doc_id=doc_id, content=content, metadata=metadata or {})
        self._index.add_document(doc)

        self._documents[doc_id] = {
            "doc_id": doc_id,
            "content": content[:200],
            "facets": facet_values,
            **(metadata or {}),
        }

        for facet_name, value in facet_values.items():
            if facet_name in self._facets:
                if isinstance(value, list):
                    for v in value:
                        self._facets[facet_name].add(doc_id, v)
                else:
                    self._facets[facet_name].add(doc_id, value)

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        include_facets: bool = True,
    ) -> dict:
        """Search with optional facet filters."""
        # Get initial results from text search
        text_results = self._index.search(query, limit=1000)
        result_ids = set(doc_id for doc_id, _ in text_results)
        scores = {doc_id: score for doc_id, score in text_results}

        # Apply facet filters
        if filters:
            for facet_name, filter_value in filters.items():
                facet = self._facets.get(facet_name)
                if not facet:
                    continue

                if isinstance(filter_value, dict):
                    # Range filter
                    matching = facet.filter_range(
                        min_val=filter_value.get("min"),
                        max_val=filter_value.get("max"),
                    )
                elif isinstance(filter_value, list):
                    matching = facet.filter(filter_value)
                else:
                    matching = facet.filter([str(filter_value)])

                result_ids &= matching

        # Sort by score
        ranked = sorted(result_ids, key=lambda d: scores.get(d, 0), reverse=True)
        total = len(ranked)

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        page_ids = ranked[start:end]

        # Build results
        hits = []
        for doc_id in page_ids:
            doc = self._documents.get(doc_id, {})
            hits.append({
                **doc,
                "score": scores.get(doc_id, 0),
            })

        response = {
            "query": query,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "hits": hits,
        }

        # Include facet counts for the current result set
        if include_facets:
            response["facets"] = {}
            for name, facet in self._facets.items():
                response["facets"][name] = facet.get_counts(result_ids)

        return response
'''),
    ("projects/search-engine", r'''<think>
Search result pagination needs to handle large result sets efficiently.
I should implement cursor-based pagination (for real-time data) and
offset-based pagination (for static results), plus highlight support.
</think>
Implement search result pagination with cursor and offset modes, and search term highlighting.''', r'''import re
from typing import Any, Dict, List, Optional, Tuple


class SearchHighlighter:
    """Highlights search terms in document text."""

    def __init__(self, pre_tag: str = "<mark>", post_tag: str = "</mark>"):
        self._pre = pre_tag
        self._post = post_tag

    def highlight(self, text: str, query_terms: List[str], max_length: int = 300) -> str:
        """Highlight query terms in text and return a snippet."""
        if not query_terms:
            return text[:max_length]

        text_lower = text.lower()
        positions = []

        for term in query_terms:
            term_lower = term.lower()
            start = 0
            while True:
                idx = text_lower.find(term_lower, start)
                if idx == -1:
                    break
                positions.append((idx, idx + len(term)))
                start = idx + 1

        if not positions:
            return text[:max_length]

        # Find the best snippet window
        positions.sort()
        best_start = max(0, positions[0][0] - 50)
        best_end = min(len(text), best_start + max_length)

        snippet = text[best_start:best_end]
        if best_start > 0:
            snippet = "..." + snippet
        if best_end < len(text):
            snippet = snippet + "..."

        # Apply highlighting (work backwards to preserve positions)
        # Re-find terms in the snippet
        for term in query_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            snippet = pattern.sub(
                lambda m: f"{self._pre}{m.group()}{self._post}",
                snippet,
            )

        return snippet

    def highlight_field(self, value: str, query_terms: List[str]) -> str:
        """Highlight all occurrences in a field value."""
        result = value
        for term in query_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            result = pattern.sub(
                lambda m: f"{self._pre}{m.group()}{self._post}",
                result,
            )
        return result


class Paginator:
    """Handles search result pagination with multiple strategies."""

    def __init__(self, default_page_size: int = 20, max_page_size: int = 100):
        self._default_size = default_page_size
        self._max_size = max_page_size

    def paginate_offset(
        self,
        results: List[Any],
        page: int = 1,
        page_size: Optional[int] = None,
    ) -> dict:
        """Offset-based pagination."""
        size = min(page_size or self._default_size, self._max_size)
        total = len(results)
        total_pages = max(1, (total + size - 1) // size)
        page = max(1, min(page, total_pages))

        start = (page - 1) * size
        end = start + size
        items = results[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    def paginate_cursor(
        self,
        results: List[dict],
        cursor: Optional[str] = None,
        page_size: Optional[int] = None,
        sort_key: str = "score",
    ) -> dict:
        """Cursor-based pagination for stable ordering."""
        import base64
        import json

        size = min(page_size or self._default_size, self._max_size)

        # Decode cursor
        start_idx = 0
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode())
                start_idx = cursor_data.get("offset", 0)
            except Exception:
                start_idx = 0

        # Get page
        end_idx = start_idx + size
        items = results[start_idx:end_idx]
        has_next = end_idx < len(results)

        # Encode next cursor
        next_cursor = None
        if has_next:
            cursor_data = {"offset": end_idx}
            next_cursor = base64.b64encode(
                json.dumps(cursor_data).encode()
            ).decode()

        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_next": has_next,
            "page_size": size,
        }


class SearchResultFormatter:
    """Formats search results with highlighting and metadata."""

    def __init__(self):
        self._highlighter = SearchHighlighter()
        self._paginator = Paginator()

    def format_results(
        self,
        hits: List[Tuple[str, float]],
        documents: Dict[str, dict],
        query: str,
        page: int = 1,
        page_size: int = 20,
        highlight: bool = True,
    ) -> dict:
        """Format search results with pagination and highlighting."""
        query_terms = query.lower().split()

        formatted_hits = []
        for doc_id, score in hits:
            doc = documents.get(doc_id, {})
            hit = {
                "doc_id": doc_id,
                "score": round(score, 4),
                "title": doc.get("title", ""),
                "metadata": doc.get("metadata", {}),
            }

            content = doc.get("content", "")
            if highlight and content:
                hit["snippet"] = self._highlighter.highlight(content, query_terms)
                if doc.get("title"):
                    hit["title"] = self._highlighter.highlight_field(
                        doc["title"], query_terms
                    )
            else:
                hit["snippet"] = content[:200]

            formatted_hits.append(hit)

        paginated = self._paginator.paginate_offset(formatted_hits, page, page_size)

        return {
            "query": query,
            "total_results": paginated["total"],
            "page": paginated["page"],
            "page_size": paginated["page_size"],
            "total_pages": paginated["total_pages"],
            "results": paginated["items"],
            "has_next": paginated["has_next"],
            "has_prev": paginated["has_prev"],
        }
'''),
    ("projects/search-engine", r'''Build the search engine query parser with boolean operators, phrase search, and field-specific queries.''', r'''import re
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
from enum import Enum


class QueryType(Enum):
    TERM = "term"
    PHRASE = "phrase"
    AND = "and"
    OR = "or"
    NOT = "not"
    FIELD = "field"
    WILDCARD = "wildcard"


@dataclass
class QueryNode:
    """A node in the parsed query tree."""
    query_type: QueryType
    value: str = ""
    field: str = ""
    children: List["QueryNode"] = None

    def __post_init__(self):
        if self.children is None:
            self.children = []


class QueryParser:
    """Parses search queries into a query tree with boolean logic.

    Supported syntax:
    - Simple terms: hello world (implicit AND)
    - Phrase search: "hello world"
    - Boolean: hello AND world, hello OR world, NOT hello
    - Field search: title:hello, author:"John Doe"
    - Wildcard: hel*, h?llo
    - Grouping: (hello OR world) AND python
    """

    def parse(self, query: str) -> QueryNode:
        """Parse a query string into a QueryNode tree."""
        tokens = self._tokenize(query)
        if not tokens:
            return QueryNode(QueryType.TERM, value="")
        node, _ = self._parse_or(tokens, 0)
        return node

    def _tokenize(self, query: str) -> List[str]:
        """Tokenize query into meaningful parts."""
        tokens = []
        i = 0
        while i < len(query):
            c = query[i]

            if c in (" ", "\t"):
                i += 1
                continue

            if c == '"':
                # Quoted phrase
                end = query.find('"', i + 1)
                if end == -1:
                    end = len(query)
                tokens.append(query[i:end + 1])
                i = end + 1

            elif c in ("(", ")"):
                tokens.append(c)
                i += 1

            elif c == "-" and (not tokens or tokens[-1] in ("(", "AND", "OR")):
                tokens.append("NOT")
                i += 1

            else:
                # Word or field:value
                end = i
                while end < len(query) and query[end] not in (" ", "\t", "(", ")"):
                    end += 1
                word = query[i:end]
                tokens.append(word)
                i = end

        return tokens

    def _parse_or(self, tokens: List[str], pos: int) -> Tuple[QueryNode, int]:
        """Parse OR expressions."""
        left, pos = self._parse_and(tokens, pos)

        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1  # skip OR
            right, pos = self._parse_and(tokens, pos)
            left = QueryNode(QueryType.OR, children=[left, right])

        return left, pos

    def _parse_and(self, tokens: List[str], pos: int) -> Tuple[QueryNode, int]:
        """Parse AND expressions (including implicit AND)."""
        left, pos = self._parse_not(tokens, pos)

        while pos < len(tokens) and tokens[pos] not in (")", "OR"):
            if tokens[pos].upper() == "AND":
                pos += 1  # skip AND
            right, pos = self._parse_not(tokens, pos)
            left = QueryNode(QueryType.AND, children=[left, right])

        return left, pos

    def _parse_not(self, tokens: List[str], pos: int) -> Tuple[QueryNode, int]:
        """Parse NOT expressions."""
        if pos < len(tokens) and tokens[pos].upper() == "NOT":
            pos += 1
            child, pos = self._parse_primary(tokens, pos)
            return QueryNode(QueryType.NOT, children=[child]), pos
        return self._parse_primary(tokens, pos)

    def _parse_primary(self, tokens: List[str], pos: int) -> Tuple[QueryNode, int]:
        """Parse primary expressions (terms, phrases, groups)."""
        if pos >= len(tokens):
            return QueryNode(QueryType.TERM, value=""), pos

        token = tokens[pos]

        if token == "(":
            # Grouped expression
            node, pos = self._parse_or(tokens, pos + 1)
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return node, pos

        if token.startswith('"') and token.endswith('"'):
            # Phrase query
            phrase = token[1:-1]
            return QueryNode(QueryType.PHRASE, value=phrase), pos + 1

        if ":" in token and not token.startswith(":"):
            # Field query
            field, value = token.split(":", 1)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return QueryNode(QueryType.FIELD, value=value, field=field), pos + 1

        if "*" in token or "?" in token:
            # Wildcard query
            return QueryNode(QueryType.WILDCARD, value=token), pos + 1

        # Simple term
        return QueryNode(QueryType.TERM, value=token.lower()), pos + 1


class QueryEvaluator:
    """Evaluates parsed queries against the inverted index."""

    def __init__(self, index):
        self._index = index

    def evaluate(self, node: QueryNode) -> Set[str]:
        """Evaluate a query tree and return matching document IDs."""
        if node.query_type == QueryType.TERM:
            return self._eval_term(node.value)
        elif node.query_type == QueryType.PHRASE:
            return self._eval_phrase(node.value)
        elif node.query_type == QueryType.AND:
            sets = [self.evaluate(child) for child in node.children]
            result = sets[0]
            for s in sets[1:]:
                result = result & s
            return result
        elif node.query_type == QueryType.OR:
            sets = [self.evaluate(child) for child in node.children]
            result = set()
            for s in sets:
                result = result | s
            return result
        elif node.query_type == QueryType.NOT:
            child_results = self.evaluate(node.children[0])
            all_docs = set(self._index._doc_lengths.keys())
            return all_docs - child_results
        elif node.query_type == QueryType.WILDCARD:
            return self._eval_wildcard(node.value)
        elif node.query_type == QueryType.FIELD:
            return self._eval_term(node.value)
        return set()

    def _eval_term(self, term: str) -> Set[str]:
        postings = self._index._index.get(term, {})
        return set(postings.keys())

    def _eval_phrase(self, phrase: str) -> Set[str]:
        terms = phrase.lower().split()
        if not terms:
            return set()

        # Get docs containing all terms
        doc_sets = [set(self._index._index.get(t, {}).keys()) for t in terms]
        if not doc_sets:
            return set()
        candidates = doc_sets[0]
        for s in doc_sets[1:]:
            candidates = candidates & s

        # Check position adjacency
        results = set()
        for doc_id in candidates:
            positions = [self._index._index[t].get(doc_id, []) for t in terms]
            for start_pos in positions[0]:
                match = True
                for offset, term_positions in enumerate(positions[1:], 1):
                    if (start_pos + offset) not in term_positions:
                        match = False
                        break
                if match:
                    results.add(doc_id)
                    break

        return results

    def _eval_wildcard(self, pattern: str) -> Set[str]:
        regex = re.compile(
            "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"
        )
        results = set()
        for term in self._index._index:
            if regex.match(term):
                results.update(self._index._index[term].keys())
        return results
'''),
]
