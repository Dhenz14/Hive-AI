"""
Reciprocal Rank Fusion (RRF) — merge results from multiple retrieval sources.

Used to combine results from:
- Primary hybrid search + HyDE search
- Multiple sub-query searches (query decomposition)
- Any other multi-source retrieval

Reference: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and
individual Rank Learning Methods" (2009)
"""
import logging

logger = logging.getLogger(__name__)

_RRF_K = 60  # Standard RRF constant (used by Elasticsearch)


def rrf_merge(result_lists: list[list[dict]], k: int = _RRF_K,
              limit: int = 12, id_key: str = "id") -> list[dict]:
    """
    Merge multiple ranked result lists using Reciprocal Rank Fusion.

    Each result_list is a list of section dicts, ordered best-first.
    Sections are identified by id_key (default "id").

    Returns a single merged list sorted by fused RRF score, best first.
    """
    if not result_lists:
        return []
    if len(result_lists) == 1:
        return result_lists[0][:limit]

    # Build per-section RRF scores across all lists
    scores: dict = {}  # id -> float
    sections: dict = {}  # id -> dict (keep the best copy)

    for result_list in result_lists:
        for rank, section in enumerate(result_list):
            sid = section.get(id_key)
            if sid is None:
                # Sections without ID (e.g. community summaries) — use content hash
                sid = hash(section.get("content", "")[:200])
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
            if sid not in sections:
                sections[sid] = section

    # Sort by fused score, best first
    ranked = sorted(scores.keys(), key=lambda sid: scores[sid], reverse=True)

    merged = []
    for sid in ranked[:limit]:
        section = dict(sections[sid])  # shallow copy — don't mutate originals (may be cached)
        section["rrf_score"] = round(scores[sid], 4)
        merged.append(section)

    logger.debug(f"RRF merge: {len(result_lists)} lists, {sum(len(rl) for rl in result_lists)} total → {len(merged)} merged")
    return merged
