"""
Lane A — Shadow Backtest Corpus

Reconstructs pseudo-critique-patterns from historical score_ledger.json for:
  - Dashboard/report rehearsal
  - Time-split logic testing
  - Probe-group leakage checks
  - Sample-size estimation per bucket
  - Reliability diagram rehearsal

GOVERNANCE BOUNDARY (NON-NEGOTIABLE):
  - Every record has synthetic_backtest=True
  - Every record has provenance="historical_reconstruction"
  - Every record has usable_for_live_calibration=False
  - Shadow data is stored in a SEPARATE file, never in the live critique book
  - Shadow data NEVER enters the live Beta posterior
  - The live confidence_calibrator.py ONLY reads from the critique memory book

This script produces shadow_backtest.json — a file that mimics the shape of
closed critique patterns but is explicitly marked as non-production data.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Governance flags — hardcoded, not configurable
_GOVERNANCE = {
    "synthetic_backtest": True,
    "provenance": "historical_reconstruction",
    "usable_for_live_calibration": False,
    "usable_for_dashboard_rehearsal": True,
    "warning": "This data is reconstructed from historical score_ledger.json. "
               "It does NOT carry real attempt_id lifecycle, real attribution, "
               "or real closure provenance. NEVER feed into live posterior.",
}

_DEFAULT_OUTPUT = "shadow_backtest.json"

# Success threshold — must match live system (scripts/critique_memory.py, docs/phase3_acceptance_gates.md)
_SUCCESS_THRESHOLD = 0.01


def load_score_ledger(path: str = None) -> dict:
    """Load score_ledger.json from WSL or Windows path."""
    candidates = [
        path,
        "score_ledger.json",
        "/opt/hiveai/project/score_ledger.json",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    raise FileNotFoundError("score_ledger.json not found")


def reconstruct_pseudo_patterns(ledger: dict) -> list:
    """
    Reconstruct pseudo-critique-patterns from version transitions in the ledger.

    For each consecutive version pair (sorted by timestamp), generate one
    pseudo-pattern per domain where the score changed. This mimics what
    critique_memory would have recorded if it existed during training.

    Returns list of pseudo-pattern dicts with governance flags.
    """
    # Sort versions by timestamp
    versions = []
    for key, data in ledger.items():
        if not isinstance(data, dict):
            continue
        ts = data.get("timestamp")
        if not ts:
            continue
        versions.append({"key": key, "data": data, "timestamp": ts})

    versions.sort(key=lambda v: v["timestamp"])

    patterns = []
    domains = ["cpp", "go", "hive", "js", "python", "rust"]

    for i in range(1, len(versions)):
        prev = versions[i - 1]
        curr = versions[i]

        prev_key = prev["key"]
        curr_key = curr["key"]
        is_failed = curr_key.startswith("failed/")

        for domain in domains:
            pre_score = prev["data"].get(domain)
            post_score = curr["data"].get(domain)

            if pre_score is None or post_score is None:
                continue

            delta = post_score - pre_score
            fix_succeeded = delta > _SUCCESS_THRESHOLD

            # Infer weakness_type from score level (coarse — this is reconstruction, not truth)
            if pre_score < 0.70:
                weakness_type = "compound"
            elif pre_score < 0.85:
                weakness_type = "keyword_only"
            elif pre_score < 0.95:
                weakness_type = "structure_only"
            else:
                weakness_type = "none"

            pattern = {
                # Governance flags (hardcoded, non-negotiable)
                **_GOVERNANCE,

                # Pseudo-critique fields (reconstructed, not real)
                "pseudo_attempt_id": f"shadow-{curr_key}-{domain}",
                "domain": domain,
                "probe_id": f"{domain}-aggregate",  # NOT real probe-level — domain aggregate only
                "weakness_type": weakness_type,
                "weakness_classifier_version": 0,  # version 0 = reconstructed, never mix with live v1
                "template_used": "unknown",  # historical data doesn't record template
                "pairs_generated": None,
                "fix_version": curr_key,
                "prev_version": prev_key,
                "pre_score": round(pre_score, 4),
                "post_score": round(post_score, 4),
                "delta": round(delta, 4),
                "fix_succeeded": fix_succeeded,
                "status": "closed",
                "eval_mode": "full",  # all historical evals were 60-probe full mode at this point
                "attribution": "unknown",  # can't determine isolated vs batched retroactively
                "opened_at": prev["timestamp"],
                "closed_at": curr["timestamp"],
                "is_failed_version": is_failed,

                # Bucket key (uses classifier_version=0 to NEVER collide with live v1)
                "bucket_key": f"full::0::{domain}::{weakness_type}::unknown",
            }
            patterns.append(pattern)

    return patterns


def build_shadow_corpus(ledger_path: str = None, output_path: str = None) -> dict:
    """
    Build the complete shadow backtest corpus.

    Returns corpus dict with metadata + patterns.
    """
    ledger = load_score_ledger(ledger_path)
    patterns = reconstruct_pseudo_patterns(ledger)

    # Compute summary stats
    by_domain = {}
    by_weakness = {}
    successes = 0
    failures = 0
    for p in patterns:
        d = p["domain"]
        w = p["weakness_type"]
        by_domain[d] = by_domain.get(d, 0) + 1
        by_weakness[w] = by_weakness.get(w, 0) + 1
        if p["fix_succeeded"]:
            successes += 1
        else:
            failures += 1

    corpus = {
        "governance": _GOVERNANCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "score_ledger.json",
        "success_threshold": _SUCCESS_THRESHOLD,
        "total_patterns": len(patterns),
        "successes": successes,
        "failures": failures,
        "by_domain": by_domain,
        "by_weakness_type": by_weakness,
        "version_transitions": len(set(p["fix_version"] for p in patterns)),
        "patterns": patterns,
    }

    output_path = output_path or _DEFAULT_OUTPUT
    with open(output_path, "w") as f:
        json.dump(corpus, f, indent=2, default=str)

    logger.info(f"Shadow backtest corpus: {len(patterns)} patterns "
                f"({successes} successes, {failures} failures) → {output_path}")
    return corpus


def rehearse_calibration(corpus: dict) -> dict:
    """
    Run the confidence_calibrator on shadow data to rehearse Gates 5-8 plumbing.

    This uses the SAME calibration code but on shadow data only.
    Results are labeled as rehearsal, never live.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.confidence_calibrator import compute_calibration_ledger, validate_calibration
    from datetime import timedelta

    patterns = corpus["patterns"]

    # Find a reasonable time-split point (60% fit / 40% holdout)
    timestamps = sorted(set(p["closed_at"] for p in patterns if p.get("closed_at")))
    if len(timestamps) < 3:
        return {"verdict": "insufficient_data", "reason": "Not enough time diversity"}

    split_idx = int(len(timestamps) * 0.6)
    cutoff_str = timestamps[split_idx]
    cutoff = datetime.fromisoformat(cutoff_str)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    # Run calibration on shadow data
    ledger = compute_calibration_ledger(patterns, fit_cutoff=cutoff)
    validation = validate_calibration(patterns, fit_cutoff=cutoff)

    return {
        "governance": _GOVERNANCE,
        "rehearsal": True,
        "fit_cutoff": cutoff_str,
        "calibration_ledger_summary": {
            "total_buckets": ledger["total_buckets"],
            "total_fitted": ledger["total_closed_patterns"],
        },
        "validation": validation,
        "sample_size_by_bucket": {
            k: {"evidence": v["evidence_count"], "usable": v["usable"]}
            for k, v in ledger.get("buckets", {}).items()
        },
    }


def estimate_campaign_needs(corpus: dict) -> dict:
    """
    Estimate how many real closures are needed per bucket to reach usable evidence.

    Uses shadow data to project bucket sparsity under the live 5-tuple key.
    """
    # Count patterns per live-compatible bucket (but with classifier_version=1, not 0)
    bucket_counts = {}
    for p in corpus["patterns"]:
        # Project to what the live bucket would look like
        live_key = f"full::1::{p['domain']}::{p['weakness_type']}::unknown"
        bucket_counts[live_key] = bucket_counts.get(live_key, 0) + 1

    # For each projected bucket, estimate closures needed
    # Usable = alpha + beta >= 5, meaning evidence_count >= 3
    # For validation: need >= 20 in holdout, so total ~50+ across all buckets
    estimates = {}
    for key, historical_count in sorted(bucket_counts.items(), key=lambda x: -x[1]):
        estimates[key] = {
            "historical_transitions": historical_count,
            "min_for_usable": max(0, 3 - historical_count),  # proxy: would need 3+ real closures
            "note": "These are domain-level aggregates. Real 5-tuple buckets will be sparser "
                    "because template is 'unknown' in shadow data but specific in live.",
        }

    return {
        "governance": _GOVERNANCE,
        "total_projected_buckets": len(estimates),
        "buckets_with_5plus_historical": sum(1 for v in estimates.values() if v["historical_transitions"] >= 5),
        "estimates": estimates,
        "recommendation": (
            f"Shadow data shows {len(estimates)} projected buckets. "
            f"In practice, real buckets will be sparser because 'template' is unknown in shadow data. "
            f"Target: 6-10 real closures per target bucket across 3-6 buckets = ~30-50 total closures."
        ),
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Lane A — Shadow Backtest Corpus Builder")
    print("=" * 60)
    print()
    print("GOVERNANCE: synthetic_backtest=True, usable_for_live_calibration=False")
    print()

    # Build corpus
    corpus = build_shadow_corpus()
    print(f"\nCorpus: {corpus['total_patterns']} patterns "
          f"({corpus['successes']} successes, {corpus['failures']} failures)")
    print(f"By domain: {corpus['by_domain']}")
    print(f"By weakness: {corpus['by_weakness_type']}")

    # Rehearse calibration
    print("\n--- Rehearsing calibration plumbing ---")
    rehearsal = rehearse_calibration(corpus)
    print(f"Rehearsal verdict: {rehearsal['validation']['verdict']}")
    print(f"Buckets fitted: {rehearsal['calibration_ledger_summary']['total_buckets']}")
    if "gates" in rehearsal["validation"]:
        for gate_name, gate_data in rehearsal["validation"]["gates"].items():
            print(f"  {gate_name}: {gate_data.get('verdict', 'N/A')}")

    # Estimate campaign needs
    print("\n--- Campaign size estimation ---")
    estimates = estimate_campaign_needs(corpus)
    print(f"Projected buckets: {estimates['total_projected_buckets']}")
    print(f"Buckets with 5+ historical transitions: {estimates['buckets_with_5plus_historical']}")
    print(f"\nRecommendation: {estimates['recommendation']}")

    # Save estimates
    with open("shadow_campaign_estimates.json", "w") as f:
        json.dump(estimates, f, indent=2, default=str)
    print(f"\nEstimates saved to shadow_campaign_estimates.json")
