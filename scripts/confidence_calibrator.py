"""
GEM 2 — Bayesian Confidence Calibration

Pure Bernoulli-Beta conjugate updating over closed critique patterns.
Each closed attempt contributes exactly one binary observation to its
5-tuple bucket's posterior. No fractional counts, no evidence weighting.

Bucket key (5-tuple):
    (eval_mode, weakness_classifier_version, domain, weakness_type, template)

Calibrated target:
    P(fix_succeeded == True) where fix_succeeded = (delta > 0.01)

Attribution (isolated/batched) is a stratification dimension for reporting
only — it does NOT weight the posterior. get_effective_templates() in
critique_memory.py uses weighted scoring for template ranking; that is a
separate system, not this calibrator.

Design contract frozen in docs/phase3_acceptance_gates.md at commit 59c6e85.
"""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# --- Constants (frozen in gate spec) ---

CALIBRATION_VERSION = "v1"
PRIOR_SPEC = "Beta(1,1)"
PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0
FEATURE_SCHEMA_VERSION = 1
INSUFFICIENT_DATA_THRESHOLD = 5  # alpha + beta < this → insufficient_data

# Success threshold — single source of truth.
# Also defined in scripts/critique_memory.py close_critique_loop().
# These MUST match. Frozen in docs/phase3_acceptance_gates.md.
SUCCESS_THRESHOLD = 0.01


def _bucket_key(eval_mode: str, wcv: int, domain: str,
                weakness_type: str, template: str) -> str:
    """Format the 5-tuple bucket key as a stable string."""
    return f"{eval_mode}::{wcv}::{domain}::{weakness_type}::{template}"


def _parse_bucket_key(key: str) -> dict:
    """Parse a bucket key string back to components."""
    parts = key.split("::")
    if len(parts) != 5:
        return {}
    return {
        "eval_mode": parts[0],
        "weakness_classifier_version": int(parts[1]),
        "domain": parts[2],
        "weakness_type": parts[3],
        "template": parts[4],
    }


# ---------------------------------------------------------------------------
# Core: compute calibration ledger from closed critique patterns
# ---------------------------------------------------------------------------

def compute_calibration_ledger(
    closed_patterns: list[dict],
    fit_cutoff: Optional[datetime] = None,
) -> dict:
    """
    Compute the full calibration ledger from closed critique patterns.

    Args:
        closed_patterns: List of critique pattern dicts (from retrieve_critique_patterns).
                         Must have status=="closed" and required metadata fields.
        fit_cutoff: Optional datetime. If provided, only patterns closed before
                    this time are used for fitting. Patterns after are excluded
                    (reserved for held-out validation).

    Returns:
        Versioned calibration ledger dict.
    """
    # Filter to closed-only and apply cutoff
    fitting_data = []
    for p in closed_patterns:
        if p.get("status") != "closed":
            continue
        if p.get("fix_succeeded") is None:
            continue

        if fit_cutoff:
            closed_at = p.get("closed_at")
            if closed_at:
                try:
                    closed_dt = datetime.fromisoformat(closed_at)
                    if closed_dt.tzinfo is None:
                        closed_dt = closed_dt.replace(tzinfo=timezone.utc)
                    if closed_dt >= fit_cutoff:
                        continue  # held out
                except (ValueError, TypeError):
                    continue
            else:
                continue  # no closed_at → skip

        fitting_data.append(p)

    # Partition into 5-tuple buckets
    buckets = {}
    for p in fitting_data:
        # Extract bucket dimensions — default eval_mode to "full" since
        # critique patterns from regression_eval use full mode by default
        eval_mode = p.get("eval_mode", "full")
        wcv = p.get("weakness_classifier_version", 1)
        domain = p.get("domain", "unknown")
        weakness_type = p.get("weakness_type", "unknown")
        template = p.get("template_used", "unknown")

        key = _bucket_key(eval_mode, wcv, domain, weakness_type, template)
        if key not in buckets:
            buckets[key] = {"successes": 0, "failures": 0, "attempts": []}
        if p["fix_succeeded"]:
            buckets[key]["successes"] += 1
        else:
            buckets[key]["failures"] += 1
        buckets[key]["attempts"].append(p.get("attempt_id"))

    # Compute posteriors
    now = datetime.now(timezone.utc).isoformat()
    earliest = None
    latest = None
    for p in fitting_data:
        closed_at = p.get("closed_at")
        if closed_at:
            if earliest is None or closed_at < earliest:
                earliest = closed_at
            if latest is None or closed_at > latest:
                latest = closed_at

    entries = {}
    for key, data in buckets.items():
        entry = _compute_bucket_entry(key, data["successes"], data["failures"])
        entries[key] = entry

    return {
        "calibration_version": CALIBRATION_VERSION,
        "prior_spec": PRIOR_SPEC,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "computed_at": now,
        "fit_window": {
            "from": earliest,
            "to": latest or now,
            "cutoff": fit_cutoff.isoformat() if fit_cutoff else None,
        },
        "total_closed_patterns": len(fitting_data),
        "total_buckets": len(entries),
        "buckets": entries,
    }


def _compute_bucket_entry(bucket_key: str, successes: int, failures: int) -> dict:
    """Compute posterior for a single bucket."""
    alpha = PRIOR_ALPHA + successes
    beta = PRIOR_BETA + failures
    evidence_count = successes + failures
    n = evidence_count

    # MLE baseline (raw success rate)
    mle = successes / n if n > 0 else None

    # Posterior mean
    posterior_mean = alpha / (alpha + beta)

    # 90% credible interval via beta distribution quantiles
    ci_lower, ci_upper = _beta_credible_interval(alpha, beta, 0.90)

    # Effective sample size (observations beyond prior)
    effective_n = alpha + beta - (PRIOR_ALPHA + PRIOR_BETA)

    # Source and usability
    is_prior_only = evidence_count == 0
    insufficient = (alpha + beta) < INSUFFICIENT_DATA_THRESHOLD

    parsed = _parse_bucket_key(bucket_key)

    return {
        "bucket_key": bucket_key,
        "eval_mode": parsed.get("eval_mode"),
        "weakness_classifier_version": parsed.get("weakness_classifier_version"),
        "domain": parsed.get("domain"),
        "weakness_type": parsed.get("weakness_type"),
        "template": parsed.get("template"),
        "calibration_version": CALIBRATION_VERSION,
        "prior_spec": PRIOR_SPEC,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "successes": successes,
        "failures": failures,
        "evidence_count": evidence_count,
        "mle": round(mle, 4) if mle is not None else None,
        "alpha": alpha,
        "beta": beta,
        "posterior_mean": round(posterior_mean, 4),
        "ci_90_lower": round(ci_lower, 4),
        "ci_90_upper": round(ci_upper, 4),
        "effective_sample_size": effective_n,
        "source": "prior_only" if is_prior_only else "posterior",
        "usable": not is_prior_only and not insufficient,
        "insufficient_data": insufficient,
    }


def _beta_credible_interval(alpha: float, beta: float, coverage: float = 0.90) -> tuple:
    """
    Compute equal-tailed credible interval for Beta(alpha, beta).
    Uses scipy if available, falls back to normal approximation.
    """
    tail = (1.0 - coverage) / 2.0
    try:
        from scipy.stats import beta as beta_dist
        lower = beta_dist.ppf(tail, alpha, beta)
        upper = beta_dist.ppf(1.0 - tail, alpha, beta)
        return (float(lower), float(upper))
    except ImportError:
        # Normal approximation fallback
        mean = alpha / (alpha + beta)
        var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        std = math.sqrt(var)
        # z for 90% CI ≈ 1.645
        z = 1.645
        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return (lower, upper)


# ---------------------------------------------------------------------------
# Empirical validation harness (Gates 5-6)
# ---------------------------------------------------------------------------

def validate_calibration(
    closed_patterns: list[dict],
    fit_cutoff: datetime,
) -> dict:
    """
    Run empirical validation: fit on data before cutoff, evaluate on data after.

    Implements Gates 5 (reliability + ECE + Brier) and Gate 6 (stratified).
    Returns validation report with honest insufficient_data handling.
    """
    # Split data
    fit_data = []
    holdout_data = []

    # Group by probe_id to prevent retry leakage (Gate 3)
    probe_groups = {}
    for p in closed_patterns:
        if p.get("status") != "closed" or p.get("fix_succeeded") is None:
            continue
        probe = p.get("probe_id", "unknown")
        if probe not in probe_groups:
            probe_groups[probe] = []
        probe_groups[probe].append(p)

    # Assign entire probe groups to fit or holdout based on earliest closure
    for probe, patterns in probe_groups.items():
        earliest_close = None
        for p in patterns:
            closed_at = p.get("closed_at")
            if closed_at:
                if earliest_close is None or closed_at < earliest_close:
                    earliest_close = closed_at

        if earliest_close is None:
            continue

        try:
            earliest_dt = datetime.fromisoformat(earliest_close)
            if earliest_dt.tzinfo is None:
                earliest_dt = earliest_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if earliest_dt < fit_cutoff:
            fit_data.extend(patterns)
        else:
            holdout_data.extend(patterns)

    # Check minimum data requirements
    if len(holdout_data) < 20:
        return {
            "verdict": "insufficient_data",
            "reason": f"Holdout set has {len(holdout_data)} closed attempts (need >= 20)",
            "fit_count": len(fit_data),
            "holdout_count": len(holdout_data),
            "gates": {
                "gate_5": {"verdict": "insufficient_data"},
                "gate_6": {"verdict": "insufficient_data"},
            },
        }

    # Fit calibration on training data
    ledger = compute_calibration_ledger(fit_data)

    # Evaluate on holdout
    gate_5 = _evaluate_gate_5(ledger, holdout_data)
    gate_6 = _evaluate_gate_6(ledger, holdout_data)

    overall = "pass" if gate_5["verdict"] == "pass" and gate_6["verdict"] == "pass" else "fail"
    if gate_5["verdict"] == "insufficient_data" or gate_6["verdict"] == "insufficient_data":
        overall = "insufficient_data"

    return {
        "verdict": overall,
        "fit_count": len(fit_data),
        "holdout_count": len(holdout_data),
        "fit_cutoff": fit_cutoff.isoformat(),
        "gates": {
            "gate_5": gate_5,
            "gate_6": gate_6,
        },
    }


def _evaluate_gate_5(ledger: dict, holdout: list[dict]) -> dict:
    """Gate 5: Reliability + ECE + Brier on held-out data."""
    predictions_mle = []
    predictions_cal = []
    outcomes = []

    for p in holdout:
        eval_mode = p.get("eval_mode", "full")
        wcv = p.get("weakness_classifier_version", 1)
        domain = p.get("domain", "unknown")
        weakness_type = p.get("weakness_type", "unknown")
        template = p.get("template_used", "unknown")
        key = _bucket_key(eval_mode, wcv, domain, weakness_type, template)

        bucket = ledger.get("buckets", {}).get(key)
        outcome = 1.0 if p.get("fix_succeeded") else 0.0
        outcomes.append(outcome)

        if bucket:
            predictions_mle.append(bucket["mle"] if bucket["mle"] is not None else 0.5)
            predictions_cal.append(bucket["posterior_mean"])
        else:
            # Unseen bucket → prior
            predictions_mle.append(0.5)
            predictions_cal.append(0.5)

    if len(outcomes) < 20:
        return {"verdict": "insufficient_data", "holdout_count": len(outcomes)}

    # 5a: Reliability diagram (5 bins)
    bins_mle = _reliability_bins(predictions_mle, outcomes, n_bins=5)
    bins_cal = _reliability_bins(predictions_cal, outcomes, n_bins=5)

    # 5b: ECE
    ece_mle = _compute_ece(bins_mle)
    ece_cal = _compute_ece(bins_cal)

    # 5c: Brier score
    brier_mle = sum((p - o) ** 2 for p, o in zip(predictions_mle, outcomes)) / len(outcomes)
    brier_cal = sum((p - o) ** 2 for p, o in zip(predictions_cal, outcomes)) / len(outcomes)

    ece_improved = ece_cal < ece_mle
    verdict = "pass" if ece_improved else "fail"

    return {
        "verdict": verdict,
        "holdout_count": len(outcomes),
        "reliability_bins_mle": bins_mle,
        "reliability_bins_cal": bins_cal,
        "ece_mle": round(ece_mle, 4),
        "ece_cal": round(ece_cal, 4),
        "ece_delta": round(ece_mle - ece_cal, 4),
        "ece_improved": ece_improved,
        "brier_mle": round(brier_mle, 4),
        "brier_cal": round(brier_cal, 4),
        "brier_delta": round(brier_mle - brier_cal, 4),
    }


def _evaluate_gate_6(ledger: dict, holdout: list[dict]) -> dict:
    """Gate 6: Stratified performance — no major slice degrades."""
    # Compute global ECE first
    all_preds = []
    all_outcomes = []
    for p in holdout:
        eval_mode = p.get("eval_mode", "full")
        wcv = p.get("weakness_classifier_version", 1)
        domain = p.get("domain", "unknown")
        weakness_type = p.get("weakness_type", "unknown")
        template = p.get("template_used", "unknown")
        key = _bucket_key(eval_mode, wcv, domain, weakness_type, template)
        bucket = ledger.get("buckets", {}).get(key)
        outcome = 1.0 if p.get("fix_succeeded") else 0.0
        pred = bucket["posterior_mean"] if bucket else 0.5
        all_preds.append(pred)
        all_outcomes.append(outcome)

    global_ece = _compute_ece(_reliability_bins(all_preds, all_outcomes, n_bins=5))

    # Stratify by each dimension
    strata_results = {}
    for dim_name, dim_key in [
        ("eval_mode", "eval_mode"),
        ("domain", "domain"),
        ("weakness_type", "weakness_type"),
        ("template", "template_used"),
        ("attribution", "attribution"),
    ]:
        groups = {}
        for i, p in enumerate(holdout):
            val = p.get(dim_key, "unknown")
            if val not in groups:
                groups[val] = {"preds": [], "outcomes": []}
            groups[val]["preds"].append(all_preds[i])
            groups[val]["outcomes"].append(all_outcomes[i])

        dim_results = {}
        for val, data in groups.items():
            n = len(data["outcomes"])
            if n < 5:
                dim_results[val] = {
                    "n": n, "verdict": "insufficient_data",
                }
                continue
            ece = _compute_ece(_reliability_bins(data["preds"], data["outcomes"], n_bins=5))
            too_high = ece > 2.0 * global_ece if global_ece > 0 else False
            dim_results[val] = {
                "n": n, "ece": round(ece, 4),
                "verdict": "fail" if too_high else "pass",
            }
        strata_results[dim_name] = dim_results

    # Overall: fail if any stratum with n>=5 has ECE > 2x global
    any_fail = any(
        entry.get("verdict") == "fail"
        for dim in strata_results.values()
        for entry in dim.values()
    )

    return {
        "verdict": "fail" if any_fail else "pass",
        "global_ece": round(global_ece, 4),
        "strata": strata_results,
    }


def _reliability_bins(predictions: list, outcomes: list, n_bins: int = 5) -> list:
    """Compute reliability diagram bins."""
    bins = []
    for i in range(n_bins):
        low = i / n_bins
        high = (i + 1) / n_bins
        indices = [j for j, p in enumerate(predictions)
                   if (low <= p < high) or (i == n_bins - 1 and p == high)]
        if not indices:
            bins.append({
                "bin_low": round(low, 2), "bin_high": round(high, 2),
                "count": 0, "mean_predicted": None, "mean_observed": None,
                "deviation": None,
            })
            continue
        mean_pred = sum(predictions[j] for j in indices) / len(indices)
        mean_obs = sum(outcomes[j] for j in indices) / len(indices)
        bins.append({
            "bin_low": round(low, 2), "bin_high": round(high, 2),
            "count": len(indices),
            "mean_predicted": round(mean_pred, 4),
            "mean_observed": round(mean_obs, 4),
            "deviation": round(abs(mean_pred - mean_obs), 4),
        })
    return bins


def _compute_ece(bins: list) -> float:
    """Expected Calibration Error from reliability bins."""
    total = sum(b["count"] for b in bins)
    if total == 0:
        return 0.0
    ece = 0.0
    for b in bins:
        if b["count"] > 0 and b["deviation"] is not None:
            ece += (b["count"] / total) * b["deviation"]
    return ece


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

_DEFAULT_LEDGER_PATH = "confidence_ledger.json"


def save_calibration_ledger(ledger: dict, path: str = None) -> str:
    """Save calibration ledger to JSON file. Returns path."""
    path = path or _DEFAULT_LEDGER_PATH
    with open(path, "w") as f:
        json.dump(ledger, f, indent=2, default=str)
    logger.info(f"Saved calibration ledger to {path} ({ledger.get('total_buckets', 0)} buckets)")
    return path


def load_calibration_ledger(path: str = None) -> Optional[dict]:
    """Load calibration ledger from JSON. Returns None if not found."""
    path = path or _DEFAULT_LEDGER_PATH
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load calibration ledger from {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# DB-backed convenience: compute ledger from live critique patterns
# ---------------------------------------------------------------------------

def compute_ledger_from_db(db, fit_cutoff: Optional[datetime] = None) -> dict:
    """
    Compute calibration ledger from closed critique patterns in the database.
    Convenience wrapper that reads from critique_memory and feeds compute_calibration_ledger.
    """
    from scripts.critique_memory import retrieve_critique_patterns
    all_patterns = retrieve_critique_patterns(db, status="closed", limit=10000)
    return compute_calibration_ledger(all_patterns, fit_cutoff=fit_cutoff)


def validate_from_db(db, fit_cutoff: datetime) -> dict:
    """
    Run empirical validation from DB.
    All closed patterns are loaded; the split is done by the harness.
    """
    from scripts.critique_memory import retrieve_critique_patterns
    all_closed = retrieve_critique_patterns(db, status="closed", limit=10000)
    return validate_calibration(all_closed, fit_cutoff=fit_cutoff)
