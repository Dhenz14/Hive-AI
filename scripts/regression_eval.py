"""Regression Evaluation: Multi-domain probes with score ledger.

Runs 60 domain probes (10 per domain x 6 domains) against llama-server,
scores each domain, compares against historical best scores in score_ledger.json.

FAIL if any domain drops > threshold (default 0.03) from its best score.
PASS -> update ledger with new scores.

Probes defined in probe_library.py (60 probes across 6 domains).

Usage:
    # Baseline eval (first time — populates ledger)
    python scripts/regression_eval.py --model-version v1.0

    # After merge — check for regression
    python scripts/regression_eval.py --model-version v1-hive --threshold 0.03

    # Custom server URL
    python scripts/regression_eval.py --model-version v1.0 --server-url http://localhost:11435

    # Quick mode (original 18 probes only, for fast checks)
    python scripts/regression_eval.py --model-version v1.0 --quick
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

# Import probe library
sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_library import ALL_PROBES, Probe, DOMAINS

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."
TEMPERATURE = 0.0  # Deterministic decoding — no sampling variance between runs
MAX_TOKENS = 2048  # Thinking disabled via system prompt; reasoning fallback if needed
TIMEOUT = 120  # seconds per probe

# Original 18 probe IDs for --quick mode (backward compatibility)
QUICK_PROBE_IDS = {
    "py-decorators", "py-async-gen", "py-metaclass",
    "rs-ownership", "rs-tokio", "rs-traits",
    "go-workers", "go-interfaces", "go-channels",
    "cpp-raii", "cpp-variadic", "cpp-move",
    "js-event-loop", "js-promises", "js-generics",
    "hive-custom-json", "hive-rc", "hive-keys",
}

# Full probe list — imported from probe_library (60 probes)
PROBES = ALL_PROBES


def score_response(response: str, expected_keywords: list) -> float:
    """Score a response based on keyword coverage + structural quality.

    Combines keyword coverage (70%) with structural signals (30%) to avoid
    inflated scores from keyword-stuffed but low-quality responses.

    Structural signals:
    - Contains code blocks (fenced with ```)
    - Has function/class definitions
    - Has reasonable length (not trivially short)
    - Has explanatory prose (not just code dumps)
    """
    if not response or not response.strip():
        return 0.0
    text = response.lower()

    # Keyword coverage (unique matches only — "buffer" counts once even if
    # it appears 10 times; prevents score inflation from repetition)
    found = sum(1 for kw in expected_keywords if kw.lower() in text)
    keyword_score = found / len(expected_keywords) if expected_keywords else 0.0

    # Structural quality signals
    structure_signals = []

    # Has fenced code blocks
    has_code = bool(re.search(r"```\w*\n", response))
    structure_signals.append(1.0 if has_code else 0.0)

    # Has function/class/struct definitions (language-agnostic patterns)
    has_definitions = bool(re.search(
        r"\b(def |fn |func |function |class |struct |impl |interface )\b",
        response
    ))
    structure_signals.append(1.0 if has_definitions else 0.0)

    # Reasonable length (>200 chars for a coding response)
    structure_signals.append(1.0 if len(response.strip()) > 200 else 0.3)

    # Has explanatory prose (not just a code dump)
    prose_text = re.sub(r"```[\s\S]*?```", "", response).strip()
    has_prose = len(prose_text) > 50
    structure_signals.append(1.0 if has_prose else 0.2)

    structure_score = sum(structure_signals) / len(structure_signals)

    # Combined: 70% keyword coverage, 30% structural quality
    return keyword_score * 0.7 + structure_score * 0.3


def run_probe(probe: Probe, server_url: str, max_retries: int = 2) -> tuple[float, str]:
    """Run a single probe against llama-server and return (score, response).
    Retries on empty responses (llama-server intermittent issue)."""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                f"{server_url}/v1/chat/completions",
                json={
                    "model": "hiveai",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": probe.prompt},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "top_k": 1,
                    "seed": 42,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content", "")
                reasoning = msg.get("reasoning_content", "")
                if not content.strip() and attempt < max_retries:
                    print(f"    RETRY {attempt+1}/{max_retries}: empty response, retrying...")
                    time.sleep(2)
                    continue
                # Use content for scoring; fall back to reasoning if content empty
                # (thinking models may put all knowledge in reasoning_content)
                score_text = content if content.strip() else reasoning
                if score_text != content and score_text:
                    print(f"    NOTE: scoring from reasoning_content ({len(reasoning)} chars)")
                score = score_response(score_text, probe.expected_keywords)
                return score, score_text
            else:
                print(f"    ERROR: {resp.status_code} — {resp.text[:200]}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return 0.0, f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            print(f"    ERROR: {e}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            return 0.0, str(e)
    return 0.0, "max retries exceeded"


def run_all_probes(server_url: str, quick: bool = False) -> dict:
    """Run domain probes, return {domain: score} dict.

    Args:
        server_url: llama-server URL
        quick: If True, use original 18 probes only (backward compatible)
               If False, use all 60 probes (10 per domain)
    """
    probes = [p for p in PROBES if p.id in QUICK_PROBE_IDS] if quick else PROBES
    domain_scores = defaultdict(list)
    total = len(probes)

    mode = "QUICK (18 probes)" if quick else "FULL (60 probes)"
    print(f"Running {total} probes against {server_url} [{mode}]...")
    start = time.time()

    for i, probe in enumerate(probes):
        print(f"  [{i+1}/{total}] {probe.domain}: {probe.prompt[:60]}...")
        score, response = run_probe(probe, server_url)
        domain_scores[probe.domain].append(score)
        kw_found = sum(1 for kw in probe.expected_keywords if kw.lower() in response.lower())
        print(f"    Score: {score:.3f} ({kw_found}/{len(probe.expected_keywords)} keywords)"
              f" [{probe.id}]")

    elapsed = time.time() - start

    # Average per domain
    avg_scores = {}
    for domain, scores in sorted(domain_scores.items()):
        avg_scores[domain] = round(sum(scores) / len(scores), 4)

    print(f"\nProbes completed in {elapsed:.0f}s ({len(probes)} probes, "
          f"{len(avg_scores)} domains)")
    return avg_scores


def load_ledger(ledger_path: str) -> dict:
    """Load score ledger from JSON file."""
    if os.path.exists(ledger_path):
        with open(ledger_path, "r") as f:
            return json.load(f)
    return {}


def save_ledger(ledger: dict, ledger_path: str):
    """Save score ledger to JSON file."""
    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2)


def check_regression(current_scores: dict, ledger: dict,
                      threshold: float, warn_threshold: float) -> tuple[bool, list]:
    """Check for regression against historical best scores.
    Returns (passed, list_of_issues)."""
    if not ledger:
        return True, ["No historical data — baseline run"]

    # Find best score per domain across all versions
    best_scores = {}
    for version_data in ledger.values():
        if isinstance(version_data, dict):
            for domain, score in version_data.items():
                if domain in ("timestamp", "overall"):
                    continue
                if isinstance(score, (int, float)):
                    best_scores[domain] = max(best_scores.get(domain, 0), score)

    issues = []
    passed = True

    for domain, current in current_scores.items():
        best = best_scores.get(domain)
        if best is None:
            continue
        delta = current - best
        if delta < -threshold:
            issues.append(f"FAIL: {domain} dropped {abs(delta):.4f} "
                          f"({best:.4f} -> {current:.4f}, threshold={threshold})")
            passed = False
        elif delta < -warn_threshold:
            issues.append(f"WARN: {domain} dropped {abs(delta):.4f} "
                          f"({best:.4f} -> {current:.4f})")

    return passed, issues


def main():
    parser = argparse.ArgumentParser(description="Multi-domain regression evaluation")
    parser.add_argument("--model-version", required=True,
                        help="Version string (e.g., v1.0, v1-hive)")
    parser.add_argument("--server-url", type=str, default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--threshold", type=float, default=0.03,
                        help="Max allowed regression per domain (default: 0.03)")
    parser.add_argument("--warn-threshold", type=float, default=0.015,
                        help="Warning threshold (default: 0.015)")
    parser.add_argument("--ledger", type=str,
                        default=str(PROJECT_ROOT / "score_ledger.json"),
                        help="Path to score ledger JSON")
    parser.add_argument("--quick", action="store_true",
                        help="Use original 18 probes only (faster, less precise)")
    parser.add_argument("--style-prefix", type=str, default="",
                        help="Style prefix to prepend to system prompt (e.g., '<direct>')")
    args = parser.parse_args()

    # Apply style prefix to system prompt (v3.0 style tokens)
    global SYSTEM_PROMPT
    if args.style_prefix:
        SYSTEM_PROMPT = f"{args.style_prefix}\n{SYSTEM_PROMPT}"

    probe_count = 18 if args.quick else len(PROBES)
    print("=" * 60)
    print(f"  Regression Evaluation — {args.model_version}")
    print("=" * 60)
    print(f"  Server: {args.server_url}")
    print(f"  Probes: {probe_count} ({'quick' if args.quick else 'full'} mode)")
    print(f"  Threshold: {args.threshold} (warn: {args.warn_threshold})")
    print(f"  Ledger: {args.ledger}")
    print("=" * 60)

    # Check server health
    try:
        resp = requests.get(f"{args.server_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"ERROR: llama-server health check failed: {resp.status_code}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"ERROR: Cannot reach llama-server: {e}")
        print("Start llama-server first, then re-run this script.")
        sys.exit(1)

    # Run probes
    scores = run_all_probes(args.server_url, quick=args.quick)

    # Display results
    print("\n" + "=" * 60)
    print("  Domain Scores")
    print("=" * 60)
    overall = sum(scores.values()) / len(scores) if scores else 0
    for domain, score in sorted(scores.items()):
        bar = "#" * int(score * 40)
        print(f"  {domain:12s}: {score:.4f}  |{bar}")
    print(f"  {'OVERALL':12s}: {overall:.4f}")
    print("=" * 60)

    # Load ledger and check regression
    ledger = load_ledger(args.ledger)
    passed, issues = check_regression(scores, ledger, args.threshold, args.warn_threshold)

    if issues:
        print("\nRegression check:")
        for issue in issues:
            print(f"  {issue}")

    # Update ledger only on pass (don't let failed scores become new baseline)
    scores_with_meta = dict(scores)
    scores_with_meta["overall"] = round(overall, 4)
    scores_with_meta["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if passed:
        ledger[args.model_version] = scores_with_meta
        save_ledger(ledger, args.ledger)
        print(f"\nLedger updated: {args.ledger}")
    else:
        # Still record in ledger under a "failed/" prefix for history, but
        # don't overwrite the clean version key so best-scores stay intact
        ledger[f"failed/{args.model_version}"] = scores_with_meta
        save_ledger(ledger, args.ledger)
        print(f"\nLedger updated (marked as failed): {args.ledger}")

    # Final verdict — determine exit code BEFORE any auto-mining that could
    # raise exceptions or otherwise interfere with the exit path
    exit_code = 0 if passed else 1

    print("\n" + "=" * 60)
    if passed:
        print("  PASSED — No regression detected")
        print(f"  {args.model_version} is safe to promote as new base")
    else:
        print("  FAILED — Regression detected!")
        print(f"  DO NOT promote {args.model_version}")
        print("  Consider: increase --replay-ratio or decrease LoRA rank")

        # Auto-trigger failure mining for regressed domains
        try:
            _auto_mine_failures(scores, issues, args.model_version)
        except Exception as e:
            print(f"  WARN: Auto-mining crashed: {e}")

    print("=" * 60)

    sys.exit(exit_code)


def _auto_mine_failures(scores: dict, issues: list, version: str):
    """Auto-generate targeted training pairs for regressed domains."""
    regressed = []
    for issue in issues:
        # Parse "FAIL: <domain> dropped ..." format
        if issue.startswith("FAIL:"):
            parts = issue.split()
            if len(parts) >= 2:
                regressed.append(parts[1])

    if not regressed:
        return

    print(f"\n  Auto-mining failures for: {', '.join(regressed)}")

    # Try weakness_hunter.py first (generates pairs directly)
    weakness_script = PROJECT_ROOT / "scripts" / "weakness_hunter.py"
    if weakness_script.exists():
        try:
            # Build a minimal eval dict for weakness_hunter
            eval_data = {"by_category": {}}
            for domain, score in scores.items():
                if isinstance(score, (int, float)):
                    eval_data["by_category"][domain] = {"score": score}

            # Write temp eval file
            tmp_eval = PROJECT_ROOT / f"_tmp_eval_{version}.json"
            with open(tmp_eval, "w") as f:
                json.dump(eval_data, f)

            result = subprocess.run(
                [sys.executable, str(weakness_script),
                 "--eval", str(tmp_eval),
                 "--generate", "--pairs", "15"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT),
                timeout=300
            )

            tmp_eval.unlink(missing_ok=True)

            if result.returncode == 0:
                print(f"  Weakness patches generated — check loras/training_data/weakness_patches/")
            else:
                print(f"  WARN: weakness_hunter failed: {result.stderr[:150]}")
        except Exception as e:
            print(f"  WARN: Auto-mining failed: {e}")
    else:
        print(f"  WARN: weakness_hunter.py not found — manual intervention needed")


if __name__ == "__main__":
    main()
