import logging
import json
import re
from hiveai.models import SessionLocal, Job, CrawledPage, Chunk, GraphTriple, GoldenBook
from hiveai.pipeline.crawler import mass_crawl
from hiveai.pipeline.cleaner import process_chunks
from hiveai.pipeline.reasoner import run_reasoning_pipeline
from hiveai.pipeline.writer import write_golden_book
from hiveai.pipeline.graph_merger import find_overlapping_books, merge_triples, build_cross_references
from hiveai.pipeline.entity_resolver import resolve_triples
from hiveai.pipeline.contradiction import detect_contradictions, resolve_contradictions
from hiveai.llm.client import fast, clean_llm_response
from hiveai.llm.prompts import SOURCE_URLS_PROMPT, GAP_RESEARCH_PROMPT
from hiveai.pipeline.reasoner import extract_triples, check_coverage
from hiveai.pipeline.url_discovery import discover_urls, discover_gap_urls, extract_links_from_content, validate_urls
from hiveai.config import SERPER_API_KEY
from hiveai.pipeline.queue_worker import is_job_cancelled
import requests

logger = logging.getLogger(__name__)


def search_web_for_urls(topic, max_results=15):
    try:
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = {"q": topic, "num": max_results}
        resp = requests.post("https://google.serper.dev/search", headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        urls = [item["link"] for item in data.get("organic", []) if "link" in item]
        topic_slug = topic.replace(' ', '_')
        wiki_url = f"https://en.wikipedia.org/wiki/{topic_slug}"
        if wiki_url not in urls:
            urls.append(wiki_url)
        return urls
    except Exception as e:
        logger.warning(f"Serper web search failed: {e}")
        return []


def _llm_generate_source_urls(topic):
    try:
        prompt = SOURCE_URLS_PROMPT.format(topic=topic)
        response = fast(prompt, max_tokens=2048)
        text = clean_llm_response(response)

        array_match = re.search(r'\[.*\]', text, re.DOTALL)
        if array_match:
            text = array_match.group()

        urls = json.loads(text)

        if isinstance(urls, dict) and "urls" in urls:
            urls = urls["urls"]

        if isinstance(urls, list):
            valid_urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
            from urllib.parse import urlparse
            domains = [urlparse(u).netloc for u in valid_urls]
            unique_domains = set(domains)
            if len(valid_urls) > 4 and len(unique_domains) < len(valid_urls) * 0.3:
                logger.warning(f"Low URL diversity: {len(unique_domains)} unique domains from {len(valid_urls)} URLs, regenerating")
                prompt2 = SOURCE_URLS_PROMPT.format(topic=topic) + "\n\nCRITICAL: Your previous response had too many URLs from the same domain. Each URL MUST be from a DIFFERENT domain."
                response2 = fast(prompt2, max_tokens=2048)
                text2 = clean_llm_response(response2)
                array_match2 = re.search(r'\[.*\]', text2, re.DOTALL)
                if array_match2:
                    text2 = array_match2.group()
                try:
                    urls2 = json.loads(text2)
                    if isinstance(urls2, list):
                        valid2 = [u for u in urls2 if isinstance(u, str) and u.startswith("http")]
                        if valid2:
                            valid_urls = valid2
                except Exception:
                    pass
            return valid_urls
    except Exception as e:
        logger.warning(f"Failed to generate source URLs via LLM: {e}")

    topic_slug = topic.replace(' ', '_')
    topic_dash = topic.lower().replace(' ', '-')
    return [
        f"https://en.wikipedia.org/wiki/{topic_slug}",
        f"https://simple.wikipedia.org/wiki/{topic_slug}",
        f"https://www.britannica.com/topic/{topic_dash}",
        f"https://www.geeksforgeeks.org/{topic_dash}/",
        f"https://www.tutorialspoint.com/{topic_dash}/index.htm",
        f"https://developer.mozilla.org/en-US/search?q={topic.replace(' ', '+')}",
    ]


def generate_source_urls(topic):
    if SERPER_API_KEY:
        urls = search_web_for_urls(topic)
        if len(urls) >= 5:
            topic_slug = topic.replace(' ', '_')
            wiki_url = f"https://en.wikipedia.org/wiki/{topic_slug}"
            if wiki_url not in urls:
                urls.append(wiki_url)
            logger.info(f"Source URLs: using Serper web search ({len(urls)} URLs)")
            return urls
        logger.info("Source URLs: Serper returned insufficient results, trying free discovery")

    logger.info("Source URLs: using free URL discovery (SearXNG + Brave + DuckDuckGo + seed URLs)")
    urls = discover_urls(topic)
    if len(urls) >= 3:
        logger.info(f"Source URLs: free discovery found {len(urls)} URLs")
        return urls

    logger.info("Source URLs: free discovery insufficient, falling back to LLM generation")
    llm_urls = _llm_generate_source_urls(topic)
    combined = list(urls) + [u for u in llm_urls if u not in urls]
    return combined


TOPIC_STOP_WORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "is",
    "vs", "versus", "about", "with", "how", "what", "why", "knowledge"
}

def normalize_topic_words(text):
    words = set()
    for w in text.lower().replace("-", " ").replace("_", " ").split():
        w = w.strip(".,;:!?()[]{}\"'")
        if len(w) > 1 and w not in TOPIC_STOP_WORDS:
            words.add(w)
    return words

def check_and_replace_duplicate_book(topic, db):
    topic_words = normalize_topic_words(topic)
    if not topic_words:
        return None

    existing_books = db.query(GoldenBook).all()
    best_match = None
    best_score = 0

    for book in existing_books:
        book_topic = book.title.replace("Knowledge: ", "").strip()
        book_words = normalize_topic_words(book_topic)
        if not book_words:
            continue

        intersection = topic_words & book_words
        shorter = min(len(topic_words), len(book_words))
        overlap_ratio = len(intersection) / shorter if shorter else 0

        if overlap_ratio > best_score:
            best_score = overlap_ratio
            best_match = book

    if best_match and best_score >= 0.5:
        logger.info(f"Duplicate detected: new topic '{topic}' overlaps with existing book '{best_match.title}' (overlap={best_score:.2f}). Replacing old book id={best_match.id}.")
        from hiveai.models import Job
        jobs = db.query(Job).filter(Job.golden_book_id == best_match.id).all()
        for job in jobs:
            job.golden_book_id = None
        db.delete(best_match)
        db.commit()
        return best_match
    return None


def _llm_generate_gap_urls(topic, missing_facts, existing_urls):
    try:
        gaps_text = "\n".join([f"- {fact}" for fact in missing_facts if fact])
        existing_text = "\n".join(existing_urls) if existing_urls else "None"
        prompt = GAP_RESEARCH_PROMPT.format(topic=topic, gaps=gaps_text, existing_urls=existing_text)
        response = fast(prompt, max_tokens=2048)
        text = clean_llm_response(response)

        array_match = re.search(r'\[.*\]', text, re.DOTALL)
        if array_match:
            text = array_match.group()

        urls = json.loads(text)

        if isinstance(urls, dict) and "urls" in urls:
            urls = urls["urls"]

        if isinstance(urls, list):
            valid = [u for u in urls if isinstance(u, str) and u.startswith("http")]
            return valid[:8]
    except Exception as e:
        logger.warning(f"Failed to generate gap URLs via LLM: {e}")

    return []


def generate_gap_urls(topic, missing_facts, existing_urls):
    if SERPER_API_KEY:
        gap_summary = " ".join([fact for fact in missing_facts if fact][:5])
        query = f"{topic} {gap_summary}"
        urls = search_web_for_urls(query, max_results=10)
        if existing_urls:
            urls = [u for u in urls if u not in existing_urls]
        if urls:
            logger.info(f"Gap URLs: using Serper web search ({len(urls)} URLs)")
            return urls[:8]
        logger.info("Gap URLs: Serper returned no new results, trying free discovery")

    urls = discover_gap_urls(topic, missing_facts, existing_urls)
    if urls:
        logger.info(f"Gap URLs: free discovery found {len(urls)} new URLs")
        return urls

    logger.info("Gap URLs: free discovery insufficient, falling back to LLM generation")
    return _llm_generate_gap_urls(topic, missing_facts, existing_urls)


def iterative_research(job_id, topic, first_pass_triples, chunks, page_lookup, db):
    try:
        triple_dicts = []
        for t in first_pass_triples:
            if isinstance(t, dict):
                triple_dicts.append(t)
            else:
                triple_dicts.append({
                    "subject": getattr(t, "subject", ""),
                    "predicate": getattr(t, "predicate", ""),
                    "object": getattr(t, "obj", getattr(t, "object", "")),
                })

        missing_facts = check_coverage(triple_dicts, chunks)

        if len(missing_facts) >= 3:
            logger.info(f"Iterative research: {len(missing_facts)} gaps found, starting second pass")

            existing_pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
            existing_urls = [p.url for p in existing_pages]

            new_urls = generate_gap_urls(topic, missing_facts, existing_urls)
            if not new_urls:
                logger.info("Iterative research: no new URLs generated for gaps")
                return 0

            logger.info(f"Iterative research: {len(new_urls)} new URLs to crawl")

            existing_chunk_ids = {c.id for c in chunks}

            crawl_results = mass_crawl(new_urls, job_id)
            if not crawl_results:
                logger.info("Iterative research: second pass crawl returned no results")
                return 0

            process_chunks(job_id)

            new_chunks = db.query(Chunk).filter(
                Chunk.job_id == job_id,
                ~Chunk.id.in_(existing_chunk_ids)
            ).all()

            if not new_chunks:
                logger.info("Iterative research: no new chunks after second pass")
                return 0

            updated_pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
            updated_page_lookup = {p.id: p for p in updated_pages}

            new_triples = extract_triples(new_chunks, updated_page_lookup)
            logger.info(f"Iterative research: extracted {len(new_triples)} new triples from second pass")

            if new_triples:
                from hiveai.pipeline.authority import adjust_triple_confidence, get_domain_authority

                stored_count = 0
                for t in new_triples:
                    if not isinstance(t, dict):
                        continue
                    if not t.get("subject") or not t.get("predicate") or not t.get("object"):
                        continue

                    conf = t.get("confidence", 1.0)
                    try:
                        conf = float(conf)
                    except (ValueError, TypeError):
                        conf = 0.7

                    source_url = t.get("source_url")
                    if source_url:
                        conf = adjust_triple_confidence(conf, source_url)

                    if conf < 0.5:
                        continue

                    triple_obj = GraphTriple(
                        job_id=job_id,
                        subject=t.get("subject", "")[:500],
                        predicate=t.get("predicate", "")[:200],
                        obj=t.get("object", "")[:500],
                        confidence=conf,
                        source_chunk_id=t.get("source_chunk_id"),
                        source_url=t.get("source_url", "")[:2000] if t.get("source_url") else None,
                    )
                    db.add(triple_obj)
                    stored_count += 1

                job = db.get(Job, job_id)
                if job:
                    job.triple_count = (job.triple_count or 0) + stored_count
                db.commit()

                logger.info(f"Iterative research: stored {stored_count} new triples from second pass")
                return stored_count

            return 0
        else:
            logger.info("Coverage sufficient after first pass, no iterative research needed")
            return 0

    except Exception as e:
        logger.warning(f"Iterative research failed (non-critical): {e}")
        return 0


def cleanup_intermediate_data(job_id, db):
    deleted = 0
    deleted += db.query(GraphTriple).filter(GraphTriple.job_id == job_id).delete()
    deleted += db.query(Chunk).filter(Chunk.job_id == job_id).delete()
    deleted += db.query(CrawledPage).filter(CrawledPage.job_id == job_id).delete()
    db.commit()
    return deleted


def run_pipeline(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        logger.info(f"=== PIPELINE START: Job {job_id} - '{job.topic}' ===")

        job.status = "generating_urls"
        db.commit()
        logger.info(f"Step 1: Generating source URLs for '{job.topic}'")
        urls = generate_source_urls(job.topic)
        logger.info(f"Step 1 complete: {len(urls)} source URLs generated")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        job = db.get(Job, job_id)
        job.status = "crawling"
        db.commit()
        logger.info(f"Step 2: Mass crawling web sources")
        crawl_results = mass_crawl(urls, job_id)
        logger.info(f"Step 2 complete: {len(crawl_results)} pages crawled")

        try:
            discovered_links = []
            crawled_urls_set = set(r.get("url", "") for r in crawl_results)
            for r in crawl_results:
                content = r.get("content", "")
                source_url = r.get("url", "")
                if content and source_url:
                    links = extract_links_from_content(content, source_url, job.topic)
                    for link_url, score in links:
                        if link_url not in crawled_urls_set and score > 0:
                            discovered_links.append(link_url)
                            crawled_urls_set.add(link_url)

            if discovered_links:
                discovered_links = discovered_links[:5]
                validated_links = validate_urls(discovered_links, timeout=8)
                if validated_links:
                    logger.info(f"Step 2b: Following {len(validated_links)} discovered links from crawled pages")
                    extra_results = mass_crawl(validated_links, job_id)
                    crawl_results.extend(extra_results)
                    logger.info(f"Step 2b complete: {len(extra_results)} additional pages from discovered links (total: {len(crawl_results)})")
        except Exception as e:
            logger.warning(f"Link discovery from crawled pages failed (non-critical): {e}")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        if not crawl_results:
            job = db.get(Job, job_id)
            job.status = "error"
            job.error_message = "No content found from web crawling"
            db.commit()
            logger.error(f"Pipeline failed: no content found for '{job.topic}'")
            return

        job = db.get(Job, job_id)
        job.status = "chunking"
        db.commit()
        logger.info(f"Step 3: Chunking crawled content")
        chunk_count = process_chunks(job_id)
        logger.info(f"Step 3 complete: {chunk_count} chunks created")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        logger.info(f"Step 4: Running reasoning pipeline (direct triple extraction → coverage check)")
        triples = run_reasoning_pipeline(job_id)
        logger.info(f"Step 4 complete: {len(triples)} knowledge triples")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        if not triples:
            job = db.get(Job, job_id)
            job.status = "error"
            job.error_message = "Reasoning pipeline produced no knowledge triples"
            db.commit()
            logger.error(f"Pipeline failed: no triples for '{job.topic}'")
            return

        logger.info(f"Step 4c: Iterative deep research")
        chunks = db.query(Chunk).filter(Chunk.job_id == job_id).all()
        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
        page_lookup = {p.id: p for p in pages}
        new_triple_count = iterative_research(job_id, job.topic, triples, chunks, page_lookup, db)
        if new_triple_count > 0:
            logger.info(f"Step 4c complete: {new_triple_count} additional triples from iterative research")
        else:
            logger.info(f"Step 4c complete: no additional triples needed")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        logger.info(f"Step 4d: Entity Resolution")
        try:
            all_triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()
            unique_triples, changed, dedup_count = resolve_triples(all_triples)
            if dedup_count > 0:
                unique_ids = set(t.id for t in unique_triples)
                for t in all_triples:
                    if t.id not in unique_ids:
                        db.delete(t)
                db.commit()
            elif changed > 0:
                db.commit()
            logger.info(f"Step 4d complete: {changed} entities normalized, {dedup_count} duplicates removed")
        except Exception as e:
            logger.warning(f"Entity resolution failed (non-critical): {e}")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        logger.info(f"Step 4e: Contradiction Detection")
        try:
            all_triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()
            contradictions = detect_contradictions(all_triples)
            if contradictions:
                resolved = resolve_contradictions(contradictions, db)
                logger.info(f"Step 4e complete: {len(contradictions)} contradictions found, {resolved} resolved")
            else:
                logger.info(f"Step 4e complete: no contradictions found")
        except Exception as e:
            logger.warning(f"Contradiction detection failed (non-critical): {e}")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        logger.info(f"Step 4f: Community Detection")
        try:
            from hiveai.pipeline.communities import build_communities
            communities = build_communities(job_id)
            if communities:
                logger.info(f"Step 4f complete: {len(communities)} communities detected")
            else:
                logger.info(f"Step 4f complete: no communities detected")
        except Exception as e:
            logger.warning(f"Community detection failed (non-critical): {e}")

        if is_job_cancelled(job_id, db):
            logger.info(f"Job {job_id} cancelled by user")
            job = db.get(Job, job_id)
            job.status = "cancelled"
            db.commit()
            return

        logger.info(f"Step 4b: Checking for overlapping knowledge (Lego mode)")
        try:
            from hiveai.pipeline.graph_merger import build_knowledge_audit
            audit_text, overlapping = build_knowledge_audit(job.topic, db)
            if overlapping:
                for overlap in overlapping:
                    logger.info(f"  Related book found: '{overlap.get('title', 'unknown')}' ({overlap.get('matching_sections', 0)} matching sections)")
                logger.info(f"  Writer will use Lego mode: referencing {len(overlapping)} existing books, writing only novel content")
            else:
                logger.info(f"  No overlapping books found — this will be a standalone book")
        except Exception as e:
            logger.warning(f"  Knowledge audit failed (non-critical, writer will handle): {e}")

        logger.info(f"Step 5: Checking for duplicate Golden Books")
        replaced = check_and_replace_duplicate_book(job.topic, db)
        if replaced:
            logger.info(f"Replaced existing book '{replaced.title}' (id={replaced.id}) for topic '{job.topic}'")

        logger.info(f"Step 6: Writing Golden Book")
        book = write_golden_book(job_id)

        if book:
            if book.quality_score is not None and book.quality_score < 0.5:
                logger.warning(f"LOW QUALITY ALERT: Book '{book.title}' scored {book.quality_score:.2f} - needs more research or rewriting")
                book.needs_rewrite = True
                db.commit()

            if book and book.quality_score is not None and book.quality_score < 0.5 and book.needs_rewrite:
                logger.info(f"Step 6b: Auto-rewriting low-quality book (score: {book.quality_score:.2f})")
                try:
                    from hiveai.pipeline.writer import rewrite_book
                    rewritten = rewrite_book(book.id)
                    if rewritten:
                        book = rewritten
                        db.refresh(book)
                        logger.info(f"Step 6b complete: book rewritten (new score: {book.quality_score})")
                except Exception as e:
                    logger.warning(f"Auto-rewrite failed (non-critical): {e}")

            cleanup_count = cleanup_intermediate_data(job_id, db)
            logger.info(f"Cleanup: removed {cleanup_count} intermediate records for job {job_id}")
            logger.info(f"=== PIPELINE COMPLETE: Job {job_id} - Golden Book '{book.title}' (quality: {book.quality_score}) ready for review ===")
        else:
            job = db.get(Job, job_id)
            job.status = "error"
            job.error_message = "Failed to generate Golden Book"
            db.commit()
            logger.error(f"Pipeline failed: could not write Golden Book for '{job.topic}'")

    except Exception as e:
        logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = "error"
                job.error_message = str(e)[:1000]
            db.commit()
        except:
            pass
    finally:
        db.close()
