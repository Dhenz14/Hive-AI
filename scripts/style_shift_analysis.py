#!/usr/bin/env python3
"""Pre-training Style Shift Analysis (v3.0)

Predicts whether a new training dataset will cause style contamination
before burning GPU time on training. Uses llama-server (no local model loading).

Algorithm:
1. Run 6 QUICK_PROBES against the current model → baseline scores
2. Inject few-shot examples from the new dataset into the prompt context
3. Re-run probes with contaminated context → measure score drop
4. If max domain drop > threshold → warn/block

Usage:
    # Analyze a new dataset before training
    python scripts/style_shift_analysis.py \\
        --new-data datasets/v5_agentic.jsonl \\
        --server-url http://localhost:11435 \\
        --threshold 0.05

    # Calibrate threshold using historical data
    python scripts/style_shift_analysis.py \\
        --new-data datasets/v5_agentic.jsonl \\
        --server-url http://localhost:11435 \\
        --calibrate

    # Strict mode (exit 1 if above threshold)
    python scripts/style_shift_analysis.py \\
        --new-data datasets/v5_agentic.jsonl \\
        --server-url http://localhost:11435 \\
        --strict
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

# Import probe library
sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_library import QUICK_PROBES

SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."


def load_new_data_samples(data_path: str, n_samples: int = 10) -> list[dict]:
    """Load random samples from the new training dataset."""
    records = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if len(records) > n_samples:
        records = random.sample(records, n_samples)
    return records


def format_few_shot_context(samples: list[dict]) -> str:
    """Format new dataset samples as few-shot context to simulate style shift."""
    parts = []
    for s in samples[:5]:  # max 5 examples to keep context reasonable
        inst = s.get("instruction", "")
        out = s.get("output", "")
        # Truncate long outputs to avoid context overflow
        if len(out) > 500:
            out = out[:500] + "..."
        parts.append(f"Example:\nQ: {inst}\nA: {out}")
    return "\n\n".join(parts)


def score_response(response: str, expected_keywords: list[str]) -> float:
    """Score a response based on keyword coverage (70%) + structure (30%).
    Same formula as regression_eval.py for consistency."""
    if not response.strip():
        return 0.0

    response_lower = response.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
    keyword_score = found / len(expected_keywords) if expected_keywords else 0.0

    import re
    structure_signals = []
    structure_signals.append(1.0 if "```" in response else 0.0)
    structure_signals.append(1.0 if re.search(r"(def |fn |func |class |void |int |let |const )", response) else 0.0)
    structure_signals.append(1.0 if 100 < len(response) < 5000 else 0.3)
    prose_text = re.sub(r"```[\s\S]*?```", "", response).strip()
    structure_signals.append(1.0 if len(prose_text) > 50 else 0.2)
    structure_score = sum(structure_signals) / len(structure_signals)

    return keyword_score * 0.7 + structure_score * 0.3


def run_probe(server_url: str, probe, system_prompt: str, timeout: int = 60) -> float:
    """Run a single probe and return score."""
    try:
        resp = requests.post(
            f"{server_url}/v1/chat/completions",
            json={
                "model": "hiveai",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": probe.prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1024,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"].get("content", "")
            return score_response(content, probe.expected_keywords)
    except Exception:
        pass
    return 0.0


def analyze_style_shift(server_url: str, new_data_path: str, n_samples: int = 10) -> dict:
    """Run baseline + contaminated probes, return per-domain shift scores."""
    print("Loading new dataset samples...")
    samples = load_new_data_samples(new_data_path, n_samples)
    if not samples:
        print("ERROR: No valid samples in dataset")
        return {}

    few_shot = format_few_shot_context(samples)
    print(f"  Using {len(samples)} few-shot examples ({len(few_shot)} chars)")

    # Phase 1: Baseline probes (clean)
    print("\nRunning baseline probes (clean)...")
    baseline = {}
    for probe in QUICK_PROBES:
        score = run_probe(server_url, probe, SYSTEM_PROMPT)
        baseline[probe.domain] = score
        print(f"  {probe.domain:12s}: {score:.3f}")

    # Phase 2: Contaminated probes (with few-shot new-style context)
    print("\nRunning contaminated probes (with new-style context)...")
    contaminated_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Here are some examples of how you should respond:\n\n"
        f"{few_shot}\n\n"
        f"Now answer the following question in the same style:"
    )
    contaminated = {}
    for probe in QUICK_PROBES:
        score = run_probe(server_url, probe, contaminated_prompt)
        contaminated[probe.domain] = score
        print(f"  {probe.domain:12s}: {score:.3f}")

    # Compute shifts
    shifts = {}
    print("\n" + "=" * 50)
    print("  Style Shift Analysis")
    print("=" * 50)
    for domain in baseline:
        delta = baseline[domain] - contaminated.get(domain, 0.0)
        shifts[domain] = delta
        indicator = "!!!" if delta > 0.05 else ("!" if delta > 0.02 else "")
        print(f"  {domain:12s}: {baseline[domain]:.3f} -> {contaminated[domain]:.3f}  "
              f"(shift: {delta:+.3f}) {indicator}")

    max_shift = max(shifts.values()) if shifts else 0.0
    overall_shift = sum(shifts.values()) / len(shifts) if shifts else 0.0
    print(f"\n  Max domain shift:  {max_shift:+.3f}")
    print(f"  Mean domain shift: {overall_shift:+.3f}")
    print("=" * 50)

    return {
        "baseline": baseline,
        "contaminated": contaminated,
        "shifts": shifts,
        "max_shift": max_shift,
        "overall_shift": overall_shift,
    }


def save_history(result: dict, data_path: str, history_path: str, dataset_style: str = "unknown"):
    """Append result to style_shift_history.json for calibration."""
    history = []
    if os.path.exists(history_path):
        with open(history_path, "r") as f:
            history = json.load(f)

    entry = {
        "dataset": os.path.basename(data_path),
        "style": dataset_style,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "max_shift": result["max_shift"],
        "overall_shift": result["overall_shift"],
        "shifts": result["shifts"],
    }
    history.append(entry)

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"\nHistory saved to {history_path}")


def main():
    parser = argparse.ArgumentParser(description="Pre-training style shift analysis")
    parser.add_argument("--new-data", required=True,
                        help="Path to new training JSONL dataset")
    parser.add_argument("--server-url", type=str, default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="Max acceptable style shift per domain (default: 0.05)")
    parser.add_argument("--n-samples", type=int, default=10,
                        help="Number of new-data samples for few-shot (default: 10)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with code 1 if shift exceeds threshold")
    parser.add_argument("--dataset-style", type=str, default="unknown",
                        choices=["direct", "agentic", "unknown"],
                        help="Style of the new dataset (for history calibration)")
    parser.add_argument("--history", type=str,
                        default=str(Path(__file__).resolve().parent.parent / "style_shift_history.json"),
                        help="Path to shift history JSON for calibration")
    args = parser.parse_args()

    # Health check
    try:
        resp = requests.get(f"{args.server_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"ERROR: llama-server unhealthy: {resp.status_code}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"ERROR: Cannot reach llama-server: {e}")
        sys.exit(1)

    result = analyze_style_shift(args.server_url, args.new_data, args.n_samples)
    if not result:
        sys.exit(1)

    save_history(result, args.new_data, args.history, args.dataset_style)

    # Verdict
    if result["max_shift"] > args.threshold:
        print(f"\nWARNING: Style shift {result['max_shift']:.3f} exceeds threshold {args.threshold}")
        print("  Recommendation: increase replay ratio to 40-50%, or add <direct> anchoring")
        if args.strict:
            print("  STRICT MODE: blocking training run")
            sys.exit(1)
    else:
        print(f"\nPASS: Style shift {result['max_shift']:.3f} within threshold {args.threshold}")

    sys.exit(0)


if __name__ == "__main__":
    main()
