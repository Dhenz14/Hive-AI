import logging
import hashlib
import json
from hiveai.models import SessionLocal, GraphTriple, CrawledPage, GoldenBook, Job, BookSection
from hiveai.llm.client import reason, fast, embed_texts
from hiveai.llm.prompts import GOLDEN_BOOK_PROMPT, REWRITE_BOOK_PROMPT, GOLDEN_BOOK_OUTLINE_PROMPT, GOLDEN_BOOK_REVIEW_PROMPT
from hiveai.chat import _extract_section_keywords

logger = logging.getLogger(__name__)


def split_book_content(book):
    if not book.content:
        return []

    lines = book.content.split("\n")
    sections = []
    current_header = book.title or "Introduction"
    current_lines = []

    for line in lines:
        if line.startswith("#") and len(line) > 2:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if len(text) > 50:
                    sections.append({
                        "header": current_header,
                        "content": text,
                    })
            current_header = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if len(text) > 50:
            sections.append({
                "header": current_header,
                "content": text,
            })

    return sections


def embed_book_sections(book, db):
    sections = split_book_content(book)
    if not sections:
        logger.info(f"No sections to embed for book {book.id}")
        return 0

    # Contextual enrichment: prepend document-context prefix for better retrieval
    texts = []
    for s in sections:
        try:
            from hiveai.rag.contextual_enrichment import generate_context_prefix
            prefix = generate_context_prefix(book.title, s["header"], s["content"])
            if prefix:
                s["_contextual_prefix"] = prefix
                texts.append(f"{prefix}\n\n{s['content']}")
            else:
                texts.append(s["content"])
        except Exception:
            texts.append(s["content"])

    logger.info(f"Embedding {len(texts)} sections for book {book.id}")
    embeddings = embed_texts(texts)

    # Extract keywords for each section (non-blocking — failures are OK)
    logger.info(f"Extracting keywords for {len(sections)} sections of book {book.id}")
    section_keywords = []
    for section in sections:
        try:
            kw = _extract_section_keywords(section["header"], section["content"])
            kw_data = kw if isinstance(kw, dict) else {"keywords": kw} if kw else {}
            # Persist contextual prefix in metadata
            prefix = section.get("_contextual_prefix")
            if prefix:
                kw_data["contextual_prefix"] = prefix
            section_keywords.append(json.dumps(kw_data) if kw_data else None)
        except Exception as e:
            logger.debug(f"Keyword extraction failed for '{section['header']}': {e}")
            section_keywords.append(None)

    for i, section in enumerate(sections):
        bs = BookSection(
            book_id=book.id,
            header=section["header"],
            content=section["content"],
            token_count=len(section["content"].split()),
            embedding=embeddings[i] if i < len(embeddings) else None,
            keywords_json=section_keywords[i] if i < len(section_keywords) else None,
        )
        db.add(bs)

    db.commit()
    kw_count = sum(1 for k in section_keywords if k is not None)
    logger.info(f"Saved {len(sections)} embedded sections for book {book.id} ({kw_count} with keywords)")
    return len(sections)


def write_golden_book(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = "writing"
        db.commit()

        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()
        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()

        if not triples:
            logger.warning(f"No triples found for job {job_id}, cannot write book")
            return None

        knowledge_audit = ""
        overlapping_books = []
        novel_triples = triples  # default: use all triples
        try:
            from hiveai.pipeline.graph_merger import build_knowledge_audit, filter_novel_triples
            knowledge_audit, overlapping_books = build_knowledge_audit(job.topic, db)
            if knowledge_audit and overlapping_books:
                overlapping_ids = [ob["book_id"] for ob in overlapping_books]
                novel_triples = filter_novel_triples(triples, overlapping_ids, db)
                if not novel_triples:
                    logger.info(f"All triples are already known — still writing book with unique perspective")
                    novel_triples = triples  # fallback: use all if nothing is novel
                else:
                    logger.info(f"Novelty filter: {len(triples)} total → {len(novel_triples)} novel triples")
        except Exception as audit_err:
            logger.warning(f"Knowledge audit failed (non-critical): {audit_err}")

        triples_text = "\n".join([
            f"({t.subject}) --[{t.predicate}]--> ({t.obj})"
            for t in novel_triples
        ])

        source_urls = list(set([p.url for p in pages if p.url]))

        triple_source_urls = list(set([t.source_url for t in triples if t.source_url]))
        for url in triple_source_urls:
            if url not in source_urls:
                source_urls.append(url)

        sources_text = "\n".join([f"- {url}" for url in source_urls[:50]])

        target_words = max(800, len(triples) * 8)

        outline_text = ""
        try:
            outline_prompt = GOLDEN_BOOK_OUTLINE_PROMPT.format(
                topic=job.topic,
                triples=triples_text[:6000],
                triple_count=len(triples),
            )
            logger.info(f"Step 1/3: Generating outline for job {job_id}")
            outline_text = fast(outline_prompt, max_tokens=2048)
            if outline_text:
                outline_text = f"Document Outline (follow this structure):\n{outline_text}"
                logger.info(f"Outline generated ({len(outline_text.split())} words)")
            else:
                outline_text = ""
                logger.warning("Outline generation returned empty, proceeding without outline")
        except Exception as e:
            logger.warning(f"Outline generation failed, proceeding without outline: {e}")
            outline_text = ""

        if knowledge_audit:
            from hiveai.llm.prompts import GOLDEN_BOOK_LEGO_PROMPT
            prompt = GOLDEN_BOOK_LEGO_PROMPT.format(
                topic=job.topic,
                outline=outline_text,
                triples=triples_text,
                sources=sources_text,
                triple_count=len(novel_triples),
                source_count=len(source_urls),
                target_words=target_words,
                knowledge_audit=knowledge_audit,
            )
            logger.info(f"Using Lego mode: {len(overlapping_books)} related books found, writing only novel content")
        else:
            prompt = GOLDEN_BOOK_PROMPT.format(
                topic=job.topic,
                outline=outline_text,
                triples=triples_text,
                sources=sources_text,
                triple_count=len(triples),
                source_count=len(source_urls),
                target_words=target_words,
            )

        logger.info(f"Step 2/3: Writing Golden Book for job {job_id} ({len(triples)} triples, {len(source_urls)} sources)")
        final_content = reason(prompt, max_tokens=8192)

        if not final_content:
            logger.error(f"LLM returned empty content for job {job_id}")
            return None

        try:
            review_prompt = GOLDEN_BOOK_REVIEW_PROMPT.format(
                content=final_content[:6000],
                triples=triples_text[:4000],
            )
            logger.info(f"Step 3/3: Reviewing Golden Book for job {job_id}")
            review_response = fast(review_prompt, max_tokens=2048)
            if review_response and "MAJOR_ISSUES" in review_response:
                logger.info(f"Review found major issues, triggering rewrite for job {job_id}")
                rewrite_prompt = REWRITE_BOOK_PROMPT.format(
                    topic=job.topic,
                    current_content=final_content[:8000],
                    quality_issues=review_response,
                    knowledge_source=triples_text[:6000],
                )
                rewritten = reason(rewrite_prompt, max_tokens=8192)
                if rewritten and len(rewritten) >= len(final_content) * 0.5:
                    final_content = rewritten
                    logger.info("Rewrite completed after review")
                else:
                    logger.warning("Rewrite produced insufficient content, keeping original")
            else:
                logger.info("Review passed — no major issues found")
        except Exception as e:
            logger.warning(f"Review step failed, keeping original content: {e}")

        content_hash = hashlib.sha256(final_content.encode()).hexdigest()
        word_count = len(final_content.split())

        book = GoldenBook(
            job_id=job_id,
            title=f"Knowledge: {job.topic}",
            content=final_content,
            content_hash=content_hash,
            source_count=len(source_urls),
            source_urls=source_urls,
            triple_count=len(triples),
            word_count=word_count,
            status="draft",
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        job.golden_book_id = book.id
        job.status = "review"
        db.commit()

        logger.info(f"Golden Book written: '{book.title}' ({word_count} words, hash: {content_hash[:12]}...)")

        try:
            from hiveai.pipeline.compressor import compress_golden_book
            triples_for_compress = [
                {"subject": t.subject, "predicate": t.predicate, "obj": t.obj,
                 "confidence": t.confidence, "source_url": t.source_url or ""}
                for t in triples
            ]
            compressed = compress_golden_book(book.content, triples_for_compress, topic=job.topic)
            if compressed:
                book.compressed_content = compressed
                db.commit()
                logger.info(f"Compressed knowledge generated ({len(compressed)} chars)")
        except Exception as compress_err:
            logger.warning(f"Failed to generate compressed knowledge: {compress_err}")

        if overlapping_books:
            try:
                from hiveai.pipeline.graph_merger import save_book_references
                save_book_references(book.id, overlapping_books, db)
                logger.info(f"Saved {len(overlapping_books)} cross-book references")
            except Exception as ref_err:
                logger.warning(f"Failed to save book references: {ref_err}")

        try:
            embed_book_sections(book, db)
        except Exception as embed_err:
            logger.warning(f"Failed to embed sections for book {book.id}: {embed_err}")

        try:
            from hiveai.pipeline.scorer import score_book
            result = score_book(book)
            book.quality_score = result["score"]
            book.quality_details = result["details"]
            db.commit()
            logger.info(f"Quality score for book {book.id}: {result['score']}")
        except Exception as score_err:
            logger.warning(f"Failed to score book {book.id}: {score_err}")

        return book

    except Exception as e:
        logger.error(f"Golden Book writing failed for job {job_id}: {e}")
        job = db.get(Job, job_id)
        if job:
            job.status = "error"
            job.error_message = str(e)
        db.commit()
        raise
    finally:
        db.close()


def rewrite_book(book_id):
    db = SessionLocal()
    try:
        book = db.get(GoldenBook, book_id)
        if not book:
            logger.warning(f"Book {book_id} not found for rewrite")
            return None

        job = db.get(Job, book.job_id) if book.job_id else None
        topic = job.topic if job else book.title.replace("Knowledge: ", "")

        knowledge_source = ""
        if book.job_id:
            triples = db.query(GraphTriple).filter(GraphTriple.job_id == book.job_id).all()
            if triples:
                knowledge_source = "Knowledge Graph Triples:\n" + "\n".join([
                    f"({t.subject}) --[{t.predicate}]--> ({t.obj})"
                    for t in triples
                ])

        if not knowledge_source:
            sections = db.query(BookSection).filter(BookSection.book_id == book_id).all()
            if sections:
                knowledge_source = "Existing sections:\n" + "\n\n".join([
                    f"### {s.header}\n{s.content}" for s in sections
                ])
            else:
                knowledge_source = "Original document content (use this as the knowledge source)"

        quality_issues = "Overall score: "
        if book.quality_score is not None:
            quality_issues += f"{book.quality_score:.2f}/1.00\n"
        else:
            quality_issues += "not scored\n"

        if book.quality_details:
            details = book.quality_details if isinstance(book.quality_details, dict) else json.loads(book.quality_details)
            for criterion, score in details.items():
                status = "WEAK" if score < 0.5 else "OK" if score < 0.8 else "STRONG"
                quality_issues += f"- {criterion}: {score:.2f} ({status})\n"

        prompt = REWRITE_BOOK_PROMPT.format(
            topic=topic,
            current_content=book.content[:8000],
            quality_issues=quality_issues,
            knowledge_source=knowledge_source[:6000],
        )

        logger.info(f"Rewriting book {book_id} '{book.title}' (current score: {book.quality_score})")
        new_content = reason(prompt, max_tokens=8192)

        if not new_content or len(new_content) < len(book.content) * 0.5:
            logger.warning(f"Rewrite produced insufficient content for book {book_id}, keeping original")
            return book

        book.content = new_content
        book.content_hash = hashlib.sha256(new_content.encode()).hexdigest()
        book.word_count = len(new_content.split())
        book.needs_rewrite = False
        db.commit()

        try:
            from hiveai.pipeline.compressor import compress_golden_book
            triples = db.query(GraphTriple).filter(GraphTriple.job_id == book.job_id).all() if book.job_id else []
            if triples:
                triples_for_compress = [
                    {"subject": t.subject, "predicate": t.predicate, "obj": t.obj,
                     "confidence": t.confidence, "source_url": t.source_url or ""}
                    for t in triples
                ]
                compressed = compress_golden_book(new_content, triples_for_compress, topic=topic)
                if compressed:
                    book.compressed_content = compressed
                    db.commit()
        except Exception as compress_err:
            logger.warning(f"Failed to regenerate compressed knowledge during rewrite: {compress_err}")

        db.query(BookSection).filter(BookSection.book_id == book_id).delete()
        db.commit()

        try:
            embed_book_sections(book, db)
        except Exception as e:
            logger.warning(f"Failed to re-embed sections for rewritten book {book_id}: {e}")

        try:
            from hiveai.pipeline.scorer import score_book
            result = score_book(book)
            book.quality_score = result["score"]
            book.quality_details = result["details"]
            db.commit()
            logger.info(f"Rewritten book {book_id} new quality score: {result['score']}")
        except Exception as e:
            logger.warning(f"Failed to re-score rewritten book {book_id}: {e}")

        return book
    except Exception as e:
        logger.error(f"Book rewrite failed for {book_id}: {e}")
        return None
    finally:
        db.close()
