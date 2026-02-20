import logging
import re
import numpy as np
from hiveai.config import CHUNK_SIZE, CHUNK_OVERLAP, SEMANTIC_CHUNKING
from hiveai.models import SessionLocal, CrawledPage, Chunk, Job

try:
    import semchunk
    SEMCHUNK_AVAILABLE = True
except ImportError:
    SEMCHUNK_AVAILABLE = False

logger = logging.getLogger(__name__)

ERROR_PAGE_PATTERNS = ["404", "Not Found", "Page not found", "Access Denied"]


def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', ' ', text)
    text = text.strip()
    return text


def _chunk_text_legacy(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    overlap_text = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" + para if current_chunk else para)
        else:
            if current_chunk:
                chunks.append(current_chunk)
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            
            if len(para) > chunk_size:
                words = para.split()
                sub_chunk = ""
                for word in words:
                    if len(sub_chunk) + len(word) + 1 <= chunk_size:
                        sub_chunk += (" " + word if sub_chunk else word)
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk)
                            overlap_text = sub_chunk[-overlap:] if len(sub_chunk) > overlap else sub_chunk
                        sub_chunk = word
                if sub_chunk:
                    current_chunk = sub_chunk
                    if overlap_text and len(overlap_text) + len(current_chunk) <= chunk_size:
                        current_chunk = overlap_text + " " + current_chunk
            else:
                current_chunk = para
                if overlap_text and len(overlap_text) + len(para) + 2 <= chunk_size:
                    current_chunk = overlap_text + "\n\n" + para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if SEMCHUNK_AVAILABLE:
        try:
            chunker = semchunk.chunkerify(lambda t: len(t.split()), chunk_size=chunk_size)
            chunks = chunker.chunk(text)
            if chunks:
                return chunks
        except Exception:
            pass
    
    return _chunk_text_legacy(text, chunk_size=chunk_size, overlap=overlap)


def _semantic_chunk(text, min_chunk_size=200, max_chunk_size=3000):
    """Split text into semantically coherent chunks using embedding similarity."""
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) < 4:
        return None

    try:
        from hiveai.llm.client import embed_texts
        embeddings = embed_texts(sentences)
        if not embeddings or len(embeddings) != len(sentences):
            return None
    except Exception:
        return None

    similarities = []
    for i in range(len(embeddings) - 1):
        a = np.array(embeddings[i])
        b = np.array(embeddings[i + 1])
        sim = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)
        similarities.append(sim)

    if not similarities:
        return None
    mean_sim = np.mean(similarities)
    std_sim = np.std(similarities)
    threshold = mean_sim - std_sim
    threshold = max(threshold, 0.3)

    chunks = []
    current_chunk = [sentences[0]]
    current_len = len(sentences[0])

    for i, sim in enumerate(similarities):
        next_sentence = sentences[i + 1]
        next_len = len(next_sentence)

        if sim < threshold and current_len >= min_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = [next_sentence]
            current_len = next_len
        elif current_len + next_len > max_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = [next_sentence]
            current_len = next_len
        else:
            current_chunk.append(next_sentence)
            current_len += next_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    merged = []
    for chunk in chunks:
        if merged and len(chunk) < min_chunk_size:
            merged[-1] = merged[-1] + " " + chunk
        else:
            merged.append(chunk)

    if not merged:
        return None

    logger.info(f"Semantic chunking: {len(merged)} chunks from {len(sentences)} sentences (threshold={threshold:.3f})")
    return merged


def _is_error_page(content):
    for pattern in ERROR_PAGE_PATTERNS:
        if pattern.lower() in content.lower():
            pattern_ratio = len(pattern) / len(content)
            if pattern_ratio > 0.05:
                return True
    return False


def _generate_page_context(page):
    try:
        from hiveai.llm.client import fast, clean_llm_response
        from hiveai.llm.prompts import CHUNK_CONTEXT_PROMPT

        title = page.title or page.url or "Unknown"
        content = page.cleaned_markdown or page.raw_content or ""
        preview = content[:500]

        prompt = CHUNK_CONTEXT_PROMPT.format(title=title, preview=preview)
        response = fast(prompt, max_tokens=256)
        if response:
            summary = clean_llm_response(response)
            if summary and len(summary) > 5:
                logger.info(f"Generated context for page {page.id}: {summary[:80]}...")
                return summary
    except Exception as e:
        logger.warning(f"Context generation failed for page {page.id}: {e}")

    return None


def process_chunks(job_id):
    db = SessionLocal()
    try:
        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
        total_chunks = 0
        seen_contents = set()

        for page in pages:
            content = page.cleaned_markdown or page.raw_content
            if not content:
                continue

            context_summary = _generate_page_context(page)
            if context_summary:
                context_prefix = f"[Context: {context_summary}]\n\n"
            else:
                context_prefix = f"[Source: {page.url}]\n\n"
                logger.info(f"Using fallback context for page {page.id}: {page.url}")

            semantic_chunks = _semantic_chunk(content) if SEMANTIC_CHUNKING else None
            if semantic_chunks is not None:
                text_chunks = semantic_chunks
            else:
                logger.info(f"Falling back to fixed-size chunking for page {page.id}")
                text_chunks = chunk_text(content)
            for i, chunk_text_content in enumerate(text_chunks):
                if len(chunk_text_content.strip()) < 100:
                    continue
                if chunk_text_content in seen_contents:
                    continue
                if _is_error_page(chunk_text_content):
                    continue
                seen_contents.add(chunk_text_content)
                contextualized_content = context_prefix + chunk_text_content
                chunk = Chunk(
                    job_id=job_id,
                    page_id=page.id,
                    content=contextualized_content,
                    chunk_index=i,
                    token_count=len(contextualized_content.split()),
                )
                db.add(chunk)
                total_chunks += 1

        job = db.get(Job, job_id)
        if job:
            job.chunk_count = total_chunks
            job.status = "chunked"
        db.commit()

        logger.info(f"Chunking complete: {total_chunks} chunks from {len(pages)} pages for job {job_id}")
        return total_chunks
    finally:
        db.close()
