"""
Lego Rebuild Script
Processes existing books into a proper Lego mound:
1. Book 2 (foundation) - extract triples, compress only (no rewrite)
2. All subsequent books - extract triples, knowledge audit, Lego rewrite, compress, save references
"""
import logging
import hashlib
import json
import sys
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("lego_rebuild")

from hiveai.models import SessionLocal, GoldenBook, BookSection, BookReference
from hiveai.llm.client import reason, fast, embed_texts
from hiveai.pipeline.compressor import compress_golden_book, encode_triples_dense
from hiveai.pipeline.writer import split_book_content
from hiveai.pipeline.graph_merger import build_knowledge_audit, filter_novel_triples, save_book_references, find_overlapping_books
from hiveai.llm.prompts import GOLDEN_BOOK_LEGO_PROMPT, GOLDEN_BOOK_OUTLINE_PROMPT, GOLDEN_BOOK_REVIEW_PROMPT, REWRITE_BOOK_PROMPT

TRIPLE_FROM_PROSE_PROMPT = """Extract subject-predicate-object knowledge triples from this text.
Focus on concrete facts, relationships, and technical details.
Be concise — return ONLY the JSON array, no explanation.

Text:
{text}

JSON array: [{{"subject":"...","predicate":"...","object":"...","confidence":0.9}},...]"""


def extract_triples_from_prose(book_content, topic):
    prompt = TRIPLE_FROM_PROSE_PROMPT.format(text=book_content[:6000])
    try:
        response = fast(prompt, max_tokens=4096)
        if not response:
            return []

        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            parsed = json.loads(response[start:end])
            triples = []
            for t in parsed:
                if isinstance(t, dict) and "subject" in t and "predicate" in t and "object" in t:
                    triples.append({
                        "subject": t["subject"],
                        "predicate": t["predicate"],
                        "obj": t["object"],
                        "confidence": t.get("confidence", 0.8),
                        "source_url": "",
                    })
            logger.info(f"  Extracted {len(triples)} triples from prose")
            return triples
    except Exception as e:
        logger.warning(f"  Triple extraction failed: {e}")

    return []


def compress_book_from_triples(book, triples, db):
    topic = book.title.replace("Knowledge: ", "")
    compressed = compress_golden_book(book.content, triples, topic=topic)
    if compressed:
        book.compressed_content = compressed
        db.commit()
        logger.info(f"  Compressed: {len(compressed)} chars")
    return compressed


def embed_book(book, db):
    db.query(BookSection).filter(BookSection.book_id == book.id).delete()
    db.commit()

    sections = split_book_content(book)
    if not sections:
        return 0

    texts = [s["content"] for s in sections]
    logger.info(f"  Embedding {len(texts)} sections")
    embeddings = embed_texts(texts)

    for i, section in enumerate(sections):
        bs = BookSection(
            book_id=book.id,
            header=section["header"],
            content=section["content"],
            token_count=len(section["content"].split()),
            embedding=embeddings[i] if i < len(embeddings) else None,
        )
        db.add(bs)

    db.commit()
    return len(sections)


def lego_rewrite_book(book, triples, knowledge_audit, overlapping_books, db):
    topic = book.title.replace("Knowledge: ", "")

    triples_text = "\n".join([
        f"({t['subject']}) --[{t['predicate']}]--> ({t['obj']})"
        for t in triples
    ])

    source_urls = book.source_urls or []
    sources_text = "\n".join([f"- {url}" for url in source_urls[:50]])
    target_words = max(800, len(triples) * 8)

    outline_text = ""
    try:
        outline_prompt = GOLDEN_BOOK_OUTLINE_PROMPT.format(
            topic=topic,
            triples=triples_text[:6000],
            triple_count=len(triples),
        )
        outline_text = fast(outline_prompt, max_tokens=2048)
        if outline_text:
            outline_text = f"Document Outline (follow this structure):\n{outline_text}"
    except Exception as e:
        logger.warning(f"  Outline failed: {e}")

    prompt = GOLDEN_BOOK_LEGO_PROMPT.format(
        topic=topic,
        outline=outline_text,
        triples=triples_text,
        sources=sources_text,
        triple_count=len(triples),
        source_count=len(source_urls),
        target_words=target_words,
        knowledge_audit=knowledge_audit,
    )

    logger.info(f"  Writing Lego rewrite ({len(triples)} triples, {len(overlapping_books)} refs)")
    new_content = fast(prompt, max_tokens=8192)

    if not new_content or len(new_content) < 500:
        logger.warning(f"  Lego rewrite produced insufficient content, keeping original")
        return False

    book.content = new_content
    book.content_hash = hashlib.sha256(new_content.encode()).hexdigest()
    book.word_count = len(new_content.split())
    db.commit()

    logger.info(f"  Rewritten: {book.word_count} words")
    return True


def process_foundation_book(book_id, db):
    book = db.get(GoldenBook, book_id)
    if not book:
        logger.error(f"Book {book_id} not found")
        return False

    logger.info(f"=== FOUNDATION: '{book.title}' (id={book.id}) ===")
    logger.info(f"  Content: {len(book.content)} chars, {len(book.content.split())} words")

    triples = extract_triples_from_prose(book.content, book.title)
    if not triples:
        logger.error("  No triples extracted from foundation book!")
        return False

    compress_book_from_triples(book, triples, db)
    embed_book(book, db)

    logger.info(f"  Foundation book ready")
    return True


def process_lego_book(book_id, db):
    book = db.get(GoldenBook, book_id)
    if not book:
        logger.error(f"Book {book_id} not found")
        return False

    topic = book.title.replace("Knowledge: ", "")
    logger.info(f"=== LEGO REWRITE: '{book.title}' (id={book.id}) ===")

    triples = extract_triples_from_prose(book.content, topic)
    if not triples:
        logger.warning(f"  No triples extracted, skipping Lego rewrite")
        return False

    knowledge_audit, overlapping_books = build_knowledge_audit(topic, db)

    if knowledge_audit and overlapping_books:
        logger.info(f"  Knowledge audit found {len(overlapping_books)} overlapping books")

        class FakeTriple:
            def __init__(self, d):
                self.subject = d["subject"]
                self.predicate = d["predicate"]
                self.obj = d["obj"]
                self.confidence = d.get("confidence", 0.8)
                self.source_url = d.get("source_url", "")

        fake_triples = [FakeTriple(t) for t in triples]
        overlapping_ids = [ob["book_id"] for ob in overlapping_books]
        novel_triples_obj = filter_novel_triples(fake_triples, overlapping_ids, db)

        novel_triples = [
            {"subject": t.subject, "predicate": t.predicate, "obj": t.obj,
             "confidence": t.confidence, "source_url": t.source_url}
            for t in novel_triples_obj
        ]

        if not novel_triples:
            logger.info(f"  All triples known — using all {len(triples)} for unique perspective")
            novel_triples = triples
        else:
            logger.info(f"  Novelty filter: {len(triples)} → {len(novel_triples)} novel triples")

        lego_rewrite_book(book, novel_triples, knowledge_audit, overlapping_books, db)

        save_book_references(book.id, overlapping_books, db)
        logger.info(f"  Saved {len(overlapping_books)} cross-book references")
    else:
        logger.info(f"  No overlapping books found — compressing without Lego rewrite")

    compress_book_from_triples(book, triples, db)
    embed_book(book, db)

    logger.info(f"  Book {book.id} processed")
    return True


def main():
    target_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

    db = SessionLocal()
    try:
        books = db.query(GoldenBook).order_by(GoldenBook.created_at.asc()).all()
        foundation_id = books[0].id

        if target_id:
            if target_id == foundation_id:
                process_foundation_book(target_id, db)
            else:
                process_lego_book(target_id, db)
            return

        logger.info(f"Found {len(books)} books to process")

        start_time = time.time()

        if not books[0].compressed_content:
            process_foundation_book(books[0].id, db)
        else:
            logger.info(f"Foundation book already compressed, skipping")

        for book in books[1:]:
            db.expire_all()
            if book.compressed_content:
                logger.info(f"Skipping already-compressed book {book.id}: '{book.title}'")
                continue
            process_lego_book(book.id, db)
            logger.info("")

        elapsed = time.time() - start_time
        logger.info(f"=== LEGO REBUILD COMPLETE ({elapsed:.0f}s) ===")

        db.expire_all()
        books = db.query(GoldenBook).order_by(GoldenBook.created_at.asc()).all()
        for b in books:
            has_compressed = "YES" if b.compressed_content else "NO"
            logger.info(f"  Book {b.id}: '{b.title}' compressed={has_compressed}")

        ref_count = db.query(BookReference).count()
        logger.info(f"  Total cross-book references: {ref_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
