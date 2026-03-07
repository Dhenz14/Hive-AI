#!/usr/bin/env python3
"""
mine_failures.py -- Mine model failures for v8 training data.

Queries the v7 LoRA model with all eval challenges, scores responses,
and outputs failures (score < threshold) as training targets.

Usage:
    python scripts/mine_failures.py                          # Full run
    python scripts/mine_failures.py --category rust --limit 20
    python scripts/mine_failures.py --threshold 0.6          # Stricter
"""

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_eval import (
    score_code_validity,
    score_test_passing,
    score_concept_coverage,
    score_explanation_quality,
    compute_weighted_score,
    SANDBOX_TIMEOUT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHALLENGES_PATH = Path(__file__).parent / "eval_challenges.json"
CHALLENGES_HARD_PATH = Path(__file__).parent / "eval_challenges_hard.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "loras" / "training_data" / "v8_failures.jsonl"
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant."
MAX_RETRIES = 3
REQUEST_TIMEOUT = 600  # 10 min per challenge


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------

def set_lora_scale(base_url: str, scale: float):
    """Set the LoRA adapter scale via llama-server API."""
    resp = requests.post(
        f"{base_url}/lora-adapters",
        json=[{"id": 0, "scale": scale}],
        timeout=10,
    )
    resp.raise_for_status()
    time.sleep(0.3)
    logger.info(f"LoRA scale set to {scale}")


def call_model(base_url: str, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> dict:
    """Call llama-server's OpenAI-compatible chat endpoint."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    last_err = None

    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp = requests.post(
                url,
                json={
                    "model": "hiveai",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.time() - t0) * 1000)

            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")

            # Strip inline think tags
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            content = content.strip()

            full_for_explain = ((reasoning + "\n\n" + content).strip()
                                if reasoning else content)

            usage = data.get("usage", {})
            return {
                "content": content,
                "full_for_explain": full_for_explain,
                "tokens_eval": usage.get("completion_tokens", 0),
                "duration_ms": elapsed_ms,
                "error": None,
            }
        except Exception as e:
            last_err = str(e)
            wait = 10 * (attempt + 1)
            logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} failed: {e} -- retry in {wait}s")
            time.sleep(wait)

    return {"content": "", "full_for_explain": "", "tokens_eval": 0,
            "duration_ms": 0, "error": last_err}


# ---------------------------------------------------------------------------
# Challenge loading
# ---------------------------------------------------------------------------

def load_all_challenges() -> list[dict]:
    """Load challenges from eval_challenges.json and eval_challenges_hard.json."""
    challenges = []

    if CHALLENGES_PATH.exists():
        with open(CHALLENGES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} challenges from {CHALLENGES_PATH.name}")
        challenges.extend(data)
    else:
        logger.warning(f"{CHALLENGES_PATH.name} not found")

    if CHALLENGES_HARD_PATH.exists():
        with open(CHALLENGES_HARD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} hard challenges from {CHALLENGES_HARD_PATH.name}")
        challenges.extend(data)
    else:
        logger.info(f"{CHALLENGES_HARD_PATH.name} not found -- skipping hard challenges")

    return challenges


# ---------------------------------------------------------------------------
# Evaluate + score a single challenge
# ---------------------------------------------------------------------------

def evaluate_challenge(challenge: dict, base_url: str) -> dict:
    """Query model, score response, return result with failure info."""
    cid = challenge["id"]
    logger.info(f"  [{cid}] {challenge.get('topic', '?')} (D{challenge.get('difficulty', '?')})...")

    result = call_model(base_url, challenge["instruction"])

    if result["error"]:
        logger.error(f"  [{cid}] ERROR: {result['error']}")
        return {
            "id": cid,
            "category": challenge.get("category", "unknown"),
            "difficulty": challenge.get("difficulty", 0),
            "topic": challenge.get("topic", ""),
            "instruction": challenge["instruction"],
            "response": "",
            "scores": {
                "code_validity": 0.0,
                "test_passing": None,
                "concept_coverage": 0.0,
                "explanation": 0.0,
                "overall": 0.0,
            },
            "error": result["error"],
            "duration_ms": result["duration_ms"],
        }

    response = result["content"]
    response_for_explain = result.get("full_for_explain", response)
    test_code = challenge.get("test_code")

    d1_code = score_code_validity(response)
    d2_test = score_test_passing(response, test_code)
    d3_concept = score_concept_coverage(response, challenge.get("expected_concepts", []))
    d4_explain = score_explanation_quality(response_for_explain)
    overall = compute_weighted_score(d1_code, d2_test, d3_concept, d4_explain)

    logger.info(
        f"  [{cid}] score={overall:.3f} "
        f"(code={d1_code:.2f} test={d2_test if d2_test is not None else 'N/A'} "
        f"concept={d3_concept:.2f} explain={d4_explain:.2f}) "
        f"[{result['duration_ms']}ms]"
    )

    return {
        "id": cid,
        "category": challenge.get("category", "unknown"),
        "difficulty": challenge.get("difficulty", 0),
        "topic": challenge.get("topic", ""),
        "instruction": challenge["instruction"],
        "response": response,
        "scores": {
            "code_validity": round(d1_code, 3),
            "test_passing": round(d2_test, 3) if d2_test is not None else None,
            "concept_coverage": round(d3_concept, 3),
            "explanation": round(d4_explain, 3),
            "overall": round(overall, 3),
        },
        "error": None,
        "duration_ms": result["duration_ms"],
    }


# ---------------------------------------------------------------------------
# Failure extraction
# ---------------------------------------------------------------------------

def get_failure_dims(scores: dict, dim_threshold: float = 0.5) -> list[str]:
    """Return list of scoring dimensions below the dim_threshold."""
    dims = []
    for dim_name in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
        val = scores.get(dim_name)
        if val is not None and val < dim_threshold:
            dims.append(dim_name)
    return dims


def write_failures(results: list[dict], threshold: float, output_path: Path):
    """Write failure records to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            if r["error"]:
                # Errors are always failures
                record = {
                    "challenge_id": r["id"],
                    "category": r["category"],
                    "difficulty": r["difficulty"],
                    "score": 0.0,
                    "instruction": r["instruction"],
                    "model_response": r["response"],
                    "failure_dims": ["error"],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                continue

            overall = r["scores"]["overall"]
            if overall < threshold:
                failure_dims = get_failure_dims(r["scores"])
                record = {
                    "challenge_id": r["id"],
                    "category": r["category"],
                    "difficulty": r["difficulty"],
                    "score": overall,
                    "instruction": r["instruction"],
                    "model_response": r["response"],
                    "failure_dims": failure_dims,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return count


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[dict], threshold: float):
    """Print failure analysis summary."""
    total = len(results)
    errors = sum(1 for r in results if r["error"])
    scored = [r for r in results if not r["error"]]

    failures = [r for r in scored if r["scores"]["overall"] < threshold]
    critical = [r for r in scored if r["scores"]["overall"] < 0.5]

    failure_rate = len(failures) / max(len(scored), 1)

    sep = "=" * 70
    print(f"\n{sep}")
    print("  FAILURE MINING SUMMARY")
    print(sep)
    print(f"  Total challenges:    {total}")
    print(f"  Errors:              {errors}")
    print(f"  Scored:              {len(scored)}")
    print(f"  Failures (<{threshold}):    {len(failures)}  ({failure_rate:.1%})")
    print(f"  Critical (<0.5):     {len(critical)}")

    # By category
    cat_failures = defaultdict(lambda: {"total": 0, "failures": 0, "scores": []})
    for r in scored:
        cat = r["category"]
        cat_failures[cat]["total"] += 1
        cat_failures[cat]["scores"].append(r["scores"]["overall"])
        if r["scores"]["overall"] < threshold:
            cat_failures[cat]["failures"] += 1

    print(f"\n  Failures by Category:")
    print(f"  {'Category':<20s}  {'Fail/Total':>10s}  {'Rate':>6s}  {'Avg Score':>9s}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*6}  {'-'*9}")
    for cat in sorted(cat_failures.keys(), key=lambda c: -cat_failures[c]["failures"]):
        d = cat_failures[cat]
        avg = sum(d["scores"]) / len(d["scores"])
        rate = d["failures"] / d["total"]
        print(f"  {cat:<20s}  {d['failures']:>4d}/{d['total']:<4d}  {rate:>5.0%}  {avg:>8.3f}")

    # Worst 10
    worst = sorted(scored, key=lambda r: r["scores"]["overall"])[:10]
    print(f"\n  Worst 10 Challenges:")
    print(f"  {'ID':<22s}  {'Cat':<14s}  {'Score':>6s}  {'Topic'}")
    print(f"  {'-'*22}  {'-'*14}  {'-'*6}  {'-'*30}")
    for r in worst:
        marker = " ** CRITICAL" if r["scores"]["overall"] < 0.5 else ""
        print(f"  {r['id']:<22s}  {r['category']:<14s}  {r['scores']['overall']:>5.3f}  "
              f"{r.get('topic', '')[:30]}{marker}")

    # Critical failures highlight
    if critical:
        print(f"\n  CRITICAL FAILURES (score < 0.5):")
        for r in sorted(critical, key=lambda x: x["scores"]["overall"]):
            dims = get_failure_dims(r["scores"])
            print(f"    {r['id']:<22s}  {r['scores']['overall']:.3f}  dims={dims}")

    print(f"\n{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mine model failures for v8 training data")
    parser.add_argument("--base-url", type=str, default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--threshold", type=float, default=0.7,
                        help="Score below this = failure (default: 0.7)")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter to a single category")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max challenges to evaluate (0=all)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help="Output JSONL path")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_path = Path(args.output)

    # --- Connectivity check ---
    try:
        requests.get(f"{base_url}/health", timeout=5)
    except requests.ConnectionError:
        logger.error(f"Cannot reach llama-server at {base_url}. Is it running?")
        sys.exit(1)

    # --- Set LoRA scale to 1.0 ---
    logger.info("Enabling LoRA (scale=1.0)...")
    set_lora_scale(base_url, 1.0)

    # --- Load challenges ---
    challenges = load_all_challenges()
    if not challenges:
        logger.error("No challenges found.")
        sys.exit(1)

    # --- Filters ---
    if args.category:
        challenges = [c for c in challenges if c.get("category") == args.category]
        logger.info(f"Filtered to category '{args.category}': {len(challenges)} challenges")

    if args.limit > 0:
        challenges = challenges[:args.limit]
        logger.info(f"Limited to {args.limit} challenges")

    if not challenges:
        logger.error("No challenges after filtering.")
        sys.exit(1)

    # --- Run evaluation ---
    logger.info(f"Evaluating {len(challenges)} challenges against LoRA model...")
    t_start = time.time()
    results = []

    try:
        for i, challenge in enumerate(challenges, 1):
            logger.info(f"\n[{i}/{len(challenges)}] {challenge['id']}")
            result = evaluate_challenge(challenge, base_url)
            results.append(result)

            # Progress update every 10
            if i % 10 == 0:
                scored = [r for r in results if not r["error"]]
                if scored:
                    avg = sum(r["scores"]["overall"] for r in scored) / len(scored)
                    fails = sum(1 for r in scored if r["scores"]["overall"] < args.threshold)
                    elapsed = time.time() - t_start
                    eta = (elapsed / i) * (len(challenges) - i)
                    logger.info(
                        f"  --- Progress: {i}/{len(challenges)} | avg={avg:.3f} | "
                        f"failures={fails} | ETA {eta/60:.1f}min ---"
                    )
    finally:
        # Always restore LoRA scale
        try:
            set_lora_scale(base_url, 1.0)
            logger.info("LoRA scale confirmed at 1.0")
        except Exception:
            logger.warning("Failed to restore LoRA scale")

    elapsed_total = time.time() - t_start
    logger.info(f"Evaluation complete in {elapsed_total/60:.1f} minutes")

    # --- Write failures ---
    fail_count = write_failures(results, args.threshold, output_path)
    logger.info(f"Wrote {fail_count} failures to {output_path}")

    # --- Print summary ---
    print_summary(results, args.threshold)


if __name__ == "__main__":
    main()
