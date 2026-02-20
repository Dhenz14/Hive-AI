import logging
import numpy as np
from sqlalchemy import text as sa_text
from hiveai.config import DB_BACKEND

logger = logging.getLogger(__name__)


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


def _cosine_distance(a, b):
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
            dist = _cosine_distance(query_embedding, emb)
            if dist < max_distance:
                scored.append({
                    "id": section.id,
                    "book_title": book.title,
                    "header": section.header,
                    "content": section.content,
                    "book_id": book.id,
                    "distance": dist,
                })
        except Exception:
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
            dist = _cosine_distance(query_embedding, emb)
            if dist < max_distance:
                book_matches[section.book_id] += 1
        except Exception:
            continue
    
    results = []
    for book_id, count in book_matches.most_common():
        if count >= min_count:
            results.append({"book_id": book_id, "match_count": count})
    
    return results
