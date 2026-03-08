#!/usr/bin/env python3
"""
train_sequential.py -- Sequential Lock-in Training for HiveAI.

Train one domain at a time. Before and after each training run, probe ALL
domains with targeted questions.  The new adapter is "locked in" only if:
  1. The trained domain's score improved by >= 0.02
  2. No other domain's score dropped by > 0.02

If either condition fails, the adapter is discarded (rollback).
Each locked-in adapter becomes the warm-start for the next domain.

Usage:
    # Step 1: Probe current model (no training, just scores)
    python scripts/train_sequential.py --dry-run

    # Step 2: Train C++ on base (no warm-start)
    python scripts/train_sequential.py --domain cpp \\
        --data loras/training_data/categories/cpp_with_replay.jsonl \\
        --warm-start none --output-dir loras/v9_step1_cpp

    # Step 3: Train Go, warm-starting from locked C++ adapter
    python scripts/train_sequential.py --domain go \\
        --data loras/training_data/categories/go_with_replay.jsonl \\
        --warm-start loras/v9_step1_cpp --output-dir loras/v9_step2_go

    # Step 4: Train Rust, warm-starting from locked Go adapter
    python scripts/train_sequential.py --domain rust \\
        --data loras/training_data/categories/rust_with_replay.jsonl \\
        --warm-start loras/v9_step2_go --output-dir loras/v9_step3_rust

    # Full pipeline (run sequentially, each depends on previous lock-in):
    for step in cpp go rust hive python js; do
        python scripts/train_sequential.py --domain $step ...
    done
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant."
TEMPERATURE = 0.1
MAX_TOKENS = 768
TIMEOUT = 120  # seconds per probe

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WSL_PROJECT = "/opt/hiveai/project"
HF_BASE_CACHE = "/root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d"


# ---------------------------------------------------------------------------
# Domain probe definitions
# ---------------------------------------------------------------------------

@dataclass
class Probe:
    domain: str
    prompt: str
    expected_keywords: List[str]


PROBES = [
    # --- Python (3) ---
    Probe(
        domain="python",
        prompt=(
            "Show how to write a Python decorator that adds both pre-call and "
            "post-call hooks, preserving the original function's signature via "
            "functools.wraps. Demonstrate with a timing decorator."
        ),
        expected_keywords=["functools", "wraps", "wrapper", "def", "time", "args", "kwargs"],
    ),
    Probe(
        domain="python",
        prompt=(
            "Write a Python async generator that reads chunks from an aiohttp "
            "response stream and yields parsed JSON objects as they arrive, "
            "handling partial chunks across boundaries."
        ),
        expected_keywords=["async", "yield", "aiohttp", "json", "chunk", "await", "buffer"],
    ),
    Probe(
        domain="python",
        prompt=(
            "Implement a Python metaclass that automatically registers all "
            "subclasses of a base class into a registry dict, keyed by a "
            "'name' class attribute. Show how to look up classes by name."
        ),
        expected_keywords=["metaclass", "__init_subclass__", "registry", "class", "name", "dict"],
    ),

    # --- Rust (3) ---
    Probe(
        domain="rust",
        prompt=(
            "Explain Rust's ownership and borrowing rules with a concrete "
            "example showing how to fix a 'cannot borrow as mutable because "
            "it is also borrowed as immutable' error. Show before and after code."
        ),
        expected_keywords=["borrow", "mut", "&", "let", "fn", "ownership", "lifetime"],
    ),
    Probe(
        domain="rust",
        prompt=(
            "Write a Rust async function using tokio that spawns multiple tasks, "
            "each making an HTTP request, then collects all results using "
            "JoinSet. Handle individual task failures without cancelling others."
        ),
        expected_keywords=["tokio", "async", "spawn", "JoinSet", "await", "Result", "Error"],
    ),
    Probe(
        domain="rust",
        prompt=(
            "Compare trait objects (dyn Trait) vs generics (impl Trait / <T: Trait>) "
            "in Rust. When would you choose dynamic dispatch over static dispatch? "
            "Show a concrete example where trait objects are necessary."
        ),
        expected_keywords=["dyn", "impl", "Trait", "dispatch", "vtable", "Box", "generic"],
    ),

    # --- Go (3) ---
    Probe(
        domain="go",
        prompt=(
            "Implement a Go worker pool pattern with a configurable number of "
            "workers, a job channel, and a results channel. Include graceful "
            "shutdown via context.Context cancellation."
        ),
        expected_keywords=["goroutine", "chan", "context", "WaitGroup", "func", "select", "worker"],
    ),
    Probe(
        domain="go",
        prompt=(
            "Show how Go interface composition works by defining small interfaces "
            "(Reader, Writer) and composing them into a ReadWriter. Demonstrate "
            "how a concrete type satisfies the composed interface implicitly."
        ),
        expected_keywords=["interface", "Reader", "Writer", "func", "struct", "Read", "Write"],
    ),
    Probe(
        domain="go",
        prompt=(
            "Write a Go function that uses select with multiple channels: a data "
            "channel, a done channel, and a time.After timeout. Handle all three "
            "cases and explain the non-deterministic selection behavior."
        ),
        expected_keywords=["select", "case", "chan", "time.After", "done", "func", "default"],
    ),

    # --- C++ (3) ---
    Probe(
        domain="cpp",
        prompt=(
            "Explain RAII in C++ and demonstrate the differences between "
            "unique_ptr, shared_ptr, and weak_ptr. Show a concrete example "
            "where weak_ptr prevents a circular reference memory leak."
        ),
        expected_keywords=["unique_ptr", "shared_ptr", "weak_ptr", "RAII", "destructor", "lock", "cycle"],
    ),
    Probe(
        domain="cpp",
        prompt=(
            "Write a C++ variadic template function that pretty-prints any "
            "number of arguments with their types (using typeid or "
            "if-constexpr). Show fold expressions and parameter pack expansion."
        ),
        expected_keywords=["template", "typename", "Args", "fold", "constexpr", "pack", "variadic"],
    ),
    Probe(
        domain="cpp",
        prompt=(
            "Explain C++ move semantics: what is an rvalue reference (&&), when "
            "does the compiler invoke the move constructor vs copy constructor, "
            "and write a class with both. Show std::move usage."
        ),
        expected_keywords=["move", "&&", "rvalue", "std::move", "constructor", "noexcept", "swap"],
    ),

    # --- JavaScript/TypeScript (3) ---
    Probe(
        domain="js",
        prompt=(
            "Explain the JavaScript event loop in detail: call stack, task queue, "
            "microtask queue, and how setTimeout(fn, 0) interacts with "
            "Promise.resolve().then(). Show the execution order of a tricky example."
        ),
        expected_keywords=["event loop", "microtask", "setTimeout", "Promise", "stack", "queue", "then"],
    ),
    Probe(
        domain="js",
        prompt=(
            "Write a JavaScript function that chains promises to: fetch a user, "
            "fetch their posts, then fetch comments for the first post. Handle "
            "errors at each stage with proper .catch() placement. Then rewrite "
            "using async/await with try/catch."
        ),
        expected_keywords=["Promise", "then", "catch", "async", "await", "fetch", "try"],
    ),
    Probe(
        domain="js",
        prompt=(
            "Write a TypeScript generic function `pipe` that composes N functions "
            "in sequence, where each function's output type matches the next "
            "function's input type. The final type should be inferred correctly."
        ),
        expected_keywords=["generic", "function", "pipe", "type", "infer", "return", "extends"],
    ),

    # --- Hive blockchain (3) ---
    Probe(
        domain="hive",
        prompt=(
            "Write a Python function using the beem library that broadcasts a "
            "custom_json operation to the Hive blockchain for a Hive Engine token "
            "transfer. Use the ssc-mainnet-hive id and posting authority."
        ),
        expected_keywords=["custom_json", "beem", "posting", "ssc-mainnet-hive", "broadcast", "json", "Hive"],
    ),
    Probe(
        domain="hive",
        prompt=(
            "Explain Hive blockchain resource credits (RC): what they are, how "
            "they regenerate, how they limit operations, and write Python code "
            "using beem to check an account's current RC percentage."
        ),
        expected_keywords=["resource", "credit", "RC", "mana", "regenerat", "beem", "account"],
    ),
    Probe(
        domain="hive",
        prompt=(
            "Explain the Hive key hierarchy: owner, active, posting, and memo "
            "keys. What operations does each authorize? Write a Python function "
            "using beem that derives all four keys from a master password."
        ),
        expected_keywords=["owner", "active", "posting", "memo", "key", "beem", "password"],
    ),
]


# ---------------------------------------------------------------------------
# llama-server helpers
# ---------------------------------------------------------------------------

def set_lora_scale(base_url: str, scale: float):
    """Set LoRA adapter scale via llama-server API."""
    resp = requests.post(
        f"{base_url}/lora-adapters",
        json=[{"id": 0, "scale": scale}],
        timeout=10,
    )
    resp.raise_for_status()
    time.sleep(0.3)


def chat_completion(base_url: str, prompt_text: str) -> str:
    """Send a chat completion and return the assistant's response text."""
    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        json={
            "model": "hiveai",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def check_server(base_url: str):
    """Verify llama-server is reachable."""
    try:
        requests.get(f"{base_url}/health", timeout=5)
    except requests.ConnectionError:
        print(f"ERROR: Cannot reach llama-server at {base_url}. Is it running?",
              file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Probe scoring
# ---------------------------------------------------------------------------

def score_probe(response: str, probe: Probe) -> float:
    """Score a single probe response by keyword coverage (case-insensitive)."""
    text_lower = response.lower()
    if not probe.expected_keywords:
        return 1.0
    found = sum(1 for kw in probe.expected_keywords if kw.lower() in text_lower)
    return found / len(probe.expected_keywords)


def run_probes(base_url: str, probes: List[Probe]) -> Dict[str, float]:
    """
    Run all probes against the currently-loaded model config.
    Returns per-domain average scores like {"python": 0.85, "rust": 0.72, ...}.
    """
    domain_scores: Dict[str, List[float]] = {}

    for i, probe in enumerate(probes, 1):
        tag = f"[{probe.domain:>6s}] Probe {i:2d}/{len(probes)}"
        try:
            t0 = time.time()
            response = chat_completion(base_url, probe.prompt)
            elapsed = time.time() - t0
            sc = score_probe(response, probe)
            print(f"  {tag}: {sc:.2f}  ({elapsed:.1f}s)  kw={probe.expected_keywords[:3]}...")
        except Exception as e:
            print(f"  {tag}: ERROR - {e}")
            sc = 0.0

        domain_scores.setdefault(probe.domain, []).append(sc)

    # Average per domain
    return {domain: sum(scores) / len(scores) for domain, scores in domain_scores.items()}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

DOMAINS_ORDER = ["python", "rust", "go", "cpp", "js", "hive"]


def print_score_table(before: Dict[str, float], after: Dict[str, float],
                      trained_domain: Optional[str] = None):
    """Print a clear before/after comparison table."""
    all_domains = sorted(set(list(before.keys()) + list(after.keys())),
                         key=lambda d: DOMAINS_ORDER.index(d) if d in DOMAINS_ORDER else 99)

    print()
    print("=" * 60)
    print(f"  {'Domain':<12}  {'Before':>8}  {'After':>8}  {'Delta':>8}  {'Status'}")
    print("-" * 60)

    for domain in all_domains:
        b = before.get(domain, 0.0)
        a = after.get(domain, 0.0)
        delta = a - b

        if domain == trained_domain:
            if delta >= 0.02:
                status = "IMPROVED"
            elif delta >= 0.0:
                status = "FLAT (need +0.02)"
            else:
                status = "REGRESSED!"
        else:
            if delta < -0.02:
                status = "REGRESSED!"
            else:
                status = "OK"

        marker = " <-- trained" if domain == trained_domain else ""
        print(f"  {domain:<12}  {b:8.3f}  {a:8.3f}  {delta:+8.3f}  {status}{marker}")

    print("-" * 60)
    avg_b = sum(before.values()) / len(before) if before else 0
    avg_a = sum(after.values()) / len(after) if after else 0
    print(f"  {'AVERAGE':<12}  {avg_b:8.3f}  {avg_a:8.3f}  {avg_a - avg_b:+8.3f}")
    print("=" * 60)
    print()


def print_scores_solo(scores: Dict[str, float]):
    """Print current probe scores (no before/after)."""
    all_domains = sorted(scores.keys(),
                         key=lambda d: DOMAINS_ORDER.index(d) if d in DOMAINS_ORDER else 99)
    print()
    print("=" * 40)
    print(f"  {'Domain':<12}  {'Score':>8}")
    print("-" * 40)
    for domain in all_domains:
        print(f"  {domain:<12}  {scores[domain]:8.3f}")
    print("-" * 40)
    avg = sum(scores.values()) / len(scores) if scores else 0
    print(f"  {'AVERAGE':<12}  {avg:8.3f}")
    print("=" * 40)
    print()


# ---------------------------------------------------------------------------
# Training + validation
# ---------------------------------------------------------------------------

def convert_adapter_to_gguf(adapter_dir: str, output_gguf: str):
    """Convert a LoRA adapter directory to GGUF via WSL."""
    # Map Windows path to WSL path
    wsl_adapter = adapter_dir.replace("\\", "/")
    if wsl_adapter[1] == ":":
        drive = wsl_adapter[0].lower()
        wsl_adapter = f"/mnt/{drive}{wsl_adapter[2:]}"

    wsl_output = output_gguf.replace("\\", "/")
    if wsl_output[1] == ":":
        drive = wsl_output[0].lower()
        wsl_output = f"/mnt/{drive}{wsl_output[2:]}"

    cmd = (
        f"wsl -d Ubuntu-24.04 -- bash -c '"
        f"source /opt/hiveai-env/bin/activate && "
        f"if [ ! -f /tmp/llama.cpp/convert_lora_to_gguf.py ]; then "
        f"  git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /tmp/llama.cpp 2>/dev/null || true; "
        f"fi && "
        f"python /tmp/llama.cpp/convert_lora_to_gguf.py "
        f"  --base {HF_BASE_CACHE} "
        f"  {wsl_adapter} "
        f"  --outfile {wsl_output}"
        f"'"
    )
    print(f"\n  Converting adapter to GGUF...")
    print(f"  Adapter: {adapter_dir}")
    print(f"  Output:  {output_gguf}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  GGUF conversion FAILED:\n{result.stderr}", file=sys.stderr)
        return False
    print(f"  GGUF conversion OK")
    return True


def restart_server_with_lora(base_url: str, gguf_path: str):
    """
    Restart llama-server with a new LoRA GGUF.

    Since there's no hot-reload API for swapping LoRA files, we rely on the
    user having restarted the server manually or via a wrapper script.
    For now, we just verify the server is up after a brief wait.
    """
    print(f"\n  NOTE: You need to restart llama-server with --lora {gguf_path}")
    print(f"  Waiting for server to come back up...")

    # Give user time to restart, or auto-detect if already running
    for attempt in range(30):
        try:
            requests.get(f"{base_url}/health", timeout=5)
            print(f"  Server is up.")
            return True
        except requests.ConnectionError:
            if attempt == 0:
                print(f"  Server not responding, waiting...")
            time.sleep(2)

    print(f"  ERROR: Server did not come back up after 60s", file=sys.stderr)
    return False


def train_and_validate(
    domain: str,
    data_path: str,
    warm_start: Optional[str],
    output_dir: str,
    base_url: str,
) -> Optional[str]:
    """
    Full sequential lock-in cycle:
      1. Probe all domains (baseline)
      2. Train the specified domain via WSL
      3. Convert to GGUF
      4. Swap LoRA and re-probe
      5. Compare: lock in or roll back

    Returns the output adapter path if locked in, or None if rolled back.
    """
    print("\n" + "=" * 60)
    print(f"  SEQUENTIAL LOCK-IN: Training domain '{domain}'")
    print(f"  Data:       {data_path}")
    print(f"  Warm-start: {warm_start or 'none (base model)'}")
    print(f"  Output:     {output_dir}")
    print("=" * 60)

    # --- Step 1: Baseline probes ---
    print("\n--- STEP 1: Baseline probes (current model) ---")
    set_lora_scale(base_url, 1.0)
    before_scores = run_probes(base_url, PROBES)
    print_scores_solo(before_scores)

    # --- Step 2: Train in WSL ---
    print("\n--- STEP 2: Training in WSL ---")

    # Build WSL paths
    wsl_data = data_path.replace("\\", "/")
    if len(wsl_data) > 1 and wsl_data[1] == ":":
        drive = wsl_data[0].lower()
        wsl_data = f"/mnt/{drive}{wsl_data[2:]}"

    wsl_output = output_dir.replace("\\", "/")
    if len(wsl_output) > 1 and wsl_output[1] == ":":
        drive = wsl_output[0].lower()
        wsl_output = f"/mnt/{drive}{wsl_output[2:]}"

    wsl_warm = ""
    if warm_start and warm_start.lower() != "none":
        ws = warm_start.replace("\\", "/")
        if len(ws) > 1 and ws[1] == ":":
            drive = ws[0].lower()
            ws = f"/mnt/{drive}{ws[2:]}"
        wsl_warm = f"--warm-start {ws}"

    train_cmd = (
        f"wsl -d Ubuntu-24.04 -- bash -c '"
        f"source /opt/hiveai-env/bin/activate && "
        f"cd {WSL_PROJECT} && "
        f"python scripts/train_v5.py "
        f"  --data {wsl_data} "
        f"  --output-dir {wsl_output} "
        f"  --epochs 2 "
        f"  --no-kl "
        f"  {wsl_warm}"
        f"'"
    )

    print(f"  Running: {train_cmd[:120]}...")
    t0 = time.time()
    result = subprocess.run(train_cmd, shell=True, timeout=14400)  # 4h max
    elapsed = time.time() - t0
    print(f"  Training finished in {elapsed / 60:.1f} minutes (exit code: {result.returncode})")

    if result.returncode != 0:
        print(f"\n  TRAINING FAILED (exit code {result.returncode}). Aborting.", file=sys.stderr)
        return None

    # --- Step 3: Convert to GGUF ---
    print("\n--- STEP 3: Convert adapter to GGUF ---")
    gguf_name = f"hiveai-{Path(output_dir).name}-lora-f16.gguf"
    gguf_path = str(PROJECT_ROOT / "models" / gguf_name)

    if not convert_adapter_to_gguf(output_dir, gguf_path):
        print(f"\n  GGUF CONVERSION FAILED. Aborting.", file=sys.stderr)
        return None

    # --- Step 4: Swap LoRA and re-probe ---
    print("\n--- STEP 4: Restart server with new LoRA and re-probe ---")
    print(f"\n  *** ACTION REQUIRED ***")
    print(f"  Restart llama-server with:")
    print(f"    --lora {gguf_path}")
    print()
    input("  Press Enter when server is restarted (or Ctrl+C to abort)...")

    if not restart_server_with_lora(base_url, gguf_path):
        return None

    set_lora_scale(base_url, 1.0)
    after_scores = run_probes(base_url, PROBES)

    # --- Step 5: Compare and decide ---
    print("\n--- STEP 5: Lock-in decision ---")
    print_score_table(before_scores, after_scores, trained_domain=domain)

    # Check trained domain improved
    trained_before = before_scores.get(domain, 0.0)
    trained_after = after_scores.get(domain, 0.0)
    trained_delta = trained_after - trained_before

    if trained_delta < 0.02:
        print(f"  FAILED: Trained domain '{domain}' did not improve enough "
              f"(delta={trained_delta:+.3f}, need >= +0.020)")
        print(f"  ROLLING BACK -- adapter NOT locked in.")
        return None

    # Check no other domain regressed
    regressed = []
    for d in before_scores:
        if d == domain:
            continue
        delta = after_scores.get(d, 0.0) - before_scores[d]
        if delta < -0.02:
            regressed.append((d, delta))

    if regressed:
        print(f"  FAILED: Other domains regressed:")
        for d, delta in regressed:
            print(f"    {d}: {delta:+.3f}")
        print(f"  ROLLING BACK -- adapter NOT locked in.")
        return None

    # All checks passed
    print(f"  LOCKED IN: Domain '{domain}' improved by {trained_delta:+.3f}, "
          f"no regressions detected.")
    print(f"  Adapter: {output_dir}")
    print(f"  GGUF:    {gguf_path}")
    return output_dir


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sequential Lock-in Training: train one domain, validate all, keep or rollback.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--domain", type=str, default=None,
                        choices=["python", "rust", "go", "cpp", "js", "hive"],
                        help="Domain to train (required unless --dry-run)")
    parser.add_argument("--data", type=str, default=None,
                        help="Path to domain training JSONL")
    parser.add_argument("--warm-start", type=str, default=None,
                        help="Path to warm-start adapter dir, or 'none' for base model")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Where to save the new adapter")
    parser.add_argument("--base-url", type=str, default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just run probes and print scores, no training")

    args = parser.parse_args()

    # Validation
    if not args.dry_run:
        if not args.domain:
            parser.error("--domain is required unless --dry-run")
        if not args.data:
            parser.error("--data is required unless --dry-run")
        if not args.output_dir:
            parser.error("--output-dir is required unless --dry-run")
        if not Path(args.data).exists():
            parser.error(f"Data file not found: {args.data}")

    check_server(args.base_url)

    if args.dry_run:
        print("\n--- DRY RUN: Probing all domains (LoRA scale=1.0) ---")
        set_lora_scale(args.base_url, 1.0)
        scores = run_probes(args.base_url, PROBES)
        print_scores_solo(scores)

        # Also probe base model (scale=0)
        print("\n--- DRY RUN: Probing all domains (LoRA scale=0.0 / base) ---")
        set_lora_scale(args.base_url, 0.0)
        base_scores = run_probes(args.base_url, PROBES)
        print_scores_solo(base_scores)

        # Compare
        print("\n--- Comparison: Base vs LoRA ---")
        print_score_table(base_scores, scores)

        # Restore
        set_lora_scale(args.base_url, 1.0)
        print("  (LoRA scale restored to 1.0)")
        return

    # Full training + validation cycle
    result = train_and_validate(
        domain=args.domain,
        data_path=args.data,
        warm_start=args.warm_start,
        output_dir=args.output_dir,
        base_url=args.base_url,
    )

    if result:
        print(f"\nSUCCESS: Adapter locked in at {result}")
        print(f"Use --warm-start {result} for the next domain.")
        sys.exit(0)
    else:
        print(f"\nFAILED: Adapter was NOT locked in. Previous adapter remains active.")
        sys.exit(1)


if __name__ == "__main__":
    main()
