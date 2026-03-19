"""
HyDE — Hypothetical Document Embeddings

For "how to" / code generation queries, generate a short hypothetical answer
via the fast model, embed THAT, and search for similar real documents.
The hypothetical answer lives in the same semantic space as real answers,
giving dramatically better recall than embedding the question alone.

Reference: Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels" (2022)
"""
import logging
import hashlib
import threading

logger = logging.getLogger(__name__)

# Cache hypothetical embeddings to avoid redundant LLM + embed calls
_hyde_cache: dict[str, list[float]] = {}
_hyde_cache_lock = threading.Lock()
_HYDE_CACHE_MAX = 200

_HYDE_PROMPT = """Write a short technical answer (2-3 paragraphs, with code if appropriate) to this question. Be specific and use real API names, function signatures, and concrete examples.

Question: {query}

Answer:"""


def generate_hyde_embedding(query: str) -> list[float] | None:
    """
    Generate a hypothetical answer, embed it, return the embedding.
    Returns None if generation or embedding fails.
    Cost: ~200ms (1 fast LLM call + 1 embed call), cached per query.
    """
    cache_key = hashlib.md5(query.lower().strip().encode()).hexdigest()

    with _hyde_cache_lock:
        if cache_key in _hyde_cache:
            return _hyde_cache[cache_key]

    try:
        from hiveai.llm.client import fast, embed_text

        hypothetical = fast(_HYDE_PROMPT.format(query=query), max_tokens=512)
        if not hypothetical or len(hypothetical.strip()) < 20:
            logger.debug(f"HyDE: hypothetical too short for query: {query[:50]}")
            return None

        embedding = embed_text(hypothetical)
        if not embedding:
            return None

        with _hyde_cache_lock:
            if len(_hyde_cache) >= _HYDE_CACHE_MAX:
                # Evict oldest (FIFO is fine here — small cache, infrequent eviction)
                oldest_key = next(iter(_hyde_cache))
                del _hyde_cache[oldest_key]
            _hyde_cache[cache_key] = embedding

        logger.info(f"HyDE: generated hypothetical ({len(hypothetical)} chars) for: {query[:50]}")
        return embedding

    except Exception as e:
        logger.warning(f"HyDE generation failed (non-critical): {e}")
        return None


def should_use_hyde(top_distance: float, intent: str = "") -> bool:
    """
    Decide whether to trigger HyDE based on initial retrieval quality.
    Only fires when top result is weak (high distance) and query is code/doc-related.
    """
    # Only for intents where a hypothetical answer makes sense
    _hyde_intents = {"code_question", "doc_lookup", "debugging", ""}
    if intent and intent not in _hyde_intents:
        return False
    # Trigger when best result has cosine distance > 0.35 (similarity < 0.65)
    return top_distance > 0.35
