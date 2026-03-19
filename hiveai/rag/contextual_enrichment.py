"""
Contextual Retrieval Enrichment — prepend document-context prefix to sections.

Based on Anthropic's Contextual Retrieval technique (September 2024):
Before embedding a chunk, generate a short sentence explaining where the chunk
sits in the broader document. This 1-2 sentence prefix dramatically improves
retrieval quality (35-67% fewer failures when combined with BM25 + reranking).

Usage:
    # Batch enrich all sections (one-time, ~30 min for 949 sections)
    python -m hiveai.rag.contextual_enrichment --batch

    # Enrich a single section (used by promotion pipeline)
    from hiveai.rag.contextual_enrichment import enrich_section
    context_prefix = enrich_section(book_title, section_header, section_content)
"""
import json
import logging
import hashlib
import threading

logger = logging.getLogger(__name__)

# Cache to avoid regenerating context for unchanged sections
_context_cache: dict[str, str] = {}
_context_cache_lock = threading.Lock()

_CONTEXT_PROMPT = """Given the following book and section from a programming knowledge base, write a concise 1-2 sentence context prefix that explains what this section covers and how it relates to the broader document. The prefix should help a search engine match this section to relevant queries.

Book: {book_title}
Section header: {header}

Section content (first 1500 chars):
{content}

Context prefix (1-2 sentences only):"""


def generate_context_prefix(book_title: str, header: str, content: str) -> str | None:
    """Generate a contextual prefix for a section using the fast model.

    Returns a 1-2 sentence context string, or None on failure.
    """
    cache_key = hashlib.md5(f"{book_title}|{header}|{content[:200]}".encode()).hexdigest()
    with _context_cache_lock:
        if cache_key in _context_cache:
            return _context_cache[cache_key]

    try:
        from hiveai.llm.client import fast

        result = fast(
            _CONTEXT_PROMPT.format(
                book_title=book_title or "Unknown",
                header=header or "Untitled",
                content=(content or "")[:1500],
            ),
            max_tokens=120,
        )
        if not result or len(result.strip()) < 10:
            return None

        prefix = result.strip()
        # Ensure it ends with a period
        if not prefix.endswith(('.', '!', '?')):
            prefix += '.'

        with _context_cache_lock:
            if len(_context_cache) > 2000:
                # Evict oldest
                oldest = next(iter(_context_cache))
                del _context_cache[oldest]
            _context_cache[cache_key] = prefix

        return prefix

    except Exception as e:
        logger.warning(f"Context generation failed for '{header}': {e}")
        return None


def enrich_section_content(book_title: str, header: str, content: str) -> str:
    """Return content with contextual prefix prepended.

    If context generation fails, returns original content unchanged.
    """
    prefix = generate_context_prefix(book_title, header, content)
    if not prefix:
        return content
    return f"{prefix}\n\n{content}"


def batch_enrich_and_reembed(db, force: bool = False, dry_run: bool = False) -> dict:
    """Enrich all sections with contextual prefixes and re-embed.

    Args:
        db: SQLAlchemy session
        force: Re-enrich even sections that already have context
        dry_run: Generate prefixes but don't write to DB

    Returns:
        {"enriched": int, "skipped": int, "failed": int, "total": int}
    """
    from hiveai.models import BookSection, GoldenBook
    from hiveai.llm.client import embed_texts

    sections = db.query(BookSection).filter(
        BookSection.content != None,
        BookSection.content != "",
    ).all()

    # Build book title lookup
    books = {b.id: b.title for b in db.query(GoldenBook).all()}

    total = len(sections)
    enriched = 0
    skipped = 0
    failed = 0

    logger.info(f"Contextual enrichment: {total} sections to process (force={force}, dry_run={dry_run})")

    # Collect sections needing enrichment
    to_enrich = []
    for section in sections:
        meta = {}
        if section.keywords_json:
            try:
                meta = json.loads(section.keywords_json) if isinstance(section.keywords_json, str) else section.keywords_json
            except (json.JSONDecodeError, TypeError):
                meta = {}

        if not force and meta.get("contextual_prefix"):
            skipped += 1
            continue

        to_enrich.append((section, meta))

    logger.info(f"  {len(to_enrich)} sections need enrichment, {skipped} already have context")

    # Generate context prefixes
    enriched_sections = []
    for section, meta in to_enrich:
        book_title = books.get(section.book_id, "Unknown Book")
        prefix = generate_context_prefix(book_title, section.header, section.content)
        if prefix:
            meta["contextual_prefix"] = prefix
            enriched_sections.append((section, meta, prefix))
            enriched += 1
            if enriched % 50 == 0:
                logger.info(f"  Generated {enriched}/{len(to_enrich)} prefixes...")
        else:
            failed += 1

    logger.info(f"  Generated {enriched} prefixes, {failed} failed")

    if dry_run:
        logger.info("  DRY RUN — no changes written")
        return {"enriched": enriched, "skipped": skipped, "failed": failed, "total": total}

    # Re-embed with contextual content
    BATCH_SIZE = 32
    for i in range(0, len(enriched_sections), BATCH_SIZE):
        batch = enriched_sections[i:i + BATCH_SIZE]
        texts = [f"{prefix}\n\n{s.content}" for s, _, prefix in batch]
        try:
            embeddings = embed_texts(texts)
            for (section, meta, _), embedding in zip(batch, embeddings):
                section.embedding = embedding
                section.keywords_json = json.dumps(meta)
            db.flush()
            logger.info(f"  Re-embedded batch {i//BATCH_SIZE + 1}/{(len(enriched_sections) + BATCH_SIZE - 1)//BATCH_SIZE}")
        except Exception as e:
            logger.error(f"  Failed to embed batch at index {i}: {e}")
            failed += len(batch)
            enriched -= len(batch)

    db.commit()
    logger.info(f"Contextual enrichment complete: {enriched} enriched, {skipped} skipped, {failed} failed, {total} total")

    return {"enriched": enriched, "skipped": skipped, "failed": failed, "total": total}


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Contextual enrichment for RAG sections")
    parser.add_argument("--batch", action="store_true", help="Enrich all sections")
    parser.add_argument("--force", action="store_true", help="Re-enrich even sections with existing context")
    parser.add_argument("--dry-run", action="store_true", help="Generate prefixes but don't write")
    args = parser.parse_args()

    if not args.batch:
        parser.print_help()
        sys.exit(1)

    from hiveai.models import SessionLocal
    db = SessionLocal()
    try:
        result = batch_enrich_and_reembed(db, force=args.force, dry_run=args.dry_run)
        print(f"\nResult: {result}")
    finally:
        db.close()
