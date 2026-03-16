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
ANCHORS = {
    "js": ["js-generics"],       # B1
    "python": ["py-metaclass"],  # B2
    "rust": ["rs-ownership"],    # B3
    "cpp": ["cpp-variadic", "cpp-const"],  # B4, B5
}

BUCKET_MAP = {
    "js-generics": "B1",
    "py-metaclass": "B2",
    "rs-ownership": "B3",
    "cpp-variadic": "B4",
    "cpp-const": "B5",
}

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

        # Headroom checks
        anchor_infos = [_probe_info(pid) for pid in anchor_ids]
        fit_infos = [_probe_info(pid) for pid in fit_probes]
        holdout_infos = [_probe_info(pid) for pid in holdout_probes]

        all_non_anchor = fit_infos + holdout_infos
        any_below_ceiling = any(p["score"] < 0.95 for p in all_non_anchor)
        any_holdout_below_ceiling = any(p["score"] < 0.95 for p in holdout_infos)
        anchor_near_ceiling = all(p["score"] >= 0.95 for p in anchor_infos)

        headroom_flag = anchor_near_ceiling and not any_holdout_below_ceiling
        low_sensitivity = anchor_near_ceiling

        result[domain] = {
            "anchors": anchor_infos,
            "fit": fit_infos,
            "holdout": holdout_infos,
            "hash_order": hash_order,
            "checks": {
                "fit_count": len(fit_probes),
                "holdout_count": len(holdout_probes),
                "fit_min_2": len(fit_probes) >= 2,
                "holdout_min_1": len(holdout_probes) >= 1,
                "any_below_ceiling": any_below_ceiling,
                "any_holdout_below_ceiling": any_holdout_below_ceiling,
                "anchor_near_ceiling": anchor_near_ceiling,
                "headroom_flag": headroom_flag,
                "low_sensitivity": low_sensitivity,
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
        print(f"--- {domain.upper()} ---")

        # Anchors
        for a in data["anchors"]:
            bucket = BUCKET_MAP.get(a["probe_id"], "?")
            print(f"  ANCHOR [{bucket}]: {a['probe_id']:22s} score={a['score']:.3f} "
                  f"wt={a['weakness_type']}")

        # Fit
        print(f"  FIT ({checks['fit_count']}):")
        for p in data["fit"]:
            print(f"    {p['probe_id']:22s} score={p['score']:.3f} "
                  f"wt={p['weakness_type']} diff={p['difficulty']}")

        # Holdout
        print(f"  HOLDOUT ({checks['holdout_count']}):")
        for p in data["holdout"]:
            print(f"    {p['probe_id']:22s} score={p['score']:.3f} "
                  f"wt={p['weakness_type']} diff={p['difficulty']}")

        # Checks
        status_parts = []
        if not checks["fit_min_2"]:
            status_parts.append("FAIL: <2 fit")
            all_pass = False
        if not checks["holdout_min_1"]:
            status_parts.append("FAIL: <1 holdout")
            all_pass = False
        if checks["headroom_flag"]:
            status_parts.append("WARNING: low headroom (anchor+holdout all >=0.95)")
        if checks["low_sensitivity"]:
            status_parts.append("NOTE: anchor near ceiling (>=0.95)")
        if not status_parts:
            status_parts.append("PASS")

        print(f"  Status: {' | '.join(status_parts)}")
        print()

    print(f"{'='*75}")
    print(f"  Overall: {'ALL CHECKS PASS' if all_pass else 'SOME CHECKS FAILED'}")
    print(f"{'='*75}")


def write_split_manifest(split: dict):
    """Write the frozen split manifest."""
    manifest = {
        "split_salt": SPLIT_SALT,
        "split_algorithm_version": SPLIT_ALGORITHM_VERSION,
        "fit_ratio": FIT_RATIO,
        "domains": {},
    }

    for domain, data in split.items():
        manifest["domains"][domain] = {
            "anchors": [a["probe_id"] for a in data["anchors"]],
            "fit": [p["probe_id"] for p in data["fit"]],
            "holdout": [p["probe_id"] for p in data["holdout"]],
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

            holdout_scores = [p["score"] for p in data["holdout"]]
            fit_scores = [p["score"] for p in data["fit"]]
            all_scores = holdout_scores + fit_scores

            min_sibling = min(all_scores) if all_scores else 1.0
            max_sibling = max(all_scores) if all_scores else 0.0
            avg_sibling = sum(all_scores) / len(all_scores) if all_scores else 0.0

            # Count probes with keyword_only weakness
            kw_only_count = sum(1 for p in data["fit"] + data["holdout"]
                               if p["weakness_type"] == "keyword_only")

            print(f"  {bucket} ({anchor['probe_id']}):")
            print(f"    Anchor:  score={anchor['score']:.3f}  headroom={headroom:.1%}  "
                  f"wt={anchor['weakness_type']}")
            print(f"    Siblings: min={min_sibling:.3f} max={max_sibling:.3f} "
                  f"avg={avg_sibling:.3f}")
            print(f"    Keyword-only siblings: {kw_only_count}")

            if headroom < 0.08:
                print(f"    ** LOW HEADROOM: anchor within 8% of ceiling")
            if min_sibling >= 0.95:
                print(f"    ** ALL SIBLINGS AT CEILING: no sensitivity to regression")
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
