"""
RAG Quality Metrics Tracker — rolling per-domain quality signals.

Tracks metrics over a 7-day window that feed Smart Target thresholds:
- Retrieval miss rate (CRAG verdict = "incorrect")
- Low confidence rate (confidence band = "low")
- Verification failure rate (code verification fails)
- Solved example reuse rate (how often solved examples appear in results)
- Auto-stage rate (rate of verified pairs being auto-staged)

Metrics are stored as daily rollups in a JSON file alongside score_ledger.json.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

_METRICS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rag_metrics.json"
)
_metrics_lock = threading.Lock()

# In-memory counters for the current day (flushed to disk periodically)
_daily_counters: dict[str, dict] = defaultdict(lambda: {
    "total_queries": 0,
    "crag_correct": 0,
    "crag_ambiguous": 0,
    "crag_incorrect": 0,
    "confidence_high": 0,
    "confidence_medium": 0,
    "confidence_low": 0,
    "verification_pass": 0,
    "verification_fail": 0,
    "solved_example_retrieved": 0,
    "auto_staged": 0,
    "auto_promoted": 0,
})
_counters_dirty = False


def record_query(domain: str = "general", crag_verdict: str = "correct",
                 confidence_band: str = "none", verification_passed: bool | None = None,
                 solved_example_retrieved: bool = False,
                 auto_staged: bool = False, auto_promoted: bool = False):
    """Record a single query's RAG metrics. Called from chat endpoints."""
    global _counters_dirty
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{today}|{domain}"

    with _metrics_lock:
        c = _daily_counters[key]
        c["total_queries"] += 1

        if crag_verdict == "correct":
            c["crag_correct"] += 1
        elif crag_verdict == "ambiguous":
            c["crag_ambiguous"] += 1
        elif crag_verdict == "incorrect":
            c["crag_incorrect"] += 1

        if confidence_band == "high":
            c["confidence_high"] += 1
        elif confidence_band == "medium":
            c["confidence_medium"] += 1
        elif confidence_band == "low":
            c["confidence_low"] += 1

        if verification_passed is True:
            c["verification_pass"] += 1
        elif verification_passed is False:
            c["verification_fail"] += 1

        if solved_example_retrieved:
            c["solved_example_retrieved"] += 1
        if auto_staged:
            c["auto_staged"] += 1
        if auto_promoted:
            c["auto_promoted"] += 1

        _counters_dirty = True

    # Auto-flush every 50 queries
    if c["total_queries"] % 50 == 0:
        flush_metrics()


def flush_metrics():
    """Write in-memory counters to disk."""
    global _counters_dirty
    with _metrics_lock:
        if not _counters_dirty:
            return
        try:
            existing = _load_metrics_file()
            for key, counters in _daily_counters.items():
                if key in existing:
                    # Merge: take max of each counter (idempotent)
                    for field, val in counters.items():
                        existing[key][field] = max(existing[key].get(field, 0), val)
                else:
                    existing[key] = dict(counters)

            with open(_METRICS_FILE, "w") as f:
                json.dump(existing, f, indent=2)
            _counters_dirty = False
        except Exception as e:
            logger.warning(f"Failed to flush RAG metrics: {e}")


def _load_metrics_file() -> dict:
    """Load metrics from disk."""
    try:
        if os.path.exists(_METRICS_FILE):
            with open(_METRICS_FILE) as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load RAG metrics file: {e}")
    return {}


def get_domain_metrics(domain: str, days: int = 7) -> dict:
    """
    Compute rolling metrics for a domain over the last N days.

    Returns:
        {
            "domain": str,
            "window_days": int,
            "total_queries": int,
            "retrieval_miss_rate": float,  # crag_incorrect / total
            "low_confidence_rate": float,  # confidence_low / total
            "verification_fail_rate": float,  # fail / (pass + fail)
            "solved_example_reuse_rate": float,
            "auto_stage_rate": float,
        }
    """
    flush_metrics()
    all_data = _load_metrics_file()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    totals = defaultdict(int)

    for key, counters in all_data.items():
        date_str, dom = key.split("|", 1) if "|" in key else (key, "general")
        if dom != domain or date_str < cutoff:
            continue
        for field, val in counters.items():
            totals[field] += val

    total = totals["total_queries"]
    if total == 0:
        return {
            "domain": domain, "window_days": days, "total_queries": 0,
            "retrieval_miss_rate": 0.0, "low_confidence_rate": 0.0,
            "verification_fail_rate": 0.0, "solved_example_reuse_rate": 0.0,
            "auto_stage_rate": 0.0,
        }

    verify_total = totals["verification_pass"] + totals["verification_fail"]

    return {
        "domain": domain,
        "window_days": days,
        "total_queries": total,
        "retrieval_miss_rate": round(totals["crag_incorrect"] / total, 3),
        "low_confidence_rate": round(totals["confidence_low"] / total, 3),
        "verification_fail_rate": round(
            totals["verification_fail"] / verify_total if verify_total > 0 else 0.0, 3),
        "solved_example_reuse_rate": round(totals["solved_example_retrieved"] / total, 3),
        "auto_stage_rate": round(totals["auto_staged"] / total, 3),
    }


def get_all_domain_metrics(days: int = 7) -> dict[str, dict]:
    """Get metrics for all domains that have data."""
    flush_metrics()
    all_data = _load_metrics_file()

    domains = set()
    for key in all_data:
        if "|" in key:
            domains.add(key.split("|", 1)[1])

    return {domain: get_domain_metrics(domain, days) for domain in sorted(domains)}
