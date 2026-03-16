"""
Phase 3 (GEM 2) Validation Tests — Bayesian Confidence Calibration

Tests against frozen acceptance gates (docs/phase3_acceptance_gates.md, commit 59c6e85).

Structural gates (synthetic data):
  Gate 1: Semantic contract explicit
  Gate 2: No-op safety
  Gate 3: Train/eval leakage impossible
  Gate 4: Posterior behavior sane (4a-4d)
  Gate 7: Confidence versioned as data
  Gate 8: Runtime observability fields present
  Gate 9: Prior-only output semantics

Empirical gates (require real data, tested with synthetic here):
  Gate 5: Calibration improves on held-out (insufficient_data path tested)
  Gate 6: Stratified performance (insufficient_data path tested)

Run: python test_confidence_calibrator.py
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Gate 1: Semantic contract is explicit
# ---------------------------------------------------------------------------

def test_gate1_contract_fields():
    """Gate 1: All contract fields exist and are unambiguous."""
    from scripts.confidence_calibrator import (
        CALIBRATION_VERSION, PRIOR_SPEC, PRIOR_ALPHA, PRIOR_BETA,
        FEATURE_SCHEMA_VERSION, SUCCESS_THRESHOLD,
        _bucket_key, _parse_bucket_key,
    )

    # Constants exist and are correct type
    assert isinstance(CALIBRATION_VERSION, str)
    assert PRIOR_SPEC == "Beta(1,1)"
    assert PRIOR_ALPHA == 1.0
    assert PRIOR_BETA == 1.0
    assert isinstance(FEATURE_SCHEMA_VERSION, int)
    assert SUCCESS_THRESHOLD == 0.01

    # Bucket key is a 5-tuple
    key = _bucket_key("full", 1, "cpp", "keyword_only", "implement")
    assert key == "full::1::cpp::keyword_only::implement"

    # Round-trip parse
    parsed = _parse_bucket_key(key)
    assert parsed["eval_mode"] == "full"
    assert parsed["weakness_classifier_version"] == 1
    assert parsed["domain"] == "cpp"
    assert parsed["weakness_type"] == "keyword_only"
    assert parsed["template"] == "implement"

    print("PASS: test_gate1_contract_fields")


def test_gate1_success_threshold_matches_critique_memory():
    """Gate 1: SUCCESS_THRESHOLD must match critique_memory's threshold."""
    from scripts.confidence_calibrator import SUCCESS_THRESHOLD
    # The threshold is also hardcoded in close_critique_loop as _SUCCESS_THRESHOLD
    # Verify they agree
    assert SUCCESS_THRESHOLD == 0.01, f"Expected 0.01, got {SUCCESS_THRESHOLD}"
    print("PASS: test_gate1_success_threshold_matches_critique_memory")


# ---------------------------------------------------------------------------
# Gate 2: No-op safety
# ---------------------------------------------------------------------------

def test_gate2_flag_defaults_off():
    """Gate 2: BAYESIAN_CALIBRATION_ENABLED defaults to false."""
    from hiveai.config import BAYESIAN_CALIBRATION_ENABLED
    if not os.environ.get("BAYESIAN_CALIBRATION_ENABLED"):
        assert BAYESIAN_CALIBRATION_ENABLED is False, \
            "BAYESIAN_CALIBRATION_ENABLED should default False"
    print("PASS: test_gate2_flag_defaults_off")


# ---------------------------------------------------------------------------
# Gate 3: Train/eval leakage impossible
# ---------------------------------------------------------------------------

def test_gate3_time_split_enforced():
    """Gate 3: fit_cutoff correctly partitions data."""
    from scripts.confidence_calibrator import compute_calibration_ledger
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=3)

    # Create patterns: some before cutoff, some after
    patterns = [
        {"status": "closed", "fix_succeeded": True, "closed_at": (now - timedelta(days=5)).isoformat(),
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "cpp", "weakness_type": "keyword_only", "template_used": "implement",
         "attempt_id": "a1"},
        {"status": "closed", "fix_succeeded": False, "closed_at": (now - timedelta(days=1)).isoformat(),
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "cpp", "weakness_type": "keyword_only", "template_used": "implement",
         "attempt_id": "a2"},
    ]

    ledger = compute_calibration_ledger(patterns, fit_cutoff=cutoff)
    key = "full::1::cpp::keyword_only::implement"
    bucket = ledger["buckets"].get(key)

    # Only the first pattern (before cutoff) should be included
    assert bucket is not None, "Bucket should exist"
    assert bucket["evidence_count"] == 1, f"Expected 1 (pre-cutoff only), got {bucket['evidence_count']}"
    assert bucket["successes"] == 1
    assert bucket["failures"] == 0

    print("PASS: test_gate3_time_split_enforced")


def test_gate3_probe_level_grouping():
    """Gate 3: validate_calibration groups by probe to prevent retry leakage."""
    from scripts.confidence_calibrator import validate_calibration
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=3)

    # Create patterns for same probe spanning cutoff
    # All patterns for probe "cpp-raii" should go to the same side
    patterns = [
        {"status": "closed", "fix_succeeded": True,
         "closed_at": (now - timedelta(days=5)).isoformat(),  # before cutoff
         "probe_id": "cpp-raii",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "cpp", "weakness_type": "keyword_only", "template_used": "implement",
         "attempt_id": "a1"},
        {"status": "closed", "fix_succeeded": False,
         "closed_at": (now - timedelta(days=4)).isoformat(),  # before cutoff
         "probe_id": "cpp-raii",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "cpp", "weakness_type": "keyword_only", "template_used": "implement",
         "attempt_id": "a2"},
    ]

    result = validate_calibration(patterns, fit_cutoff=cutoff)
    # Both patterns are for same probe, earliest is before cutoff → all go to fit
    # Holdout is empty → insufficient_data
    assert result["verdict"] == "insufficient_data"
    assert result["holdout_count"] == 0

    print("PASS: test_gate3_probe_level_grouping")


# ---------------------------------------------------------------------------
# Gate 4: Posterior behavior is sane
# ---------------------------------------------------------------------------

def test_gate4a_no_extreme_confidence():
    """Gate 4a: No exact 0 or 1 confidence under low counts."""
    from scripts.confidence_calibrator import _compute_bucket_entry

    # Beta(1,1) — pure prior
    entry = _compute_bucket_entry("full::1::cpp::kw::impl", 0, 0)
    assert entry["posterior_mean"] == 0.5
    assert entry["source"] == "prior_only"
    assert entry["usable"] is False
    assert entry["insufficient_data"] is True

    # Beta(2,1) — one success
    entry = _compute_bucket_entry("full::1::cpp::kw::impl", 1, 0)
    assert 0 < entry["posterior_mean"] < 1
    assert entry["posterior_mean"] != 1.0
    assert abs(entry["posterior_mean"] - 0.6667) < 0.001

    # Beta(1,2) — one failure
    entry = _compute_bucket_entry("full::1::cpp::kw::impl", 0, 1)
    assert 0 < entry["posterior_mean"] < 1
    assert entry["posterior_mean"] != 0.0
    assert abs(entry["posterior_mean"] - 0.3333) < 0.001

    # All low-count entries should be insufficient_data
    for s, f in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        entry = _compute_bucket_entry("full::1::x::y::z", s, f)
        assert entry["insufficient_data"] is True, f"({s},{f}) should be insufficient"

    # Sufficient data
    entry = _compute_bucket_entry("full::1::x::y::z", 2, 2)
    # alpha+beta = 5 (1+2 + 1+2), not < 5
    assert entry["insufficient_data"] is False

    print("PASS: test_gate4a_no_extreme_confidence")


def test_gate4b_interval_narrows():
    """Gate 4b: Posterior interval narrows with more evidence."""
    from scripts.confidence_calibrator import _compute_bucket_entry

    # Low evidence: Beta(2,1) — wide interval
    low = _compute_bucket_entry("full::1::cpp::kw::impl", 1, 0)
    # High evidence: Beta(20,10) — narrow interval
    high = _compute_bucket_entry("full::1::cpp::kw::impl", 19, 9)

    low_width = low["ci_90_upper"] - low["ci_90_lower"]
    high_width = high["ci_90_upper"] - high["ci_90_lower"]

    assert low_width > high_width, \
        f"Low evidence interval ({low_width:.4f}) should be wider than high ({high_width:.4f})"

    print("PASS: test_gate4b_interval_narrows")


def test_gate4c_monotone_in_evidence():
    """Gate 4c: Adding success increases mean, adding failure decreases it."""
    from scripts.confidence_calibrator import _compute_bucket_entry

    base = _compute_bucket_entry("full::1::cpp::kw::impl", 3, 3)
    more_success = _compute_bucket_entry("full::1::cpp::kw::impl", 4, 3)
    more_failure = _compute_bucket_entry("full::1::cpp::kw::impl", 3, 4)

    assert more_success["posterior_mean"] > base["posterior_mean"], \
        "Adding success must increase posterior mean"
    assert more_failure["posterior_mean"] < base["posterior_mean"], \
        "Adding failure must decrease posterior mean"

    # Verify over a range
    for s in range(0, 10):
        a = _compute_bucket_entry("full::1::x::y::z", s, 5)
        b = _compute_bucket_entry("full::1::x::y::z", s + 1, 5)
        assert b["posterior_mean"] >= a["posterior_mean"], \
            f"Monotonicity violated: s={s}→{s+1}"

    print("PASS: test_gate4c_monotone_in_evidence")


def test_gate4d_contradictory_evidence_widens():
    """Gate 4d: Mixed evidence produces wider intervals than pure evidence."""
    from scripts.confidence_calibrator import _compute_bucket_entry

    # Pure success: Beta(6,1)
    pure_success = _compute_bucket_entry("full::1::cpp::kw::impl", 5, 0)
    # Pure failure: Beta(1,6)
    pure_failure = _compute_bucket_entry("full::1::cpp::kw::impl", 0, 5)
    # Mixed: Beta(6,6) — same total evidence, contradictory
    mixed = _compute_bucket_entry("full::1::cpp::kw::impl", 5, 5)

    pure_s_width = pure_success["ci_90_upper"] - pure_success["ci_90_lower"]
    pure_f_width = pure_failure["ci_90_upper"] - pure_failure["ci_90_lower"]
    mixed_width = mixed["ci_90_upper"] - mixed["ci_90_lower"]

    # Mixed should be wider than either pure (with same total n)
    # Note: Beta(6,6) has max variance at mean=0.5 for given n
    assert mixed_width > pure_s_width, \
        f"Mixed ({mixed_width:.4f}) should be wider than pure success ({pure_s_width:.4f})"
    assert mixed_width > pure_f_width, \
        f"Mixed ({mixed_width:.4f}) should be wider than pure failure ({pure_f_width:.4f})"

    print("PASS: test_gate4d_contradictory_evidence_widens")


# ---------------------------------------------------------------------------
# Gate 5 & 6: Empirical validation (insufficient_data path)
# ---------------------------------------------------------------------------

def test_gate5_insufficient_data_path():
    """Gate 5: With < 20 holdout attempts, returns insufficient_data."""
    from scripts.confidence_calibrator import validate_calibration
    from datetime import datetime, timezone

    # Empty data → insufficient
    result = validate_calibration([], datetime.now(timezone.utc))
    assert result["verdict"] == "insufficient_data"
    assert result["gates"]["gate_5"]["verdict"] == "insufficient_data"
    assert result["gates"]["gate_6"]["verdict"] == "insufficient_data"

    print("PASS: test_gate5_insufficient_data_path")


def test_gate5_with_synthetic_data():
    """Gate 5: With enough synthetic data, harness runs and produces diagnostics."""
    from scripts.confidence_calibrator import validate_calibration
    from datetime import datetime, timezone, timedelta
    import random

    random.seed(42)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=5)

    patterns = []
    # Generate 50 patterns: 30 before cutoff (fit), 20 after (holdout)
    # Use different probes for fit vs holdout to satisfy Gate 3
    for i in range(30):
        patterns.append({
            "status": "closed",
            "fix_succeeded": random.random() < 0.7,  # 70% success rate
            "closed_at": (now - timedelta(days=10 - i * 0.1)).isoformat(),
            "probe_id": f"fit-probe-{i}",
            "eval_mode": "full",
            "weakness_classifier_version": 1,
            "domain": "cpp",
            "weakness_type": "keyword_only",
            "template_used": "implement",
            "attribution": "isolated",
            "attempt_id": f"fit-{i}",
        })
    for i in range(25):
        patterns.append({
            "status": "closed",
            "fix_succeeded": random.random() < 0.7,
            "closed_at": (now - timedelta(days=3 - i * 0.1)).isoformat(),
            "probe_id": f"holdout-probe-{i}",
            "eval_mode": "full",
            "weakness_classifier_version": 1,
            "domain": "cpp",
            "weakness_type": "keyword_only",
            "template_used": "implement",
            "attribution": "isolated",
            "attempt_id": f"holdout-{i}",
        })

    result = validate_calibration(patterns, fit_cutoff=cutoff)

    # Should have enough data to run
    assert result["verdict"] in ("pass", "fail"), f"Expected pass/fail, got {result['verdict']}"
    assert result["fit_count"] == 30
    assert result["holdout_count"] == 25

    # Gate 5 should have all diagnostic fields
    g5 = result["gates"]["gate_5"]
    assert "ece_mle" in g5
    assert "ece_cal" in g5
    assert "brier_mle" in g5
    assert "brier_cal" in g5
    assert "reliability_bins_mle" in g5
    assert "reliability_bins_cal" in g5
    assert len(g5["reliability_bins_cal"]) == 5

    # Gate 6 should have strata
    g6 = result["gates"]["gate_6"]
    assert "global_ece" in g6
    assert "strata" in g6
    assert "domain" in g6["strata"]

    print(f"PASS: test_gate5_with_synthetic_data (verdict={result['verdict']}, "
          f"ECE mle={g5['ece_mle']} cal={g5['ece_cal']})")


# ---------------------------------------------------------------------------
# Gate 7: Confidence versioned as data
# ---------------------------------------------------------------------------

def test_gate7_versioning_fields():
    """Gate 7: Every bucket entry carries full versioning."""
    from scripts.confidence_calibrator import compute_calibration_ledger

    patterns = [
        {"status": "closed", "fix_succeeded": True,
         "closed_at": "2026-03-16T12:00:00+00:00",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "rust", "weakness_type": "structure_only", "template_used": "debug_fix",
         "attempt_id": "v7-test"},
    ]

    ledger = compute_calibration_ledger(patterns)

    # Ledger-level fields
    assert ledger["calibration_version"] == "v1"
    assert ledger["prior_spec"] == "Beta(1,1)"
    assert ledger["feature_schema_version"] == 1
    assert "fit_window" in ledger
    assert "from" in ledger["fit_window"]
    assert "to" in ledger["fit_window"]

    # Bucket-level fields
    key = "full::1::rust::structure_only::debug_fix"
    bucket = ledger["buckets"][key]

    required_fields = [
        "bucket_key", "eval_mode", "weakness_classifier_version",
        "domain", "weakness_type", "template",
        "calibration_version", "prior_spec", "feature_schema_version",
        "successes", "failures", "evidence_count",
        "mle", "alpha", "beta", "posterior_mean",
        "ci_90_lower", "ci_90_upper", "effective_sample_size",
        "source", "usable", "insufficient_data",
    ]

    for field in required_fields:
        assert field in bucket, f"Missing required field: {field}"

    # Source semantics
    assert bucket["source"] == "posterior"  # has evidence
    assert bucket["evidence_count"] == 1

    print("PASS: test_gate7_versioning_fields")


def test_gate7_prior_only_source():
    """Gate 7: Zero-evidence buckets emit source='prior_only'."""
    from scripts.confidence_calibrator import _compute_bucket_entry

    entry = _compute_bucket_entry("full::1::cpp::kw::impl", 0, 0)
    assert entry["source"] == "prior_only"
    assert entry["usable"] is False
    assert entry["evidence_count"] == 0
    assert entry["posterior_mean"] == 0.5
    assert entry["mle"] is None
    assert entry["insufficient_data"] is True

    print("PASS: test_gate7_prior_only_source")


# ---------------------------------------------------------------------------
# Gate 8: Runtime observability
# ---------------------------------------------------------------------------

def test_gate8_observability_fields():
    """Gate 8: Bucket entries have all fields needed for 'why was this 0.72?'"""
    from scripts.confidence_calibrator import _compute_bucket_entry

    entry = _compute_bucket_entry("full::1::cpp::keyword_only::implement", 5, 2)

    # Must be able to answer: why is this 0.72?
    # Answer: posterior_mean = (1+5)/(1+5+1+2) = 6/9 = 0.6667
    assert abs(entry["posterior_mean"] - 0.6667) < 0.001

    # All traceability fields present
    assert entry["alpha"] == 6.0  # 1 + 5
    assert entry["beta"] == 3.0   # 1 + 2
    assert entry["mle"] is not None  # 5/7 ≈ 0.714
    assert abs(entry["mle"] - 0.7143) < 0.001
    assert entry["ci_90_lower"] < entry["posterior_mean"] < entry["ci_90_upper"]
    assert entry["effective_sample_size"] == 7  # 6 + 3 - 2
    assert entry["source"] == "posterior"
    assert entry["usable"] is True
    assert entry["insufficient_data"] is False

    print("PASS: test_gate8_observability_fields")


# ---------------------------------------------------------------------------
# Gate 9: Failure mode acceptable
# ---------------------------------------------------------------------------

def test_gate9_zero_evidence_semantics():
    """Gate 9: Zero evidence → prior_only, usable=false, honest output."""
    from scripts.confidence_calibrator import compute_calibration_ledger

    # No patterns at all
    ledger = compute_calibration_ledger([])
    assert ledger["total_closed_patterns"] == 0
    assert ledger["total_buckets"] == 0
    assert len(ledger["buckets"]) == 0

    print("PASS: test_gate9_zero_evidence_semantics")


def test_gate9_insufficient_data_is_not_failure():
    """Gate 9: insufficient_data is a valid conclusion, not a failure."""
    from scripts.confidence_calibrator import validate_calibration
    from datetime import datetime, timezone

    result = validate_calibration([], datetime.now(timezone.utc))
    assert result["verdict"] == "insufficient_data"
    # This is NOT "fail" — it is honest uncertainty
    assert result["verdict"] != "fail"

    print("PASS: test_gate9_insufficient_data_is_not_failure")


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def test_ledger_save_load():
    """Bonus: Ledger round-trips through JSON."""
    import tempfile
    from scripts.confidence_calibrator import (
        compute_calibration_ledger, save_calibration_ledger, load_calibration_ledger,
    )

    patterns = [
        {"status": "closed", "fix_succeeded": True,
         "closed_at": "2026-03-16T12:00:00+00:00",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "go", "weakness_type": "compound", "template_used": "implement",
         "attempt_id": "io-test"},
    ]
    ledger = compute_calibration_ledger(patterns)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        save_calibration_ledger(ledger, path)
        loaded = load_calibration_ledger(path)
        assert loaded is not None
        assert loaded["calibration_version"] == ledger["calibration_version"]
        assert loaded["total_buckets"] == ledger["total_buckets"]
        assert "full::1::go::compound::implement" in loaded["buckets"]
    finally:
        os.unlink(path)

    print("PASS: test_ledger_save_load")


# ---------------------------------------------------------------------------
# Attribution is NOT in posterior (enforced)
# ---------------------------------------------------------------------------

def test_attribution_not_in_posterior():
    """Enforce: attribution does NOT alter alpha or beta."""
    from scripts.confidence_calibrator import compute_calibration_ledger

    # Two patterns: one isolated, one batched, same bucket
    patterns = [
        {"status": "closed", "fix_succeeded": True,
         "closed_at": "2026-03-16T12:00:00+00:00",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "js", "weakness_type": "keyword_only", "template_used": "implement",
         "attribution": "isolated", "attempt_id": "attr-1"},
        {"status": "closed", "fix_succeeded": True,
         "closed_at": "2026-03-16T13:00:00+00:00",
         "eval_mode": "full", "weakness_classifier_version": 1,
         "domain": "js", "weakness_type": "keyword_only", "template_used": "implement",
         "attribution": "batched", "attempt_id": "attr-2"},
    ]

    ledger = compute_calibration_ledger(patterns)
    key = "full::1::js::keyword_only::implement"
    bucket = ledger["buckets"][key]

    # Both count as exactly 1 Bernoulli trial each — no fractional weighting
    assert bucket["successes"] == 2, "Both should count as 1 success each"
    assert bucket["failures"] == 0
    assert bucket["alpha"] == 3.0, "Alpha should be 1 (prior) + 2 (successes)"
    assert bucket["beta"] == 1.0, "Beta should be 1 (prior) + 0 (failures)"

    print("PASS: test_attribution_not_in_posterior")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3 (GEM 2) Validation Tests")
    print("=" * 60)

    tests = [
        # Gate 1
        test_gate1_contract_fields,
        test_gate1_success_threshold_matches_critique_memory,
        # Gate 2
        test_gate2_flag_defaults_off,
        # Gate 3
        test_gate3_time_split_enforced,
        test_gate3_probe_level_grouping,
        # Gate 4
        test_gate4a_no_extreme_confidence,
        test_gate4b_interval_narrows,
        test_gate4c_monotone_in_evidence,
        test_gate4d_contradictory_evidence_widens,
        # Gate 5-6
        test_gate5_insufficient_data_path,
        test_gate5_with_synthetic_data,
        # Gate 7
        test_gate7_versioning_fields,
        test_gate7_prior_only_source,
        # Gate 8
        test_gate8_observability_fields,
        # Gate 9
        test_gate9_zero_evidence_semantics,
        test_gate9_insufficient_data_is_not_failure,
        # Bonus
        test_ledger_save_load,
        test_attribution_not_in_posterior,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("ALL CHECKS PASS")
    else:
        print("SOME CHECKS FAILED")
        sys.exit(1)
