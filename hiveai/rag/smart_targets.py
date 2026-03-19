"""
Smart Retrain Targets — per-domain thresholds that trigger retraining.

When RAG metrics cross thresholds for a domain, it means:
- The model consistently fails on that domain (high miss rate)
- Generated code is unreliable (high verification failure)
- Enough verified training data has accumulated to improve

This closes the self-improvement loop:
  RAG detects weakness → exports training data → model retrains →
  regression eval confirms → metrics improve → next domain targeted
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Thresholds that trigger a retrain for a domain
SMART_TARGETS = {
    # >30% of queries have irrelevant retrieval → model doesn't know this domain
    "retrieval_miss_rate": 0.30,
    # >20% of code verifications fail → model generates bad code here
    "verification_fail_rate": 0.20,
    # >40% of queries have low confidence → knowledge base gaps
    "low_confidence_rate": 0.40,
    # Need at least 50 verified pairs to retrain meaningfully
    "min_training_pairs": 50,
    # Don't retrain more than once per week
    "min_days_since_retrain": 7,
    # Minimum queries to evaluate (avoid triggering on tiny samples)
    "min_queries_for_evaluation": 20,
}

_RETRAIN_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "retrain_history.json"
)


def _load_retrain_history() -> dict:
    """Load retrain history from disk."""
    try:
        if os.path.exists(_RETRAIN_HISTORY_FILE):
            with open(_RETRAIN_HISTORY_FILE) as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_retrain_history(history: dict):
    """Save retrain history to disk."""
    try:
        with open(_RETRAIN_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except IOError as e:
        logger.warning(f"Failed to save retrain history: {e}")


def record_retrain(domain: str, version: str, pair_count: int):
    """Record that a retrain was triggered for a domain."""
    history = _load_retrain_history()
    history[domain] = {
        "last_retrain": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "pair_count": pair_count,
    }
    _save_retrain_history(history)
    logger.info(f"Retrain recorded: {domain} → {version} ({pair_count} pairs)")


def days_since_retrain(domain: str) -> float:
    """Days since last retrain for a domain. Returns inf if never retrained."""
    history = _load_retrain_history()
    entry = history.get(domain)
    if not entry or "last_retrain" not in entry:
        return float("inf")
    try:
        last = datetime.fromisoformat(entry["last_retrain"])
        delta = datetime.now(timezone.utc) - last
        return delta.total_seconds() / 86400
    except (ValueError, TypeError):
        return float("inf")


def evaluate_smart_targets(db) -> dict[str, dict]:
    """
    Evaluate all domains against smart targets.

    Returns:
        {
            "domain_name": {
                "triggered": bool,
                "reasons": ["retrieval_miss_rate: 0.35 > 0.30", ...],
                "available_pairs": int,
                "metrics": {...},
                "days_since_retrain": float,
                "blocked_reason": str | None,
            }
        }
    """
    from hiveai.rag.metrics import get_all_domain_metrics
    from hiveai.models import TrainingPair

    all_metrics = get_all_domain_metrics(days=7)
    results = {}

    for domain, metrics in all_metrics.items():
        total = metrics.get("total_queries", 0)
        result = {
            "triggered": False,
            "reasons": [],
            "available_pairs": 0,
            "metrics": metrics,
            "days_since_retrain": round(days_since_retrain(domain), 1),
            "blocked_reason": None,
        }

        # Count available verified training pairs for this domain
        pair_count = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.source.in_(["auto_verified", "human_verified"]),
            TrainingPair.quality >= 0.80,
            TrainingPair.topic.ilike(f"%{domain}%"),
        ).count()
        result["available_pairs"] = pair_count

        # Check minimum query threshold
        if total < SMART_TARGETS["min_queries_for_evaluation"]:
            result["blocked_reason"] = f"insufficient data ({total} queries, need {SMART_TARGETS['min_queries_for_evaluation']})"
            results[domain] = result
            continue

        # Check cooldown
        _days = days_since_retrain(domain)
        if _days < SMART_TARGETS["min_days_since_retrain"]:
            result["blocked_reason"] = f"cooldown ({_days:.1f} days since last retrain, need {SMART_TARGETS['min_days_since_retrain']})"
            results[domain] = result
            continue

        # Check minimum pairs
        if pair_count < SMART_TARGETS["min_training_pairs"]:
            result["blocked_reason"] = f"insufficient pairs ({pair_count}, need {SMART_TARGETS['min_training_pairs']})"
            results[domain] = result
            continue

        # Evaluate metric thresholds
        triggered = False
        miss_rate = metrics.get("retrieval_miss_rate", 0)
        if miss_rate > SMART_TARGETS["retrieval_miss_rate"]:
            result["reasons"].append(f"retrieval_miss_rate: {miss_rate} > {SMART_TARGETS['retrieval_miss_rate']}")
            triggered = True

        fail_rate = metrics.get("verification_fail_rate", 0)
        if fail_rate > SMART_TARGETS["verification_fail_rate"]:
            result["reasons"].append(f"verification_fail_rate: {fail_rate} > {SMART_TARGETS['verification_fail_rate']}")
            triggered = True

        low_conf = metrics.get("low_confidence_rate", 0)
        if low_conf > SMART_TARGETS["low_confidence_rate"]:
            result["reasons"].append(f"low_confidence_rate: {low_conf} > {SMART_TARGETS['low_confidence_rate']}")
            triggered = True

        result["triggered"] = triggered
        results[domain] = result

    return results
