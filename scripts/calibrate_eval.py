#!/usr/bin/env python3
"""
DBC Eval Calibration Script — Empirical Measurement of Check 3 Variance.

Purpose:
    Measure the actual per-challenge score variance when the same adapter
    generates outputs multiple times on the same or different hardware.
    This tells us whether the ±0.05 tolerance for Check 3 (generation
    spot-check) is realistic or needs adjustment.

What it does:
    1. Runs a subset of eval challenges N times with deterministic settings
       (seed=42, temp=0, top_k=1) to measure SAME-MACHINE variance.
    2. Runs again with NON-deterministic settings (temp=0.3, no seed) to
       measure REALISTIC variance (what Check 3 actually faces).
    3. Exports a calibration report that can be compared across machines.
    4. If given a second machine's report, computes CROSS-MACHINE variance.

Usage:
    # Single-machine calibration (measures variance across N runs)
    python scripts/calibrate_eval.py --base-url http://localhost:11435 --runs 5

    # Cross-machine comparison (after running on two machines)
    python scripts/calibrate_eval.py --compare evals/calibration/machineA.json evals/calibration/machineB.json

    # Dry run (list challenges without running)
    python scripts/calibrate_eval.py --dry-run

Output:
    evals/calibration/{hostname}_{timestamp}.json

DBC Plan Reference:
    This implements the "Pre-Launch Calibration" section of the Eval
    Verification Protocol (HIVE_AI_DBC_PLAN.md v3.6).
"""

import argparse
import json
import logging
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("calibrate_eval")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHALLENGES_PATH = Path(__file__).parent / "eval_challenges.json"
CALIBRATION_DIR = Path(__file__).parent.parent / "evals" / "calibration"
DEFAULT_SPOT_CHECK_SIZE = 25
DBC_EPOCH_SEED = 42
DEFAULT_RUNS = 5
MAX_RETRIES = 2
REQUEST_TIMEOUT = 300  # 5 minutes per challenge


# ---------------------------------------------------------------------------
# LLM Call (deterministic + non-deterministic modes)
# ---------------------------------------------------------------------------
def call_llama_server(
    prompt: str,
    base_url: str,
    *,
    temperature: float = 0.0,
    seed: int | None = 42,
    top_k: int = 1,
    max_tokens: int = 4096,
) -> dict:
    """Call llama-server with explicit determinism controls."""
    import requests

    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    payload = {
        "model": "calibration",
        "messages": [
            {"role": "system", "content": CODING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    # Deterministic controls (llama-server supports these via OpenAI-compat)
    if seed is not None:
        payload["seed"] = seed
    if top_k is not None:
        payload["top_k"] = top_k

    base = base_url.rstrip("/")
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp = requests.post(
                f"{base}/v1/chat/completions",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.time() - t0) * 1000)

            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")

            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            content = content.strip()

            full_for_explain = (
                (reasoning + "\n\n" + content).strip() if reasoning else content
            )

            usage = data.get("usage", {})
            return {
                "content": content,
                "full_for_explain": full_for_explain,
                "tokens_eval": usage.get("completion_tokens", 0),
                "duration_ms": elapsed_ms,
                "error": None,
            }
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 10 * (attempt + 1)
                logger.warning(f"Attempt {attempt+1} failed: {e} — retry in {wait}s")
                time.sleep(wait)
            else:
                return {
                    "content": "",
                    "full_for_explain": "",
                    "tokens_eval": 0,
                    "duration_ms": 0,
                    "error": str(e),
                }


# ---------------------------------------------------------------------------
# Scoring (imported from run_eval.py — pure deterministic functions)
# ---------------------------------------------------------------------------
def score_challenge(response: str, challenge: dict) -> dict:
    """Score a single challenge response. Returns per-dimension scores."""
    # Import scoring functions from eval runner
    sys.path.insert(0, str(Path(__file__).parent))
    from run_eval import (
        compute_weighted_score,
        score_code_validity,
        score_concept_coverage,
        score_explanation_quality,
        score_test_passing,
    )

    code_validity = score_code_validity(response)
    test_passing = score_test_passing(response, challenge.get("test_code"))
    concept_coverage = score_concept_coverage(
        response, challenge.get("expected_concepts", [])
    )
    explanation = score_explanation_quality(response)
    overall = compute_weighted_score(
        code_validity, test_passing, concept_coverage, explanation
    )

    return {
        "code_validity": code_validity,
        "test_passing": test_passing,
        "concept_coverage": concept_coverage,
        "explanation": explanation,
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Challenge Selection (mirrors DBC spot-check protocol)
# ---------------------------------------------------------------------------
def select_spot_check_challenges(
    challenges: list[dict], seed: int, size: int
) -> list[dict]:
    """Select the spot-check subset using the epoch seed.

    This mirrors the DBC protocol: the verifier picks the SAME random subset
    as the trainer using the shared epoch seed.
    """
    rng = random.Random(seed)
    indices = rng.sample(range(len(challenges)), min(size, len(challenges)))
    return [challenges[i] for i in sorted(indices)]


# ---------------------------------------------------------------------------
# Single Run
# ---------------------------------------------------------------------------
def run_single_pass(
    challenges: list[dict],
    base_url: str,
    *,
    temperature: float,
    seed: int | None,
    top_k: int | None,
    run_label: str,
) -> list[dict]:
    """Run all challenges once and return per-challenge results."""
    results = []
    total = len(challenges)

    for i, ch in enumerate(challenges):
        logger.info(
            f"  [{run_label}] {i+1}/{total} — {ch['id']} ({ch['category']})"
        )

        llm_result = call_llama_server(
            ch["instruction"],
            base_url,
            temperature=temperature,
            seed=seed,
            top_k=top_k,
        )

        if llm_result["error"]:
            logger.error(f"    ERROR: {llm_result['error']}")
            results.append(
                {
                    "id": ch["id"],
                    "category": ch["category"],
                    "error": llm_result["error"],
                    "scores": None,
                    "response_hash": None,
                    "response_length": 0,
                    "duration_ms": llm_result["duration_ms"],
                }
            )
            continue

        response = llm_result["content"]
        scores = score_challenge(response, ch)

        # Hash the response to detect exact text matches across runs
        import hashlib

        response_hash = hashlib.sha256(response.encode()).hexdigest()[:16]

        logger.info(
            f"    score={scores['overall']:.3f}  hash={response_hash}  "
            f"({llm_result['duration_ms']}ms)"
        )

        results.append(
            {
                "id": ch["id"],
                "category": ch["category"],
                "scores": scores,
                "response_hash": response_hash,
                "response_length": len(response),
                "duration_ms": llm_result["duration_ms"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Variance Analysis
# ---------------------------------------------------------------------------
def analyze_variance(all_runs: list[list[dict]], mode_label: str) -> dict:
    """Analyze per-challenge variance across multiple runs.

    Returns:
        dict with per-challenge and aggregate statistics.
    """
    # Group by challenge ID
    by_challenge = {}
    for run_idx, run_results in enumerate(all_runs):
        for result in run_results:
            cid = result["id"]
            if cid not in by_challenge:
                by_challenge[cid] = {
                    "id": cid,
                    "category": result["category"],
                    "runs": [],
                }
            by_challenge[cid]["runs"].append(
                {
                    "run": run_idx,
                    "scores": result["scores"],
                    "response_hash": result["response_hash"],
                    "error": result.get("error"),
                }
            )

    # Compute per-challenge variance
    challenge_stats = []
    all_variances = []
    all_ranges = []
    text_match_counts = []

    for cid, data in sorted(by_challenge.items()):
        valid_runs = [r for r in data["runs"] if r["scores"] is not None]
        if len(valid_runs) < 2:
            continue

        overall_scores = [r["scores"]["overall"] for r in valid_runs]
        hashes = [r["response_hash"] for r in valid_runs]

        # Are all responses identical text?
        all_identical = len(set(hashes)) == 1
        unique_responses = len(set(hashes))

        variance = statistics.variance(overall_scores)
        stdev = statistics.stdev(overall_scores)
        score_range = max(overall_scores) - min(overall_scores)
        mean_score = statistics.mean(overall_scores)

        stat = {
            "id": cid,
            "category": data["category"],
            "mean": round(mean_score, 4),
            "stdev": round(stdev, 4),
            "variance": round(variance, 6),
            "range": round(score_range, 4),
            "min": round(min(overall_scores), 4),
            "max": round(max(overall_scores), 4),
            "all_scores": [round(s, 4) for s in overall_scores],
            "text_identical": all_identical,
            "unique_responses": unique_responses,
        }

        # Per-dimension variance
        for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
            dim_scores = [
                r["scores"][dim]
                for r in valid_runs
                if r["scores"][dim] is not None
            ]
            if len(dim_scores) >= 2:
                stat[f"{dim}_stdev"] = round(statistics.stdev(dim_scores), 4)
                stat[f"{dim}_range"] = round(
                    max(dim_scores) - min(dim_scores), 4
                )

        challenge_stats.append(stat)
        all_variances.append(variance)
        all_ranges.append(score_range)
        text_match_counts.append(1 if all_identical else 0)

    if not challenge_stats:
        return {"mode": mode_label, "error": "No valid challenge pairs to compare"}

    # Aggregate statistics
    mean_variance = statistics.mean(all_variances)
    max_variance = max(all_variances)
    mean_range = statistics.mean(all_ranges)
    max_range = max(all_ranges)
    text_identity_rate = sum(text_match_counts) / len(text_match_counts)

    # Recommended tolerance (3-sigma of the max observed stdev)
    max_stdev = max(s["stdev"] for s in challenge_stats)
    recommended_tolerance = round(max(3 * max_stdev, 0.05), 3)

    # Statistical aggregate tolerance (for mean of 25 challenges)
    # CLT: stdev_of_mean = stdev / sqrt(n)
    mean_stdev = statistics.mean([s["stdev"] for s in challenge_stats])
    import math

    aggregate_stdev = mean_stdev / math.sqrt(DEFAULT_SPOT_CHECK_SIZE)
    recommended_aggregate_tolerance = round(max(3 * aggregate_stdev, 0.02), 3)

    # Determine confidence tier
    if max_range <= 0.05:
        tier = "HIGH_CONFIDENCE"
        tier_description = (
            "Per-challenge variance is within ±0.05. Check 3 at full 20% weight "
            "with per-challenge tolerance is viable."
        )
        recommended_check3_weight = 0.20
    elif max_range <= 0.15:
        tier = "MEDIUM_CONFIDENCE"
        tier_description = (
            "Per-challenge variance exceeds ±0.05 but aggregate mean is stable. "
            "Switch to STATISTICAL CHECK 3: compare mean of 25 challenges "
            f"within ±{recommended_aggregate_tolerance} instead of per-challenge."
        )
        recommended_check3_weight = 0.20
    elif max_range <= 0.30:
        tier = "LOW_CONFIDENCE"
        tier_description = (
            "High per-challenge variance. Reduce Check 3 weight to 10% and use "
            "RELATIVE verification (adapter must beat previous version) instead "
            "of absolute score matching."
        )
        recommended_check3_weight = 0.10
    else:
        tier = "UNRELIABLE"
        tier_description = (
            "Extreme variance. Check 3 generation spot-check is not viable on "
            "this hardware combination. Rely on Checks 1+2 (80% deterministic "
            "weight) only. Set Check 3 weight to 0."
        )
        recommended_check3_weight = 0.0

    # Find worst offenders
    worst_challenges = sorted(challenge_stats, key=lambda s: s["range"], reverse=True)[
        :5
    ]

    return {
        "mode": mode_label,
        "num_challenges": len(challenge_stats),
        "num_runs": len(all_runs),
        "aggregate": {
            "mean_variance": round(mean_variance, 6),
            "max_variance": round(max_variance, 6),
            "mean_range": round(mean_range, 4),
            "max_range": round(max_range, 4),
            "mean_stdev": round(mean_stdev, 4),
            "max_stdev": round(max_stdev, 4),
            "text_identity_rate": round(text_identity_rate, 3),
        },
        "recommendations": {
            "confidence_tier": tier,
            "description": tier_description,
            "per_challenge_tolerance": recommended_tolerance,
            "aggregate_tolerance": recommended_aggregate_tolerance,
            "check3_weight": recommended_check3_weight,
        },
        "worst_challenges": worst_challenges,
        "per_challenge": challenge_stats,
    }


# ---------------------------------------------------------------------------
# Cross-Machine Comparison
# ---------------------------------------------------------------------------
def compare_machines(path_a: str, path_b: str) -> dict:
    """Compare calibration results from two different machines.

    Computes cross-machine variance for each challenge by comparing
    the mean scores from each machine.
    """
    with open(path_a, encoding="utf-8") as f:
        report_a = json.load(f)
    with open(path_b, encoding="utf-8") as f:
        report_b = json.load(f)

    machine_a = report_a["machine"]
    machine_b = report_b["machine"]

    logger.info(f"Comparing: {machine_a['hostname']} vs {machine_b['hostname']}")

    # Use the non-deterministic analysis (realistic Check 3 scenario)
    # Fall back to deterministic if non-deterministic isn't available
    analysis_key = "analysis_nondeterministic"
    if analysis_key not in report_a:
        analysis_key = "analysis_deterministic"

    stats_a = {
        s["id"]: s for s in report_a[analysis_key].get("per_challenge", [])
    }
    stats_b = {
        s["id"]: s for s in report_b[analysis_key].get("per_challenge", [])
    }

    common_ids = sorted(set(stats_a.keys()) & set(stats_b.keys()))
    if not common_ids:
        return {"error": "No common challenges between the two reports"}

    cross_machine_deltas = []
    per_challenge = []

    for cid in common_ids:
        a_mean = stats_a[cid]["mean"]
        b_mean = stats_b[cid]["mean"]
        delta = abs(a_mean - b_mean)
        cross_machine_deltas.append(delta)

        per_challenge.append(
            {
                "id": cid,
                "category": stats_a[cid]["category"],
                f"mean_{machine_a['hostname']}": a_mean,
                f"mean_{machine_b['hostname']}": b_mean,
                "delta": round(delta, 4),
                "text_match": (
                    stats_a[cid].get("text_identical", False)
                    and stats_b[cid].get("text_identical", False)
                    # Check if deterministic runs produced same hash across machines
                ),
            }
        )

    mean_delta = statistics.mean(cross_machine_deltas)
    max_delta = max(cross_machine_deltas)
    stdev_delta = (
        statistics.stdev(cross_machine_deltas)
        if len(cross_machine_deltas) > 1
        else 0
    )

    import math

    recommended_tolerance = round(max(3 * stdev_delta, max_delta, 0.05), 3)
    aggregate_tolerance = round(
        max(3 * stdev_delta / math.sqrt(DEFAULT_SPOT_CHECK_SIZE), 0.02), 3
    )

    if max_delta <= 0.05:
        tier = "HIGH_CONFIDENCE"
    elif max_delta <= 0.15:
        tier = "MEDIUM_CONFIDENCE"
    else:
        tier = "LOW_CONFIDENCE"

    result = {
        "machine_a": machine_a,
        "machine_b": machine_b,
        "common_challenges": len(common_ids),
        "cross_machine": {
            "mean_delta": round(mean_delta, 4),
            "max_delta": round(max_delta, 4),
            "stdev_delta": round(stdev_delta, 4),
            "confidence_tier": tier,
            "recommended_per_challenge_tolerance": recommended_tolerance,
            "recommended_aggregate_tolerance": aggregate_tolerance,
        },
        "worst_deltas": sorted(per_challenge, key=lambda x: x["delta"], reverse=True)[
            :5
        ],
        "per_challenge": per_challenge,
    }

    return result


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------
def get_machine_info() -> dict:
    """Collect hardware/software profile for the calibration report."""
    info = {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
    }

    # Try to get GPU info
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            info["gpu"] = result.stdout.strip()
    except Exception:
        info["gpu"] = "unknown"

    return info


# ---------------------------------------------------------------------------
# Pretty Print
# ---------------------------------------------------------------------------
def print_summary(report: dict):
    """Print a human-readable summary of the calibration results."""
    machine = report["machine"]
    print("\n" + "=" * 70)
    print("DBC EVAL CALIBRATION REPORT")
    print("=" * 70)
    print(f"Machine:  {machine['hostname']}")
    print(f"GPU:      {machine.get('gpu', 'unknown')}")
    print(f"OS:       {machine['os']}")
    print(f"Time:     {report['timestamp']}")

    for mode in ["analysis_deterministic", "analysis_nondeterministic"]:
        if mode not in report:
            continue
        analysis = report[mode]
        label = analysis["mode"]
        agg = analysis["aggregate"]
        rec = analysis["recommendations"]

        print(f"\n{'─' * 70}")
        print(f"  Mode: {label}")
        print(f"  Challenges: {analysis['num_challenges']} × {analysis['num_runs']} runs")
        print(f"{'─' * 70}")
        print(f"  Mean range:    {agg['mean_range']:.4f}")
        print(f"  Max range:     {agg['max_range']:.4f}")
        print(f"  Mean stdev:    {agg['mean_stdev']:.4f}")
        print(f"  Max stdev:     {agg['max_stdev']:.4f}")
        print(f"  Text identity: {agg['text_identity_rate']:.1%}")
        print()
        print(f"  CONFIDENCE TIER: {rec['confidence_tier']}")
        print(f"  {rec['description']}")
        print()
        print(f"  Recommended per-challenge tolerance: ±{rec['per_challenge_tolerance']}")
        print(f"  Recommended aggregate tolerance:     ±{rec['aggregate_tolerance']}")
        print(f"  Recommended Check 3 weight:          {rec['check3_weight']:.0%}")

        if analysis.get("worst_challenges"):
            print(f"\n  Worst 5 challenges (by score range):")
            for wc in analysis["worst_challenges"]:
                print(
                    f"    {wc['id']:20s}  range={wc['range']:.4f}  "
                    f"stdev={wc['stdev']:.4f}  scores={wc['all_scores']}"
                )

    print("\n" + "=" * 70)


def print_comparison(comparison: dict):
    """Print cross-machine comparison results."""
    cm = comparison["cross_machine"]
    print("\n" + "=" * 70)
    print("CROSS-MACHINE COMPARISON")
    print("=" * 70)
    print(f"Machine A: {comparison['machine_a']['hostname']}")
    print(f"Machine B: {comparison['machine_b']['hostname']}")
    print(f"Common challenges: {comparison['common_challenges']}")
    print()
    print(f"Mean score delta:   {cm['mean_delta']:.4f}")
    print(f"Max score delta:    {cm['max_delta']:.4f}")
    print(f"Stdev delta:        {cm['stdev_delta']:.4f}")
    print(f"Confidence tier:    {cm['confidence_tier']}")
    print()
    print(f"Recommended per-challenge tolerance: ±{cm['recommended_per_challenge_tolerance']}")
    print(f"Recommended aggregate tolerance:     ±{cm['recommended_aggregate_tolerance']}")

    if comparison.get("worst_deltas"):
        print(f"\nWorst 5 cross-machine deltas:")
        for wd in comparison["worst_deltas"]:
            print(f"  {wd['id']:20s}  delta={wd['delta']:.4f}")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="DBC Eval Calibration — Measure Check 3 hardware variance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run calibration on this machine (5 runs, 25 challenges)
  python scripts/calibrate_eval.py --base-url http://localhost:11435

  # Fewer runs for quick check
  python scripts/calibrate_eval.py --base-url http://localhost:11435 --runs 3

  # More challenges for higher confidence
  python scripts/calibrate_eval.py --base-url http://localhost:11435 --challenges 50

  # Compare two machines
  python scripts/calibrate_eval.py --compare evals/calibration/machineA.json evals/calibration/machineB.json
        """,
    )

    parser.add_argument(
        "--base-url",
        type=str,
        help="llama-server base URL (e.g., http://localhost:11435)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Number of runs per mode (default: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--challenges",
        type=int,
        default=DEFAULT_SPOT_CHECK_SIZE,
        help=f"Number of challenges to calibrate (default: {DEFAULT_SPOT_CHECK_SIZE})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DBC_EPOCH_SEED,
        help=f"Epoch seed for challenge selection (default: {DBC_EPOCH_SEED})",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("REPORT_A", "REPORT_B"),
        help="Compare two calibration reports from different machines",
    )
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Only run deterministic mode (seed=42, temp=0) — skip realistic mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List selected challenges without running",
    )

    args = parser.parse_args()

    # --- Cross-machine comparison mode ---
    if args.compare:
        comparison = compare_machines(args.compare[0], args.compare[1])
        if "error" in comparison:
            logger.error(comparison["error"])
            sys.exit(1)
        print_comparison(comparison)

        # Save comparison report
        CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CALIBRATION_DIR / "cross_machine_comparison.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)
        logger.info(f"Comparison saved to {out_path}")
        return

    # --- Calibration mode ---
    if not args.base_url:
        parser.error("--base-url is required for calibration (e.g., http://localhost:11435)")

    # Load challenges
    if not CHALLENGES_PATH.exists():
        logger.error(f"Challenges not found: {CHALLENGES_PATH}")
        sys.exit(1)

    with open(CHALLENGES_PATH, encoding="utf-8") as f:
        all_challenges = json.load(f)

    logger.info(f"Loaded {len(all_challenges)} challenges from {CHALLENGES_PATH}")

    # Select spot-check subset
    selected = select_spot_check_challenges(
        all_challenges, args.seed, args.challenges
    )
    logger.info(
        f"Selected {len(selected)} challenges (seed={args.seed}): "
        + ", ".join(c["id"] for c in selected[:5])
        + ("..." if len(selected) > 5 else "")
    )

    if args.dry_run:
        print(f"\nDry run — {len(selected)} challenges would be run:\n")
        for ch in selected:
            print(f"  {ch['id']:20s}  {ch['category']:15s}  diff={ch['difficulty']}")
        print(f"\nWith {args.runs} runs × 2 modes = {args.runs * 2} total passes")
        print(f"Estimated time: ~{len(selected) * args.runs * 2 * 30 // 60} minutes")
        return

    # Collect machine info
    machine_info = get_machine_info()
    logger.info(f"Machine: {machine_info['hostname']} / {machine_info.get('gpu', '?')}")

    # --- Phase 1: Deterministic runs (seed=42, temp=0, top_k=1) ---
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 1: DETERMINISTIC MODE (seed=42, temp=0, top_k=1)")
    logger.info(f"{'='*60}")

    deterministic_runs = []
    for run in range(args.runs):
        logger.info(f"\n--- Deterministic run {run+1}/{args.runs} ---")
        results = run_single_pass(
            selected,
            args.base_url,
            temperature=0.0,
            seed=42,
            top_k=1,
            run_label=f"det-{run+1}",
        )
        deterministic_runs.append(results)

    det_analysis = analyze_variance(deterministic_runs, "DETERMINISTIC (seed=42, temp=0)")

    # --- Phase 2: Non-deterministic runs (temp=0.3, no seed) ---
    nondet_analysis = None
    nondet_runs = []
    if not args.deterministic_only:
        logger.info(f"\n{'='*60}")
        logger.info(f"PHASE 2: REALISTIC MODE (temp=0.3, no seed)")
        logger.info(f"{'='*60}")

        for run in range(args.runs):
            logger.info(f"\n--- Realistic run {run+1}/{args.runs} ---")
            results = run_single_pass(
                selected,
                args.base_url,
                temperature=0.3,
                seed=None,
                top_k=None,
                run_label=f"real-{run+1}",
            )
            nondet_runs.append(results)

        nondet_analysis = analyze_variance(
            nondet_runs, "REALISTIC (temp=0.3, no seed)"
        )

    # --- Build report ---
    report = {
        "version": "1.0",
        "dbc_plan_version": "3.6",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "machine": machine_info,
        "config": {
            "num_runs": args.runs,
            "num_challenges": len(selected),
            "epoch_seed": args.seed,
            "challenges_file": str(CHALLENGES_PATH),
        },
        "challenge_ids": [c["id"] for c in selected],
        "analysis_deterministic": det_analysis,
    }

    if nondet_analysis:
        report["analysis_nondeterministic"] = nondet_analysis

    # --- Final recommendation ---
    # Use the MORE conservative (worse) of the two analyses
    primary = nondet_analysis if nondet_analysis else det_analysis
    report["final_recommendation"] = {
        "confidence_tier": primary["recommendations"]["confidence_tier"],
        "per_challenge_tolerance": primary["recommendations"]["per_challenge_tolerance"],
        "aggregate_tolerance": primary["recommendations"]["aggregate_tolerance"],
        "check3_weight": primary["recommendations"]["check3_weight"],
        "protocol_config": {
            "type": "protocol",
            "eval_tolerance": primary["recommendations"]["per_challenge_tolerance"],
            "aggregate_tolerance": primary["recommendations"]["aggregate_tolerance"],
            "spot_check_size": args.challenges,
            "check3_weight": primary["recommendations"]["check3_weight"],
            "calibration_machine": machine_info["hostname"],
            "calibration_runs": args.runs,
        },
    }

    # --- Save report ---
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    hostname = machine_info["hostname"].replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = CALIBRATION_DIR / f"{hostname}_{timestamp}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\nCalibration report saved to {out_path}")

    # --- Print summary ---
    print_summary(report)

    # --- Print protocol config for on-chain ---
    rec = report["final_recommendation"]
    print("\nON-CHAIN PROTOCOL CONFIG (paste into DBC protocol operation):")
    print(json.dumps(rec["protocol_config"], indent=2))


if __name__ == "__main__":
    main()
