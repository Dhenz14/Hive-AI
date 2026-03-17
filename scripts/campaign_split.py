#!/usr/bin/env python3
"""
Evidence Campaign v1 — Deterministic Fit/Holdout Split

Implements the preregistered split algorithm from split_algorithm.md.
Reads full_baseline.json for scores, applies SHA256-based sorting,
assigns fit/holdout roles, checks headroom.

Usage:
    python scripts/campaign_split.py                    # apply split
    python scripts/campaign_split.py --verify           # verify reproducibility
    python scripts/campaign_split.py --headroom-report  # detailed headroom analysis
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Frozen campaign parameters
# ---------------------------------------------------------------------------
SPLIT_SALT = "evidence_campaign_v1_2026-03-16"
SPLIT_ALGORITHM_VERSION = 1

# Anchor assignments (B1-B5)
# Decision: rs-errors replaces cpp-const (B5). Rationale:
#   cpp-const (0.940, 6% headroom, none) is a low-sensitivity canary.
#   rs-errors (0.525, 47.5% headroom, keyword_only) is a strong improvement target.
#   One low-headroom C++ bucket (B4) is kept for breadth/regression.
#   Two is expensive in a 5-bucket campaign.
ANCHORS = {
    "js": ["js-generics"],                  # B1
    "python": ["py-metaclass"],             # B2
    "rust": ["rs-ownership", "rs-errors"],  # B3, B5
    "cpp": ["cpp-variadic"],                # B4
}

BUCKET_MAP = {
    "js-generics": "B1",
    "py-metaclass": "B2",
    "rs-ownership": "B3",
    "cpp-variadic": "B4",
    "rs-errors": "B5",
}

# Template assignment per bucket
BUCKET_TEMPLATES = {
    "B1": "implement",
    "B2": "explain",
    "B3": "debug_fix",
    "B4": "implement",
    "B5": "debug_fix",  # rs-errors: error handling weakness → debug_fix template
}

CEILING_THRESHOLD = 0.95

# Fit/holdout ratio: 60% fit, 40% holdout
FIT_RATIO = 0.6


def _sort_key(probe_id: str) -> str:
    """Deterministic, bias-free sort key: SHA256(SALT + probe_id)."""
    return hashlib.sha256(f"{SPLIT_SALT}{probe_id}".encode()).hexdigest()


def load_baseline() -> dict:
    """Load full_baseline.json scores into a flat dict keyed by probe_id."""
    baseline_path = PROJECT_ROOT / "evidence_campaign" / "full_baseline.json"
    if not baseline_path.exists():
        print(f"ERROR: {baseline_path} not found. Run campaign_full_baseline.py first.")
        sys.exit(1)

    with open(baseline_path) as f:
        data = json.load(f)

    scores = {}
    for domain, probes in data.items():
        for p in probes:
            scores[p["probe_id"]] = p
    return scores


def compute_split(scores: dict) -> dict:
    """Apply the deterministic split algorithm."""
    result = {}

    for domain, anchor_ids in ANCHORS.items():
        # Get all probes in this domain
        domain_probes = [pid for pid, info in scores.items() if info["domain"] == domain]

        # Remove anchors
        siblings = [pid for pid in domain_probes if pid not in anchor_ids]

        # Sort by SHA256 hash (deterministic, bias-free)
        siblings_sorted = sorted(siblings, key=_sort_key)

        # Log the hash ordering for auditability
        hash_order = [(pid, _sort_key(pid)[:12]) for pid in siblings_sorted]

        # Split: first 60% fit, rest holdout
        n_fit = round(len(siblings_sorted) * FIT_RATIO)
        fit_probes = siblings_sorted[:n_fit]
        holdout_probes = siblings_sorted[n_fit:]

        # Gather scores
        def _probe_info(pid):
            s = scores.get(pid, {})
            return {
                "probe_id": pid,
                "score": s.get("score", 0),
                "keyword_score": s.get("keyword_score", 0),
                "structure_score": s.get("structure_score", 0),
                "weakness_type": s.get("weakness_type", "unknown"),
                "difficulty": s.get("difficulty", "unknown"),
            }

        # Gather probe info
        anchor_infos = [_probe_info(pid) for pid in anchor_ids]
        fit_infos = [_probe_info(pid) for pid in fit_probes]
        holdout_infos = [_probe_info(pid) for pid in holdout_probes]

        # Classify each holdout probe's role
        for h in holdout_infos:
            h["holdout_role"] = ("regression_sentinel" if h["score"] >= CEILING_THRESHOLD
                                 else "improvement_sensitive")

        # Domain-level checks
        any_holdout_improvement = any(
            h["holdout_role"] == "improvement_sensitive" for h in holdout_infos)
        any_fit_below_ceiling = any(p["score"] < CEILING_THRESHOLD for p in fit_infos)
        anchor_near_ceiling = all(p["score"] >= CEILING_THRESHOLD for p in anchor_infos)
        min_anchor_headroom = min(1.0 - a["score"] for a in anchor_infos)
        max_anchor_headroom = max(1.0 - a["score"] for a in anchor_infos)

        # Bucket role classification
        #   improvement:  anchor has >15% headroom, holdout has improvement-sensitive probes
        #   mixed:        anchor has some headroom, holdout is regression-only
        #   sentinel:     anchor near ceiling, mostly regression detection
        if max_anchor_headroom >= 0.15 and any_holdout_improvement:
            bucket_role = "improvement"
        elif max_anchor_headroom >= 0.08:
            bucket_role = "mixed"
        else:
            bucket_role = "regression_sentinel"

        # Holdout reporting role
        if any_holdout_improvement:
            holdout_role = "improvement_sensitive"
        else:
            holdout_role = "regression_sentinel_only"

        result[domain] = {
            "anchors": anchor_infos,
            "fit": fit_infos,
            "holdout": holdout_infos,
            "hash_order": hash_order,
            "bucket_role": bucket_role,
            "holdout_role": holdout_role,
            "checks": {
                "fit_count": len(fit_probes),
                "holdout_count": len(holdout_probes),
                "fit_min_2": len(fit_probes) >= 2,
                "holdout_min_1": len(holdout_probes) >= 1,
                "any_fit_below_ceiling": any_fit_below_ceiling,
                "any_holdout_improvement": any_holdout_improvement,
                "anchor_near_ceiling": anchor_near_ceiling,
                "min_anchor_headroom": round(min_anchor_headroom, 3),
                "max_anchor_headroom": round(max_anchor_headroom, 3),
            },
        }

    return result


def print_split(split: dict):
    """Print the split assignment in human-readable format."""
    print(f"\n{'='*75}")
    print(f"  Evidence Campaign v1 — Deterministic Fit/Holdout Split")
    print(f"  Salt: {SPLIT_SALT}")
    print(f"  Algorithm: v{SPLIT_ALGORITHM_VERSION}")
    print(f"{'='*75}\n")

    all_pass = True

    for domain, data in split.items():
        checks = data["checks"]
        role = data["bucket_role"].upper()
        ho_role = data["holdout_role"]
        print(f"--- {domain.upper()} [{role}] holdout={ho_role} ---")

        # Anchors
        for a in data["anchors"]:
            bucket = BUCKET_MAP.get(a["probe_id"], "?")
            hdroom = 1.0 - a["score"]
            print(f"  ANCHOR [{bucket}]: {a['probe_id']:22s} score={a['score']:.3f} "
                  f"wt={a['weakness_type']} headroom={hdroom:.1%}")

        # Fit
        print(f"  FIT ({checks['fit_count']}):")
        for p in data["fit"]:
            tag = " CEILING" if p["score"] >= CEILING_THRESHOLD else ""
            print(f"    {p['probe_id']:22s} score={p['score']:.3f} "
                  f"wt={p['weakness_type']}{tag}")

        # Holdout
        print(f"  HOLDOUT ({checks['holdout_count']}):")
        for p in data["holdout"]:
            hr = p.get("holdout_role", "?")
            print(f"    {p['probe_id']:22s} score={p['score']:.3f} "
                  f"wt={p['weakness_type']} role={hr}")

        # Checks
        status_parts = []
        if not checks["fit_min_2"]:
            status_parts.append("FAIL: <2 fit")
            all_pass = False
        if not checks["holdout_min_1"]:
            status_parts.append("FAIL: <1 holdout")
            all_pass = False
        if not checks["any_holdout_improvement"]:
            status_parts.append("NOTE: holdout is regression-sentinel-only")
        if checks["anchor_near_ceiling"]:
            status_parts.append("NOTE: all anchors near ceiling")
        if not status_parts:
            status_parts.append("PASS")

        print(f"  Status: {' | '.join(status_parts)}")
        print()

    print(f"{'='*75}")
    print(f"  Overall: {'ALL STRUCTURAL CHECKS PASS' if all_pass else 'SOME CHECKS FAILED'}")
    print(f"{'='*75}")


def write_split_manifest(split: dict):
    """Write the frozen split manifest."""
    manifest = {
        "split_salt": SPLIT_SALT,
        "split_algorithm_version": SPLIT_ALGORITHM_VERSION,
        "fit_ratio": FIT_RATIO,
        "domains": {},
        "analysis_rules": {
            "primary_improvement_holdout": (
                "Only holdout probes with holdout_role=improvement_sensitive "
                "count toward the primary improvement-sensitive holdout denominator."
            ),
            "regression_sentinel_holdout": (
                "Holdout probes with holdout_role=regression_sentinel are reported "
                "separately. They can confirm non-regression but do not constitute "
                "positive evidence of improvement."
            ),
            "option_c_rejection": (
                "Manual override of the deterministic split was considered and rejected. "
                "Once the assignment is computed, no probe may be moved between fit and "
                "holdout regardless of ceiling status. The split algorithm is the law."
            ),
        },
    }

    for domain, data in split.items():
        manifest["domains"][domain] = {
            "anchors": [a["probe_id"] for a in data["anchors"]],
            "fit": [p["probe_id"] for p in data["fit"]],
            "holdout": [
                {"probe_id": p["probe_id"], "holdout_role": p.get("holdout_role", "unknown")}
                for p in data["holdout"]
            ],
            "bucket_role": data["bucket_role"],
            "holdout_role": data["holdout_role"],
            "hash_order": data["hash_order"],
            "checks": data["checks"],
        }

    out_path = PROJECT_ROOT / "evidence_campaign" / "split_manifest.json"
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nSplit manifest written: {out_path}")
    return out_path


def headroom_report(split: dict, scores: dict):
    """Detailed headroom analysis per bucket."""
    print(f"\n{'='*75}")
    print(f"  Headroom Analysis")
    print(f"{'='*75}\n")

    for domain, data in split.items():
        for anchor in data["anchors"]:
            bucket = BUCKET_MAP.get(anchor["probe_id"], "?")
            headroom = 1.0 - anchor["score"]
            role = data["bucket_role"]

            print(f"  {bucket} ({anchor['probe_id']}) — {role}:")
            print(f"    Anchor:  score={anchor['score']:.3f}  headroom={headroom:.1%}  "
                  f"wt={anchor['weakness_type']}")

            # Holdout breakdown
            ho_imp = [h for h in data["holdout"]
                      if h.get("holdout_role") == "improvement_sensitive"]
            ho_reg = [h for h in data["holdout"]
                      if h.get("holdout_role") == "regression_sentinel"]
            print(f"    Holdout: {len(ho_imp)} improvement-sensitive, "
                  f"{len(ho_reg)} regression-sentinel")

            if headroom < 0.08:
                print(f"    ** LOW HEADROOM: anchor within 8% of ceiling")
            if not ho_imp:
                print(f"    ** HOLDOUT REGRESSION-ONLY: cannot confirm improvement")
            print()


def main():
    parser = argparse.ArgumentParser(description="Campaign split algorithm")
    parser.add_argument("--verify", action="store_true", help="Verify reproducibility")
    parser.add_argument("--headroom-report", action="store_true", help="Detailed headroom analysis")
    args = parser.parse_args()

    scores = load_baseline()
    split = compute_split(scores)

    if args.verify:
        # Run twice, compare
        split2 = compute_split(scores)
        match = json.dumps(split, sort_keys=True) == json.dumps(split2, sort_keys=True)
        print(f"Reproducibility check: {'PASS' if match else 'FAIL'}")
        return

    print_split(split)

    if args.headroom_report:
        headroom_report(split, scores)

    write_split_manifest(split)


if __name__ == "__main__":
    main()
