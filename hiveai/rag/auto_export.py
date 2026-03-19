"""
Auto-Export — export verified training pairs for retraining.

When a smart target fires, this module:
1. Queries TrainingPair for verified pairs in the target domain
2. Filters by quality >= 0.80
3. Exports to JSONL format compatible with train_v5.py
4. Writes to datasets/auto_<domain>_<timestamp>.jsonl
"""
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 3 levels up: auto_export.py → rag/ → hiveai/ → project root → datasets/
_DATASETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "datasets"
)


def export_domain_pairs(db, domain: str, min_quality: float = 0.80,
                        max_pairs: int = 500) -> dict:
    """
    Export verified training pairs for a domain to JSONL.

    Returns:
        {
            "domain": str,
            "path": str,  # path to exported JSONL
            "pair_count": int,
            "avg_quality": float,
        }
    """
    from hiveai.models import TrainingPair

    pairs = db.query(TrainingPair).filter(
        TrainingPair.is_eligible == True,
        TrainingPair.source.in_(["auto_verified", "human_verified"]),
        TrainingPair.quality >= min_quality,
        TrainingPair.topic.ilike(f"%{domain}%"),
    ).order_by(TrainingPair.quality.desc()).limit(max_pairs).all()

    if not pairs:
        return {"domain": domain, "path": None, "pair_count": 0, "avg_quality": 0.0}

    # Ensure datasets directory exists
    os.makedirs(_DATASETS_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"auto_{domain}_{timestamp}.jsonl"
    filepath = os.path.join(_DATASETS_DIR, filename)

    total_quality = 0.0
    with open(filepath, "w", encoding="utf-8") as f:
        for pair in pairs:
            entry = {
                "instruction": pair.instruction,
                "input": "",
                "output": pair.response,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            total_quality += pair.quality

    avg_quality = total_quality / len(pairs) if pairs else 0.0

    logger.info(f"Exported {len(pairs)} pairs for domain '{domain}' → {filepath} (avg quality: {avg_quality:.3f})")

    return {
        "domain": domain,
        "path": filepath,
        "pair_count": len(pairs),
        "avg_quality": round(avg_quality, 3),
    }
