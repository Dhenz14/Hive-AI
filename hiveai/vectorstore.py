import logging
import re
import numpy as np
from sqlalchemy import text as sa_text
from hiveai.config import DB_BACKEND

logger = logging.getLogger(__name__)

# Stop words for BM25 keyword scoring (common English words with no search signal)
_BM25_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "this", "that", "these",
    "those", "what", "which", "who", "whom", "it", "its", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "they", "them", "his", "her",
}


def vector_search(db, query_embedding, limit=12, max_distance=0.8, book_id_filter=None):
    if DB_BACKEND == "postgresql":
        return _pg_vector_search(db, query_embedding, limit, max_distance, book_id_filter)
    else:
        return _sqlite_vector_search(db, query_embedding, limit, max_distance, book_id_filter)


def vector_search_grouped(db, query_embedding, max_distance=0.5, min_count=3):
    if DB_BACKEND == "postgresql":
        return _pg_vector_search_grouped(db, query_embedding, max_distance, min_count)
    else:
        return _sqlite_vector_search_grouped(db, query_embedding, max_distance, min_count)


def _pg_vector_search(db, query_embedding, limit, max_distance, book_id_filter):
    params = {"query_vec": str(query_embedding)}
    
    where_clauses = ["bs.embedding IS NOT NULL"]
    if book_id_filter:
        where_clauses.append("bs.book_id = ANY(:book_ids)")
        params["book_ids"] = book_id_filter
    
    where_sql = " AND ".join(where_clauses)
    
    results = db.execute(sa_text(f"""
        SELECT bs.id, bs.header, bs.content, gb.title as book_title,
               gb.id as book_id,
               bs.embedding <=> cast(:query_vec as vector) as distance
        FROM book_sections bs
        JOIN golden_books gb ON bs.book_id = gb.id
        WHERE {where_sql}
        ORDER BY bs.embedding <=> cast(:query_vec as vector)
        LIMIT :lim
    """), {**params, "lim": limit})
    
    rows = []
    for row in results:
        if row.distance < max_distance:
            rows.append({
                "id": row.id,
                "book_title": row.book_title,
                "header": row.header,
                "content": row.content,
                "book_id": row.book_id,
                "distance": row.distance,
            })
    return rows


def _pg_vector_search_grouped(db, query_embedding, max_distance, min_count):
    results = db.execute(sa_text("""
        SELECT bs.book_id, COUNT(*) as match_count
        FROM book_sections bs
        WHERE bs.embedding IS NOT NULL
          AND bs.embedding <=> cast(:query_vec as vector) < :max_dist
        GROUP BY bs.book_id
        HAVING COUNT(*) >= :min_cnt
        ORDER BY match_count DESC
    """), {"query_vec": str(query_embedding), "max_dist": max_distance, "min_cnt": min_count})
    
    return [{"book_id": row.book_id, "match_count": row.match_count} for row in results]


def cosine_distance(a, b):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - float(np.dot(a, b) / (norm_a * norm_b))


def _sqlite_vector_search(db, query_embedding, limit, max_distance, book_id_filter):
    from hiveai.models import BookSection, GoldenBook
    import json
    
    query = db.query(BookSection, GoldenBook).join(
        GoldenBook, BookSection.book_id == GoldenBook.id
    ).filter(BookSection.embedding_json.isnot(None))
    
    if book_id_filter:
        query = query.filter(BookSection.book_id.in_(book_id_filter))
    
    sections = query.all()
    
    scored = []
    for section, book in sections:
        try:
            emb = json.loads(section.embedding_json) if isinstance(section.embedding_json, str) else section.embedding_json
            if emb is None:
                continue
            dist = cosine_distance(query_embedding, emb)
            if dist < max_distance:
                scored.append({
                    "id": section.id,
                    "book_title": book.title,
                    "header": section.header,
                    "content": section.content,
                    "book_id": book.id,
                    "distance": dist,
                })
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug(f"Skipping section {section.id}: {e}")
            continue

    scored.sort(key=lambda x: x["distance"])
    return scored[:limit]


def _sqlite_vector_search_grouped(db, query_embedding, max_distance, min_count):
    from hiveai.models import BookSection
    import json
    from collections import Counter
    
    sections = db.query(BookSection).filter(BookSection.embedding_json.isnot(None)).all()
    
    book_matches = Counter()
    for section in sections:
        try:
            emb = json.loads(section.embedding_json) if isinstance(section.embedding_json, str) else section.embedding_json
            if emb is None:
                continue
            dist = cosine_distance(query_embedding, emb)
            if dist < max_distance:
                book_matches[section.book_id] += 1
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug(f"Skipping section {section.id}: {e}")
            continue

    results = []
    for book_id, count in book_matches.most_common():
        if count >= min_count:
            results.append({"book_id": book_id, "match_count": count})

    return results


# ---------------------------------------------------------------------------
# Hybrid BM25 + Vector Search — fuses keyword matching with semantic similarity
# for better recall on queries with rare named entities or exact terms.
# ---------------------------------------------------------------------------

def _bm25_score_section(query_terms: list[str], content: str, header: str = "") -> float:
    """
    Simple BM25-inspired keyword scoring for a section.
    Not a full BM25 implementation (no IDF corpus stats) but captures
    the core signal: term frequency with saturation.
    """
    if not query_terms or not content:
        return 0.0

    text = (header + " " + content).lower()
    words = text.split()
    doc_len = len(words)
    if doc_len == 0:
        return 0.0

    # BM25 parameters (tuned for short knowledge sections)
    k1 = 1.2  # term frequency saturation
    b = 0.75  # length normalization
    avg_dl = 200  # approximate average section length in words

    score = 0.0
    for term in query_terms:
        tf = text.count(term)
        if tf == 0:
            continue
        # BM25 term score with saturation
        norm_tf = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_dl))
        # Boost exact header matches (headers are more important)
        if term in header.lower():
            norm_tf *= 2.0
        score += norm_tf

    return score


def _load_section_keywords(db, section_ids: list[int]) -> dict[int, list[str]]:
    """Load stored keywords for a batch of section IDs. Returns {id: [keywords]}."""
    if not section_ids:
        return {}
    from hiveai.models import BookSection
    import json
    rows = db.query(BookSection.id, BookSection.keywords_json).filter(
        BookSection.id.in_(section_ids),
        BookSection.keywords_json.isnot(None),
    ).all()
    result = {}
    for sid, kw_json in rows:
        try:
            parsed = json.loads(kw_json) if kw_json else []
            # Support both plain array and structured format (solved examples)
            if isinstance(parsed, dict):
                result[sid] = parsed.get("keywords", [])
            else:
                result[sid] = parsed
        except (json.JSONDecodeError, TypeError):
            result[sid] = []
    return result


def _load_section_metadata(db, section_ids: list[int]) -> dict[int, dict]:
    """Load full keywords_json metadata for sections. Returns {id: parsed_dict_or_empty}."""
    if not section_ids:
        return {}
    from hiveai.models import BookSection
    import json
    rows = db.query(BookSection.id, BookSection.keywords_json).filter(
        BookSection.id.in_(section_ids),
        BookSection.keywords_json.isnot(None),
    ).all()
    result = {}
    for sid, kw_json in rows:
        try:
            parsed = json.loads(kw_json) if kw_json else {}
            result[sid] = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            result[sid] = {}
    return result


def hybrid_search(db, query: str, query_embedding, limit: int = 12,
                  max_distance: float = 0.8, alpha: float = 0.6,
                  book_id_filter=None) -> list[dict]:
    """
    Fuse vector similarity and keyword matching for better recall.

    Args:
        db: SQLAlchemy session
        query: Raw query text (for keyword matching)
        query_embedding: Pre-computed embedding vector
        limit: Max results to return
        max_distance: Max cosine distance for vector results
        alpha: Weight for vector score (1-alpha = keyword weight).
               Default 0.6 favors semantic but gives keywords meaningful weight.
        book_id_filter: Optional list of book IDs to restrict search

    Returns:
        List of section dicts sorted by fused score, best first.
    """
    # Step 1: Get vector results (retrieve more than needed for fusion)
    vec_results = vector_search(db, query_embedding, limit=limit * 2,
                                max_distance=max_distance, book_id_filter=book_id_filter)

    # Step 2: Extract query terms for BM25
    query_terms = [
        w.lower() for w in re.split(r'\W+', query)
        if len(w) > 2 and w.lower() not in _BM25_STOP_WORDS
    ]

    if not query_terms:
        # No useful keywords — fall back to pure vector search
        return vec_results[:limit]

    # Step 3: Score each vector result with BM25
    # Normalize vector distances to 0-1 similarity scores
    if vec_results:
        max_dist = max(r["distance"] for r in vec_results) or 1.0
        for r in vec_results:
            r["vec_score"] = 1.0 - (r["distance"] / max(max_dist, 0.001))
    else:
        return []

    # Load stored section keywords for keyword-overlap bonus
    section_ids = [r["id"] for r in vec_results]
    stored_keywords = _load_section_keywords(db, section_ids)
    query_terms_set = set(query_terms)

    # BM25 scores + stored keyword bonus
    bm25_scores = []
    for r in vec_results:
        bm25 = _bm25_score_section(query_terms, r.get("content", ""), r.get("header", ""))

        # Bonus from stored keywords: overlap between query terms and section keywords
        sec_kw = stored_keywords.get(r["id"], [])
        if sec_kw and query_terms_set:
            overlap = len(query_terms_set & set(sec_kw))
            keyword_bonus = overlap / max(len(query_terms_set), 1) * 0.3
            bm25 += keyword_bonus

        bm25_scores.append(bm25)

    # Normalize BM25 scores to 0-1
    max_bm25 = max(bm25_scores) if bm25_scores else 1.0
    if max_bm25 > 0:
        for i, r in enumerate(vec_results):
            r["bm25_score"] = bm25_scores[i] / max_bm25
    else:
        for r in vec_results:
            r["bm25_score"] = 0.0

    # Step 4: Fuse scores + solved-example bonus for code queries
    # Detect if query looks like a code task (code keywords, function names, etc.)
    _code_indicators = {"function", "implement", "write", "code", "class", "method",
                        "algorithm", "error", "bug", "fix", "debug", "refactor",
                        "python", "javascript", "typescript", "rust", "cpp", "golang"}
    _query_lower = query.lower()
    _is_code_query = bool(query_terms_set & _code_indicators) or \
                     any(c in _query_lower for c in ['()', '{}', '[]', 'def ', 'fn ', 'func '])

    # Load metadata to identify solved examples
    section_metadata = _load_section_metadata(db, section_ids) if _is_code_query else {}

    for r in vec_results:
        r["hybrid_score"] = alpha * r["vec_score"] + (1 - alpha) * r["bm25_score"]

        # Solved-example rank bonus: when similarity is close, prefer proven solutions
        # Only for code queries — docs/general chat should prefer golden book content
        if _is_code_query:
            meta = section_metadata.get(r["id"], {})
            if meta.get("source_type") == "solved_example":
                # Base bonus (0.05) — enough to break ties, not enough to override relevance
                bonus = 0.05
                # Lexical title boost: if query terms overlap with the solved example header,
                # add a small additional boost (targets paraphrase recall weakness from Gate 11)
                header_text = r.get("header", "")
                if header_text and query_terms_set:
                    header_terms = {w.lower() for w in re.split(r'\W+', header_text) if len(w) > 2}
                    title_overlap = len(query_terms_set & header_terms)
                    if title_overlap >= 2:
                        bonus += min(title_overlap * 0.02, 0.06)  # cap at +0.06
                r["hybrid_score"] += bonus
                r["is_solved_example"] = True

    # Step 5: Re-sort by fused score and return top results
    vec_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

    # Step 6: Quality filtering — drop weak/duplicate chunks
    min_score = 0.15  # below this, chunk is noise
    max_per_book = 3  # prevent one book from dominating results
    book_counts: dict[int, int] = {}
    filtered = []
    for r in vec_results:
        if r["hybrid_score"] < min_score:
            continue
        bid = r.get("book_id")
        if bid is not None:
            if book_counts.get(bid, 0) >= max_per_book:
                continue
            book_counts[bid] = book_counts.get(bid, 0) + 1
        filtered.append(r)
        if len(filtered) >= limit:
            break

    # Keep scores in output for trace/observability (budget_context uses them)
    for r in filtered:
        r["relevance_score"] = round(r.get("hybrid_score", 0), 3)
        r.pop("vec_score", None)
        r.pop("bm25_score", None)
        r.pop("hybrid_score", None)

    return filtered
