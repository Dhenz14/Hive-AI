"""
CRAG — Corrective Retrieval-Augmented Generation

After retrieval, before generation, the fast model assesses context quality:
- CORRECT:   Retrieved docs directly answer the query → use context as-is
- AMBIGUOUS: Related but incomplete → supplement with HyDE or decomposition
- INCORRECT: Irrelevant docs → drop RAG context, let model use parametric knowledge

This prevents misleading context from degrading answers. Adds ~100-200ms
per query (one fast model call).

Reference: Yan et al., "Corrective Retrieval Augmented Generation" (2024)
"""
import logging
import hashlib
import threading

logger = logging.getLogger(__name__)

from collections import OrderedDict
_judge_cache: OrderedDict = OrderedDict()
_judge_cache_lock = threading.Lock()
_JUDGE_CACHE_MAX = 200

# Verdicts
CORRECT = "correct"
AMBIGUOUS = "ambiguous"
INCORRECT = "incorrect"

_JUDGE_PROMPT = """You are a retrieval quality judge. Given a user's query and retrieved documents, assess whether the documents are relevant enough to answer the query.

Query: {query}

Retrieved documents (showing headers and first 200 chars of each):
{context_sample}

Rate the retrieval quality as exactly one word:
- CORRECT: documents directly and sufficiently answer the query
- AMBIGUOUS: documents are related but insufficient or only partially relevant
- INCORRECT: documents are irrelevant to the query

Rating:"""


def judge_retrieval(query: str, sections: list[dict]) -> str:
    """
    Assess retrieval quality. Returns 'correct', 'ambiguous', or 'incorrect'.
    Cached per (query, top section IDs) to avoid redundant LLM calls.
    """
    if not sections:
        return INCORRECT

    # Cache key includes query + top section IDs (retrieval may vary)
    _section_ids = "-".join(str(s.get("id", "")) for s in sections[:5])
    cache_key = hashlib.md5(f"{query}|{_section_ids}".encode()).hexdigest()

    with _judge_cache_lock:
        if cache_key in _judge_cache:
            return _judge_cache[cache_key]

    try:
        from hiveai.llm.client import fast

        # Build context sample — headers + truncated content
        lines = []
        for i, s in enumerate(sections[:5]):
            header = s.get("header", "untitled")
            content = (s.get("content") or "")[:200].replace("\n", " ")
            lines.append(f"[{i+1}] {header}: {content}")
        context_sample = "\n".join(lines)

        result = fast(
            _JUDGE_PROMPT.format(query=query, context_sample=context_sample),
            max_tokens=20,
        )
        if not result:
            logger.warning("CRAG judge returned empty — defaulting to AMBIGUOUS")
            return AMBIGUOUS  # fail-safe: empty response → don't assume quality

        verdict = result.strip().upper()
        if "INCORRECT" in verdict:
            out = INCORRECT
        elif "AMBIGUOUS" in verdict:
            out = AMBIGUOUS
        else:
            out = CORRECT

        with _judge_cache_lock:
            if cache_key in _judge_cache:
                _judge_cache.move_to_end(cache_key)
            _judge_cache[cache_key] = out
            while len(_judge_cache) > _JUDGE_CACHE_MAX:
                _judge_cache.popitem(last=False)

        logger.info(f"CRAG judge: {out} for '{query[:50]}' ({len(sections)} sections)")
        return out

    except Exception as e:
        logger.warning(f"CRAG judge failed (defaulting to ambiguous): {e}")
        return AMBIGUOUS  # fail-safe: broken judge → supplemental retrieval, not blind trust
