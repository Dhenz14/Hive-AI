import logging
import json
import re
import concurrent.futures
from hiveai.models import SessionLocal, Chunk, GraphTriple, CrawledPage, Job
from hiveai.llm.client import fast, fast_structured, reason, reason_structured, clean_llm_response
from hiveai.llm.client import TripleExtractionResult
from hiveai.llm.prompts import DIRECT_TRIPLE_EXTRACTION_PROMPT, COVERAGE_CHECK_PROMPT, TRIPLE_VERIFICATION_PROMPT
from hiveai.config import LLM_WORKERS, MAX_CHUNK_TEXT_FOR_LLM, EXTRACTION_QUALITY
from hiveai.pipeline.authority import adjust_triple_confidence, get_domain_authority

logger = logging.getLogger(__name__)

PROMPT_OVERHEAD_TOKENS = 800
TARGET_BATCH_TOKENS = 2000
MAX_BATCH_TOKENS = 3000


def parse_json_response(text):
    text = clean_llm_response(text)

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return []


def _build_smart_batches(chunks):
    batches = []
    current_batch = []
    current_tokens = 0

    for chunk in chunks:
        chunk_tokens = chunk.token_count or len(chunk.content.split())
        if current_tokens + chunk_tokens > MAX_BATCH_TOKENS and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(chunk)
        current_tokens += chunk_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def _get_chunk_source_url(chunk, page_lookup):
    page = page_lookup.get(chunk.page_id)
    if page:
        return page.url
    return None


def _extract_triples_batch(batch, batch_num, total_batches, page_lookup):
    chunk_sections = []
    chunk_meta = []
    for c in batch:
        url = _get_chunk_source_url(c, page_lookup)
        chunk_sections.append(c.content)
        chunk_meta.append({"chunk_id": c.id, "source_url": url})

    combined_text = "\n\n---\n\n".join(chunk_sections)

    max_chars = min(MAX_CHUNK_TEXT_FOR_LLM, 12000)
    if len(combined_text) > max_chars:
        combined_text = combined_text[:max_chars]

    try:
        prompt = DIRECT_TRIPLE_EXTRACTION_PROMPT.format(text=combined_text)
        triples = None

        use_reasoning = EXTRACTION_QUALITY == "high"
        struct_fn = reason_structured if use_reasoning else fast_structured
        fallback_fn = reason if use_reasoning else fast

        try:
            structured_result = struct_fn(prompt, TripleExtractionResult, max_tokens=4096)
            if structured_result is not None:
                triples = [t.model_dump() for t in structured_result.triples]
        except Exception:
            triples = None

        if triples is None:
            response = fallback_fn(prompt, max_tokens=4096)
            triples = parse_json_response(response)

        if isinstance(triples, list):
            valid = []
            for t in triples:
                if not isinstance(t, dict) or not t.get("subject") or not t.get("predicate") or not t.get("object"):
                    continue
                best_match = _match_triple_to_chunk(t, chunk_sections, chunk_meta)
                t["source_url"] = best_match.get("source_url")
                t["source_chunk_id"] = best_match.get("chunk_id")
                valid.append(t)
            logger.info(f"Extracted {len(valid)} triples from batch {batch_num}/{total_batches}")
            valid = _verify_triples_batch(valid)
            return valid
        logger.info(f"Extracted 0 triples from batch {batch_num}/{total_batches}")
        return []
    except Exception as e:
        logger.error(f"Triple extraction failed for batch {batch_num}: {e}")
        return []


def _verify_triples_batch(triples):
    if len(triples) <= 5:
        return triples

    triples_text = json.dumps(triples, indent=2)
    verify_fn = reason if EXTRACTION_QUALITY == "high" else fast
    try:
        prompt = TRIPLE_VERIFICATION_PROMPT.format(triples=triples_text)
        response = verify_fn(prompt, max_tokens=4096)
        verified = parse_json_response(response)
        if isinstance(verified, list) and len(verified) > 0:
            valid = [
                t for t in verified
                if isinstance(t, dict) and t.get("subject") and t.get("predicate") and t.get("object")
            ]
            if valid:
                logger.info(f"Verification: {len(triples)} → {len(valid)} triples ({len(triples) - len(valid)} removed/corrected)")
                return valid
        logger.warning("Verification returned empty or invalid result, keeping original triples")
        return triples
    except Exception as e:
        logger.warning(f"Triple verification failed, keeping original triples: {e}")
        return triples


def _match_triple_to_chunk(triple, chunk_sections, chunk_meta):
    subject = (triple.get("subject") or "").lower()
    obj = (triple.get("object") or "").lower()
    best_idx = 0
    best_score = 0
    for i, section in enumerate(chunk_sections):
        section_lower = section.lower()
        score = 0
        if subject in section_lower:
            score += 2
        if obj in section_lower:
            score += 1
        for word in subject.split():
            if len(word) > 3 and word in section_lower:
                score += 0.5
        if score > best_score:
            best_score = score
            best_idx = i
    return chunk_meta[best_idx]


BIBLIOGRAPHIC_PREDICATES = {
    "is studied in", "is discussed in", "is honored in", "is reviewed in",
    "is described in", "is mentioned in", "is explored in", "is analyzed in",
    "is presented in", "is examined in", "is covered in", "is referenced in",
}

def _is_low_quality_triple(triple):
    """Filter out vague, bibliographic, or meaningless triples."""
    obj = (triple.get("object") or "").strip()
    pred = (triple.get("predicate") or "").strip().lower()
    subj = (triple.get("subject") or "").strip()
    
    if pred in BIBLIOGRAPHIC_PREDICATES:
        return True
    
    if len(obj.split()) < 3 and not any(c.isdigit() for c in obj):
        vague_objects = {"a study", "in detail", "in context", "a certain color", "historical context", "various ways"}
        if obj.lower() in vague_objects or len(obj) < 5:
            return True
    
    if subj == obj:
        return True
    
    return False


def extract_triples(chunks, page_lookup):
    batches = _build_smart_batches(chunks)
    total_batches = len(batches)
    logger.info(f"Smart batching: {len(chunks)} chunks → {total_batches} batches (target {TARGET_BATCH_TOKENS} tokens each)")

    all_triples = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=LLM_WORKERS) as executor:
        futures = [
            executor.submit(_extract_triples_batch, batch, i + 1, total_batches, page_lookup)
            for i, batch in enumerate(batches)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            all_triples.extend(result)

    return all_triples


def check_coverage(triples, chunks):
    valid_triples = triples[:50]
    triples_text = "\n".join([f"({t['subject']}) --[{t['predicate']}]--> ({t['object']})" for t in valid_triples])
    chunks_text = "\n\n".join([c.content[:500] for c in chunks[:10]])

    try:
        prompt = COVERAGE_CHECK_PROMPT.format(triples=triples_text, chunks=chunks_text)
        response = fast(prompt, max_tokens=2048)
        if "COVERAGE_COMPLETE" in response:
            logger.info("Coverage check: complete")
            return []
        missing = parse_json_response(response)
        if isinstance(missing, list):
            logger.info(f"Coverage check: {len(missing)} missing facts found")
            return missing
        return []
    except Exception as e:
        logger.error(f"Coverage check failed: {e}")
        return []


def _build_coverage_triples(missing_facts, page_lookup):
    facts_text = "\n".join([f"- {f}" for f in missing_facts if f])
    combined = f"Convert these facts into knowledge graph triples:\n{facts_text}"
    try:
        prompt = DIRECT_TRIPLE_EXTRACTION_PROMPT.format(text=combined)
        response = fast(prompt, max_tokens=2048)
        triples = parse_json_response(response)
        if isinstance(triples, list):
            valid = [t for t in triples if isinstance(t, dict) and t.get("subject") and t.get("predicate") and t.get("object")]
            return valid
        return []
    except Exception as e:
        logger.error(f"Coverage triple building failed: {e}")
        return []


def run_reasoning_pipeline(job_id):
    db = SessionLocal()
    try:
        chunks = db.query(Chunk).filter(Chunk.job_id == job_id).all()
        if not chunks:
            logger.warning(f"No chunks found for job {job_id}")
            return []

        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
        page_lookup = {p.id: p for p in pages}

        job = db.get(Job, job_id)
        if job:
            job.status = "reasoning"
        db.commit()

        logger.info(f"Starting reasoning pipeline for job {job_id} with {len(chunks)} chunks")

        triples = extract_triples(chunks, page_lookup)
        logger.info(f"Total triples extracted: {len(triples)}")

        if not triples:
            return []

        missing_facts = check_coverage(triples, chunks)
        if missing_facts:
            extra_triples = _build_coverage_triples(missing_facts, page_lookup)
            triples.extend(extra_triples)
            logger.info(f"Added {len(extra_triples)} triples from coverage check")

        seen = set()
        unique_triples = []
        for t in triples:
            if not isinstance(t, dict):
                continue
            key = (
                (t.get("subject") or "").lower().strip(),
                (t.get("predicate") or "").lower().strip(),
                (t.get("object") or "").lower().strip(),
            )
            if key not in seen and all(key):
                seen.add(key)
                unique_triples.append(t)

        quality_filtered = 0
        filtered_triples = []
        for t in unique_triples:
            if _is_low_quality_triple(t):
                quality_filtered += 1
            else:
                filtered_triples.append(t)
        unique_triples = filtered_triples
        if quality_filtered > 0:
            logger.info(f"Quality filter: removed {quality_filtered} vague/bibliographic triples")

        low_conf_count = 0
        stored_triples = []
        triple_objects = []
        adjusted_count = 0
        authority_sum = 0.0

        for t in unique_triples:
            conf = t.get("confidence", 1.0)
            try:
                conf = float(conf)
            except (ValueError, TypeError):
                conf = 0.7

            source_url = t.get("source_url")
            if source_url:
                conf = adjust_triple_confidence(conf, source_url)
                adjusted_count += 1
                authority_sum += get_domain_authority(source_url)

            if conf < 0.5:
                low_conf_count += 1
                continue

            triple_objects.append(GraphTriple(
                job_id=job_id,
                subject=t.get("subject", "")[:500],
                predicate=t.get("predicate", "")[:200],
                obj=t.get("object", "")[:500],
                confidence=conf,
                source_chunk_id=t.get("source_chunk_id"),
                source_url=t.get("source_url", "")[:2000] if t.get("source_url") else None,
            ))
            stored_triples.append(t)

        if low_conf_count > 0:
            logger.info(f"Filtered {low_conf_count} low-confidence triples (< 0.5)")

        if adjusted_count > 0:
            avg_authority = authority_sum / adjusted_count
            logger.info(f"Authority adjustment: {adjusted_count} triples adjusted, avg authority: {avg_authority:.2f}")

        if triple_objects:
            db.add_all(triple_objects)

        if job:
            job.triple_count = len(stored_triples)
            job.status = "reasoned"
        db.commit()

        logger.info(f"Reasoning complete: {len(stored_triples)} unique triples stored for job {job_id}")
        return stored_triples

    except Exception as e:
        logger.error(f"Reasoning pipeline failed for job {job_id}: {e}")
        job = db.get(Job, job_id)
        if job:
            job.status = "error"
            job.error_message = str(e)
        db.commit()
        raise
    finally:
        db.close()
