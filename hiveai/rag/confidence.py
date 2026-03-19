"""
Retrieval Confidence Bands — signal to UI how well-supported an answer is.

Computes a confidence level from retrieval scores and CRAG verdict,
surfaced to the frontend as high/medium/low.

This enables:
- Users to know when answers are well-backed vs. guesses
- Smart retrain triggers (Phase 4) to detect knowledge gaps per domain
- Telemetry to track retrieval quality trends over time
"""
import logging

logger = logging.getLogger(__name__)


def compute_confidence(sections: list[dict], crag_verdict: str = "correct") -> dict:
    """
    Compute retrieval confidence from section scores and CRAG verdict.

    Returns:
        {
            "band": "high" | "medium" | "low" | "none",
            "score": float (0-1),
            "section_count": int,
            "crag_verdict": str,
        }
    """
    if not sections:
        return {"band": "none", "score": 0.0, "section_count": 0, "crag_verdict": crag_verdict}

    # Collect relevance scores (from hybrid_search or RRF)
    scores = []
    for s in sections[:5]:  # top 5 matter most
        score = s.get("relevance_score") or s.get("rrf_score") or 0.0
        scores.append(float(score))

    avg_score = sum(scores) / len(scores) if scores else 0.0
    top_score = max(scores) if scores else 0.0

    # Weighted confidence: 60% top score, 40% average (rewards one great match)
    raw_confidence = 0.6 * top_score + 0.4 * avg_score

    # CRAG verdict adjustment
    if crag_verdict == "incorrect":
        raw_confidence *= 0.3  # heavy penalty
    elif crag_verdict == "ambiguous":
        raw_confidence *= 0.7  # moderate penalty

    # Section count bonus (more relevant sections = higher confidence)
    count_bonus = min(len(sections) / 8.0, 1.0) * 0.1
    confidence = min(raw_confidence + count_bonus, 1.0)

    # Band thresholds
    if confidence >= 0.6:
        band = "high"
    elif confidence >= 0.3:
        band = "medium"
    else:
        band = "low"

    return {
        "band": band,
        "score": round(confidence, 3),
        "section_count": len(sections),
        "crag_verdict": crag_verdict,
    }
