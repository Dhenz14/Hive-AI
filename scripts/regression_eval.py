"""Regression Evaluation: Multi-domain probes with score ledger.

Runs 18 domain probes (3 per domain x 6 domains) against llama-server,
scores each domain, compares against historical best scores in score_ledger.json.

FAIL if any domain drops > threshold (default 0.03) from its best score.
PASS -> update ledger with new scores.

Reuses probe definitions from train_sequential.py.

Usage:
    # Baseline eval (first time — populates ledger)
    python scripts/regression_eval.py --model-version v1.0

    # After merge — check for regression
    python scripts/regression_eval.py --model-version v1-hive --threshold 0.03

    # Custom server URL
    python scripts/regression_eval.py --model-version v1.0 --server-url http://localhost:11435
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant."
TEMPERATURE = 0.1
MAX_TOKENS = 768
TIMEOUT = 120  # seconds per probe


# ---------------------------------------------------------------------------
# Domain probe definitions (same as train_sequential.py)
# ---------------------------------------------------------------------------
@dataclass
class Probe:
    domain: str
    prompt: str
    expected_keywords: list


PROBES = [
    # --- Python (3) ---
    Probe("python",
          "Show how to write a Python decorator that adds both pre-call and "
          "post-call hooks, preserving the original function's signature via "
          "functools.wraps. Demonstrate with a timing decorator.",
          ["functools", "wraps", "wrapper", "def", "time", "args", "kwargs"]),
    Probe("python",
          "Write a Python async generator that reads chunks from an aiohttp "
          "response stream and yields parsed JSON objects as they arrive, "
          "handling partial chunks across boundaries.",
          ["async", "yield", "aiohttp", "json", "chunk", "await", "buffer"]),
    Probe("python",
          "Implement a Python metaclass that automatically registers all "
          "subclasses of a base class into a registry dict, keyed by a "
          "'name' class attribute. Show how to look up classes by name.",
          ["metaclass", "__init_subclass__", "registry", "class", "name", "dict"]),

    # --- Rust (3) ---
    Probe("rust",
          "Explain Rust's ownership and borrowing rules with a concrete "
          "example showing how to fix a 'cannot borrow as mutable because "
          "it is also borrowed as immutable' error. Show before and after code.",
          ["borrow", "mut", "&", "let", "fn", "ownership", "lifetime"]),
    Probe("rust",
          "Write a Rust async function using tokio that spawns multiple tasks, "
          "each making an HTTP request, then collects all results using "
          "JoinSet. Handle individual task failures without cancelling others.",
          ["tokio", "async", "spawn", "JoinSet", "await", "Result", "Error"]),
    Probe("rust",
          "Compare trait objects (dyn Trait) vs generics (impl Trait / <T: Trait>) "
          "in Rust. When would you choose dynamic dispatch over static dispatch? "
          "Show a concrete example where trait objects are necessary.",
          ["dyn", "impl", "Trait", "dispatch", "vtable", "Box", "generic"]),

    # --- Go (3) ---
    Probe("go",
          "Implement a Go worker pool pattern with a configurable number of "
          "workers, a job channel, and a results channel. Include graceful "
          "shutdown via context.Context cancellation.",
          ["goroutine", "chan", "context", "WaitGroup", "func", "select", "worker"]),
    Probe("go",
          "Show how Go interface composition works by defining small interfaces "
          "(Reader, Writer) and composing them into a ReadWriter. Demonstrate "
          "how a concrete type satisfies the composed interface implicitly.",
          ["interface", "Reader", "Writer", "func", "struct", "Read", "Write"]),
    Probe("go",
          "Write a Go function that uses select with multiple channels: a data "
          "channel, a done channel, and a time.After timeout. Handle all three "
          "cases and explain the non-deterministic selection behavior.",
          ["select", "case", "chan", "time.After", "done", "func", "default"]),

    # --- C++ (3) ---
    Probe("cpp",
          "Explain RAII in C++ and demonstrate the differences between "
          "unique_ptr, shared_ptr, and weak_ptr. Show a concrete example "
          "where weak_ptr prevents a circular reference memory leak.",
          ["unique_ptr", "shared_ptr", "weak_ptr", "RAII", "destructor", "lock", "cycle"]),
    Probe("cpp",
          "Write a C++ variadic template function that pretty-prints any "
          "number of arguments with their types (using typeid or "
          "if-constexpr). Show fold expressions and parameter pack expansion.",
          ["template", "typename", "Args", "fold", "constexpr", "pack", "variadic"]),
    Probe("cpp",
          "Explain C++ move semantics: what is an rvalue reference (&&), when "
          "does the compiler invoke the move constructor vs copy constructor, "
          "and write a class with both. Show std::move usage.",
          ["move", "&&", "rvalue", "std::move", "constructor", "noexcept", "swap"]),

    # --- JavaScript/TypeScript (3) ---
    Probe("js",
          "Explain the JavaScript event loop in detail: call stack, task queue, "
          "microtask queue, and how setTimeout(fn, 0) interacts with "
          "Promise.resolve().then(). Show the execution order of a tricky example.",
          ["event loop", "microtask", "setTimeout", "Promise", "stack", "queue", "then"]),
    Probe("js",
          "Write a JavaScript function that chains promises to: fetch a user, "
          "fetch their posts, then fetch comments for the first post. Handle "
          "errors at each stage with proper .catch() placement. Then rewrite "
          "using async/await with try/catch.",
          ["Promise", "then", "catch", "async", "await", "fetch", "try"]),
    Probe("js",
          "Write a TypeScript generic function `pipe` that composes N functions "
          "in sequence, where each function's output type matches the next "
          "function's input type. The final type should be inferred correctly.",
          ["generic", "function", "pipe", "type", "infer", "return", "extends"]),

    # --- Hive blockchain (3) ---
    Probe("hive",
          "Write a Python function using the beem library that broadcasts a "
          "custom_json operation to the Hive blockchain for a Hive Engine token "
          "transfer. Use the ssc-mainnet-hive id and posting authority.",
          ["custom_json", "beem", "posting", "ssc-mainnet-hive", "broadcast", "json", "Hive"]),
    Probe("hive",
          "Explain Hive blockchain resource credits (RC): what they are, how "
          "they regenerate, how they limit operations, and write Python code "
          "using beem to check an account's current RC percentage.",
          ["resource", "credit", "RC", "mana", "regenerat", "beem", "account"]),
    Probe("hive",
          "Explain the Hive key hierarchy: owner, active, posting, and memo "
          "keys. What operations does each authorize? Write a Python function "
          "using beem that derives all four keys from a master password.",
          ["owner", "active", "posting", "memo", "key", "beem", "password"]),
]


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


def run_probe(probe: Probe, server_url: str) -> tuple[float, str]:
    """Run a single probe against llama-server and return (score, response)."""
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
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            score = score_response(content, probe.expected_keywords)
            return score, content
        else:
            print(f"    ERROR: {resp.status_code} — {resp.text[:200]}")
            return 0.0, f"HTTP {resp.status_code}"
    except requests.RequestException as e:
        print(f"    ERROR: {e}")
        return 0.0, str(e)


def run_all_probes(server_url: str) -> dict:
    """Run all 18 probes, return {domain: score} dict."""
    domain_scores = defaultdict(list)
    total = len(PROBES)

    print(f"Running {total} probes against {server_url}...")
    start = time.time()

    for i, probe in enumerate(PROBES):
        print(f"  [{i+1}/{total}] {probe.domain}: {probe.prompt[:60]}...")
        score, response = run_probe(probe, server_url)
        domain_scores[probe.domain].append(score)
        print(f"    Score: {score:.3f} ({sum(1 for kw in probe.expected_keywords if kw.lower() in response.lower())}"
              f"/{len(probe.expected_keywords)} keywords)")

    elapsed = time.time() - start

    # Average per domain
    avg_scores = {}
    for domain, scores in sorted(domain_scores.items()):
        avg_scores[domain] = round(sum(scores) / len(scores), 4)

    print(f"\nProbes completed in {elapsed:.0f}s")
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
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Regression Evaluation — {args.model_version}")
    print("=" * 60)
    print(f"  Server: {args.server_url}")
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
    scores = run_all_probes(args.server_url)

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

    # Update ledger
    scores_with_meta = dict(scores)
    scores_with_meta["overall"] = round(overall, 4)
    scores_with_meta["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ledger[args.model_version] = scores_with_meta
    save_ledger(ledger, args.ledger)
    print(f"\nLedger updated: {args.ledger}")

    # Final verdict
    print("\n" + "=" * 60)
    if passed:
        print("  PASSED — No regression detected")
        print(f"  {args.model_version} is safe to promote as new base")
    else:
        print("  FAILED — Regression detected!")
        print(f"  DO NOT promote {args.model_version}")
        print("  Consider: increase --replay-ratio or decrease LoRA rank")

        # Auto-trigger failure mining for regressed domains
        _auto_mine_failures(scores, issues, args.model_version)

    print("=" * 60)

    sys.exit(0 if passed else 1)


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
