"""
Contextual Compression — extract only query-relevant sentences from sections.

After retrieval and reranking, long sections often contain 80% irrelevant content.
This module uses the fast model to extract only the sentences that matter,
dramatically improving context density and token efficiency.

Only triggers for sections >500 words in tight-budget mode (executable_code).
"""
import logging
import hashlib
import threading

logger = logging.getLogger(__name__)

from collections import OrderedDict
_compress_cache: OrderedDict = OrderedDict()
_compress_cache_lock = threading.Lock()
_COMPRESS_CACHE_MAX = 100
_MIN_WORDS_TO_COMPRESS = 500

_COMPRESS_PROMPT = """Extract ONLY the sentences from this text that are directly relevant to answering the query. Return the extracted sentences verbatim — do not summarize, rephrase, or add commentary. If nothing is relevant, return "NONE".

Query: {query}

Text:
{content}

Relevant sentences:"""


def compress_section(query: str, content: str) -> str:
    """
    Extract query-relevant sentences from a section.
    Returns compressed content, or original if compression fails or isn't needed.
    """
    words = content.split()
    if len(words) < _MIN_WORDS_TO_COMPRESS:
        return content

    cache_key = hashlib.md5(f"{query}|{content}".encode()).hexdigest()
    with _compress_cache_lock:
        if cache_key in _compress_cache:
            return _compress_cache[cache_key]

    try:
        from hiveai.llm.client import fast

        result = fast(
            _COMPRESS_PROMPT.format(query=query, content=content[:3000]),
            max_tokens=1024,
        )
        if not result or result.strip().upper() == "NONE" or len(result.strip()) < 20:
            # Nothing relevant found — return first 500 words as fallback
            compressed = " ".join(words[:500])
        else:
            compressed = result.strip()

        with _compress_cache_lock:
            if cache_key in _compress_cache:
                _compress_cache.move_to_end(cache_key)
            _compress_cache[cache_key] = compressed
            while len(_compress_cache) > _COMPRESS_CACHE_MAX:
                _compress_cache.popitem(last=False)

        ratio = len(compressed) / max(len(content), 1)
        logger.debug(f"Compressed section: {len(content)} → {len(compressed)} chars ({ratio:.0%})")
        return compressed

    except Exception as e:
        logger.warning(f"Contextual compression failed (using original): {e}")
        return content


def compress_sections(query: str, sections: list[dict], max_compress: int = 3) -> list[dict]:
    """
    Compress up to max_compress long sections.
    Returns a NEW list with shallow-copied dicts — originals (and RAG cache) are never mutated.
    """
    result = []
    compressed_count = 0
    for section in sections:
        content = section.get("content", "")
        if compressed_count < max_compress and len(content.split()) >= _MIN_WORDS_TO_COMPRESS:
            section = dict(section)  # shallow copy before mutation
            section["content"] = compress_section(query, content)
            compressed_count += 1
        result.append(section)
    if compressed_count:
        logger.info(f"Compressed {compressed_count}/{len(sections)} sections for query: {query[:50]}")
    return result
