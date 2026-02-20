import re
import logging
import threading
from hiveai.models import SessionLocal, Job, GoldenBook, BookSection, Community
from hiveai.llm.client import embed_text, rerank_sections

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "about", "what", "which",
    "who", "whom", "this", "that", "these", "those", "am", "it", "its",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she",
    "her", "they", "them", "their", "tell", "explain", "describe", "much",
}


def split_book_into_sections(book):
    from hiveai.pipeline.writer import split_book_content
    sections = split_book_content(book)
    for section in sections:
        section["book_title"] = book.title
    return sections


def score_section(section, query_words):
    text = (section["header"] + " " + section["content"]).lower()
    score = 0

    for word in query_words:
        header_lower = section["header"].lower()
        if word in header_lower:
            score += 5
        count = text.count(word)
        if count > 0:
            score += min(count, 5)

    for i in range(len(query_words) - 1):
        bigram = query_words[i] + " " + query_words[i + 1]
        if bigram in text:
            score += 8

    return score


def keyword_search_sections(question, db, history=None):
    books = db.query(GoldenBook).all()
    if not books:
        return [], [], []

    query_words = [
        w for w in question.lower().split()
        if len(w) > 2 and w not in STOP_WORDS
    ]

    if history:
        for h in history[-4:]:
            content = h.get("content", "").lower()
            for w in content.split():
                if len(w) > 3 and w not in STOP_WORDS and w not in query_words:
                    query_words.append(w)
        query_words = list(dict.fromkeys(query_words))

    if not query_words:
        query_words = [w for w in question.lower().split() if len(w) > 1]

    all_sections = []
    for book in books:
        all_sections.extend(split_book_into_sections(book))

    scored = []
    for section in all_sections:
        s = score_section(section, query_words)
        if s > 0:
            scored.append((section, s))

    scored.sort(key=lambda x: x[1], reverse=True)

    top_sections = [s[0] for s in scored[:12]]
    source_books = list(set(s["book_title"] for s in top_sections))

    if not top_sections:
        for book in books[:3]:
            sections = split_book_into_sections(book)
            top_sections.extend(sections[:2])

    return top_sections, source_books, books


def _extract_key_entities(sections):
    entities = set()
    for section in sections:
        content = section.get("content", "")
        multi_word = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', content)
        entities.update(multi_word[:5])

        tech_terms = re.findall(r'\b([A-Z]{2,}[a-z]*(?:-[A-Za-z]+)*)\b', content)
        entities.update(t for t in tech_terms if len(t) > 2 and t not in ("The", "This", "That", "From", "With", "AND", "NOT", "FOR"))

        header = section.get("header", "")
        if header and len(header) > 3:
            entities.add(header)

    return list(entities)[:15]


def search_knowledge_sections(question, db, history=None):
    try:
        query_str = question
        if history:
            history_words = []
            for h in history[-4:]:
                content = h.get("content", "").lower()
                for w in content.split():
                    if len(w) > 3 and w not in STOP_WORDS and w not in history_words:
                        history_words.append(w)
            if history_words:
                query_str = question + " " + " ".join(history_words[:10])

        query_embedding = embed_text(query_str)

        from hiveai.vectorstore import vector_search
        top_sections = vector_search(db, query_embedding, limit=12, max_distance=0.8)

        if top_sections and len(top_sections) >= 2:
            try:
                entities = _extract_key_entities(top_sections)
                if entities:
                    entity_query = " ".join(entities[:10])
                    entity_embedding = embed_text(entity_query)

                    found_ids = set(s.get("id") for s in top_sections if s.get("id"))

                    hop2_results = vector_search(db, entity_embedding, limit=8, max_distance=0.7)

                    hop2_new = 0
                    for row in hop2_results:
                        if row["id"] not in found_ids:
                            top_sections.append(row)
                            found_ids.add(row["id"])
                            hop2_new += 1
                            if hop2_new >= 4:
                                break

                    if hop2_new > 0:
                        logging.getLogger(__name__).info(f"Multi-hop RAG: {len(entities)} entities → {hop2_new} additional sections")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Multi-hop search failed (non-critical): {e}")

        if len(top_sections) >= 3:
            book_ids = list(set(section['book_id'] for section in top_sections))
            logging.getLogger(__name__).info(f"Vector search found sections from {len(book_ids)} books")

            try:
                from hiveai.models import BookReference
                refs = db.query(BookReference).filter(
                    BookReference.from_book_id.in_(book_ids)
                ).all()
                ref_book_ids = [r.to_book_id for r in refs if r.to_book_id not in set(book_ids)]
                if ref_book_ids:
                    found_ids = set(s.get("id") for s in top_sections if s.get("id"))
                    ref_results = vector_search(db, query_embedding, limit=4, max_distance=0.7, book_id_filter=ref_book_ids)
                    ref_added = 0
                    for row in ref_results:
                        if row["id"] not in found_ids:
                            row["book_title"] = f"{row['book_title']} (referenced)"
                            top_sections.append(row)
                            found_ids.add(row["id"])
                            ref_added += 1
                    if ref_added > 0:
                        logging.getLogger(__name__).info(f"Book references: added {ref_added} sections from {len(ref_book_ids)} referenced books")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Book reference lookup failed (non-critical): {e}")

            try:
                top_sections = rerank_sections(question, top_sections)
                logging.getLogger(__name__).info(f"Cross-encoder reranking applied to {len(top_sections)} sections")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Reranking failed (non-critical): {e}")

            try:
                if len(top_sections) < 5:
                    from hiveai.pipeline.communities import get_community_summaries
                    community_summaries = get_community_summaries(question, db)
                    if community_summaries:
                        for cs in community_summaries[:3]:
                            top_sections.append({
                                "header": "Community Knowledge Summary",
                                "content": cs,
                                "book_title": "Community Analysis",
                                "book_id": None,
                            })
                        logging.getLogger(__name__).info(f"Added {min(len(community_summaries), 3)} community summaries for broad question")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Community summary lookup failed (non-critical): {e}")

            source_books = list(set(s["book_title"] for s in top_sections))
            books = db.query(GoldenBook).all()
            return top_sections, source_books, books

    except Exception as e:
        logging.getLogger(__name__).warning(f"Vector search failed, falling back to keyword search: {e}")

    return keyword_search_sections(question, db, history=history)


def build_conversation_context(history):
    if not history:
        return ""

    recent = history[-6:]
    topics_discussed = []
    context_lines = []

    for h in recent:
        role = h.get("role", "")
        content = h.get("content", "")
        if role == "user":
            topics_discussed.append(content[:100])
            context_lines.append(f"User asked: {content[:300]}")
        elif role == "assistant":
            summary = content[:400]
            if len(content) > 400:
                summary += "..."
            context_lines.append(f"Keeper answered: {summary}")

    result = "\nConversation history (build on this, don't repeat):"
    if topics_discussed:
        result += f"\nTopics already discussed: {', '.join(topics_discussed)}"
    result += "\n" + "\n".join(context_lines)
    return result


def get_compressed_knowledge(book_ids, db):
    if not book_ids:
        return ""
    compressed_parts = []
    books = db.query(GoldenBook).filter(GoldenBook.id.in_(book_ids)).all()
    seen_ids = set(book_ids)

    for book in books:
        if book.compressed_content:
            compressed_parts.append(book.compressed_content)

    try:
        from hiveai.models import BookReference
        refs = db.query(BookReference).filter(
            BookReference.from_book_id.in_(book_ids)
        ).all()

        ref_book_ids = [r.to_book_id for r in refs if r.to_book_id not in seen_ids]
        if ref_book_ids:
            ref_books = db.query(GoldenBook).filter(GoldenBook.id.in_(ref_book_ids)).all()
            for ref_book in ref_books:
                if ref_book.compressed_content and ref_book.id not in seen_ids:
                    compressed_parts.append(f"--- Referenced: {ref_book.title} ---\n{ref_book.compressed_content}")
                    seen_ids.add(ref_book.id)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to follow book references (non-critical): {e}")

    return "\n\n".join(compressed_parts)


def clean_topic(raw_topic):
    topic = raw_topic.strip().strip('"').strip("'").strip()
    topic = topic.split("\n")[0].strip()
    for sep in [". ", "; ", " - ", " — ", ", my ", ", but "]:
        if sep in topic.lower():
            topic = topic[:topic.lower().index(sep)].strip()
            break
    if len(topic) > 100:
        topic = " ".join(topic[:100].split()[:-1])
    if len(topic) < 3:
        return None
    return topic

def trigger_auto_learn(topic, db):
    topic = clean_topic(topic)
    if not topic:
        return {"active": False}, True

    existing = db.query(Job).filter(
        Job.topic.ilike(f"%{topic}%"),
        Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing", "review"])
    ).first()

    if existing:
        return {"active": True, "topic": topic, "job_id": existing.id}, True

    job = Job(topic=topic, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    return {"active": True, "topic": topic, "job_id": job.id}, False
