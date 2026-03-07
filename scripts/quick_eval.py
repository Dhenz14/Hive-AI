#!/usr/bin/env python3
"""
quick_eval.py -- Quick A/B evaluation for Hive-AI LoRA vs base model.

Runs 20 anchor prompts at LoRA scale=0 (base) and scale=1 (LoRA),
scores each response, and prints a side-by-side comparison with verdict.

Requires llama-server running at http://localhost:11435 with OpenAI-compatible API
and LoRA adapter control via POST /lora-adapters.

Usage:
    python scripts/quick_eval.py              # full A/B comparison
    python scripts/quick_eval.py --base-only  # only run base model
    python scripts/quick_eval.py --lora-only  # only run LoRA model
    python scripts/quick_eval.py --json       # structured JSON output
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:11435"
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant."
TEMPERATURE = 0.1
MAX_TOKENS = 1024
TIMEOUT = 120  # seconds per prompt


# ---------------------------------------------------------------------------
# Anchor prompts
# ---------------------------------------------------------------------------

@dataclass
class Prompt:
    id: int
    text: str
    keywords: list = field(default_factory=list)
    runnable: Optional[bool] = None  # True/False/None
    concise: bool = False            # expect short answer


PROMPTS = [
    # --- Python: easy baseline + hard (4) ---
    Prompt(1,
           "Write a Python function to find the longest common subsequence of two strings. Include a test.",
           keywords=["def", "lcs", "return"], runnable=True),
    Prompt(2,
           "Write a Python decorator that retries a function up to 3 times on exception with exponential backoff.",
           keywords=["def", "decorator", "retry", "sleep", "except"], runnable=True),
    Prompt(3,
           "Implement a Python LRU cache from scratch (no functools) that is thread-safe, supports max_size, and has O(1) get/put. Include unit tests.",
           keywords=["OrderedDict", "Lock", "class", "get", "put", "max_size", "test"], runnable=True),
    Prompt(4,
           "Write a Python coroutine-based pipeline: one producer yields items, two consumers process them concurrently via asyncio.Queue, with graceful shutdown on SIGINT.",
           keywords=["async", "Queue", "asyncio", "signal", "await", "producer", "consumer"], runnable=False),

    # --- Rust: hard (3) ---
    Prompt(5,
           "Write a Rust function that takes a &str of CSV data and returns a Vec<HashMap<String, String>> where keys are header names. Handle quoted fields with commas inside them.",
           keywords=["fn", "HashMap", "Vec", "String", "split", "quote"]),
    Prompt(6,
           "Implement a generic Stack<T> in Rust with push, pop, and peek methods.",
           keywords=["struct", "impl", "Option", "fn"]),
    Prompt(7,
           "Write a Rust async function using tokio that downloads 5 URLs concurrently with a semaphore limit of 2, collects results into a Vec<Result<String, Error>>, and handles timeouts.",
           keywords=["async", "tokio", "Semaphore", "Result", "timeout", "join"]),

    # --- Go: hard (3) ---
    Prompt(8,
           "Implement a worker pool in Go: a Pool struct that accepts jobs via a channel, processes them with N goroutines, supports graceful shutdown via context cancellation, and returns results.",
           keywords=["func", "chan", "context", "sync.WaitGroup", "goroutine", "Cancel"]),
    Prompt(9,
           "Write a Go HTTP middleware that implements rate limiting with a token bucket algorithm. It should be configurable per-route.",
           keywords=["func", "http.Handler", "Mutex", "token", "bucket", "middleware"]),
    Prompt(10,
           "Write a Go function that traverses a directory tree concurrently using goroutines, finds all files matching a glob pattern, and returns results via a channel. Handle errors and context cancellation.",
           keywords=["func", "filepath", "chan", "goroutine", "context", "Walk"]),

    # --- JavaScript/TypeScript: medium + hard (3) ---
    Prompt(11,
           "Write a TypeScript generic function that deeply merges two objects, with proper types. Handle arrays, nested objects, and null values.",
           keywords=["function", "Partial", "keyof", "Record", "Array"]),
    Prompt(12,
           "Implement a JavaScript Promise.allSettled polyfill from scratch, then write a retry wrapper that retries rejected promises up to N times with backoff.",
           keywords=["Promise", "allSettled", "retry", "reject", "resolve", "setTimeout"]),
    Prompt(13,
           "Write a React custom hook useDebounce<T> in TypeScript that debounces a value with cleanup on unmount, and a useDebouncedCallback that debounces a function. Include types.",
           keywords=["useEffect", "useRef", "useState", "cleanup", "generic", "timeout"]),

    # --- Hive blockchain: hard (3) ---
    Prompt(14,
           "Write a Python script using beem that: 1) creates a custom_json operation for a Hive Engine token transfer, 2) broadcasts it with proper authority (posting key), 3) then verifies the transaction was included in a block by polling.",
           keywords=["beem", "custom_json", "Hive", "broadcast", "posting", "ssc-mainnet-hive"]),
    Prompt(15,
           "Explain the Hive blockchain key hierarchy (owner, active, posting, memo). Write a Python function using beem that generates a new account's keys from a master password and validates them.",
           keywords=["owner", "active", "posting", "memo", "PasswordKey", "beem", "generate"]),
    Prompt(16,
           "Write a Python function using beem that calculates the current APR for Hive Power delegation, factoring in the reward pool, recent claims, and vesting fund. Explain each variable.",
           keywords=["beem", "reward_fund", "vesting", "APR", "delegation", "median_price"]),

    # --- System design + architecture: hard (3) ---
    Prompt(17,
           "Implement a circuit breaker pattern in Python with three states (closed, open, half-open), configurable failure threshold, timeout duration, and success threshold to close. Include usage example.",
           keywords=["class", "CircuitBreaker", "open", "closed", "half_open", "threshold", "timeout"]),
    Prompt(18,
           "Design and implement a simple pub/sub system in Python supporting: topic-based subscriptions, wildcard matching (e.g. 'user.*'), async message delivery, and subscriber backpressure.",
           keywords=["class", "subscribe", "publish", "wildcard", "async", "queue", "topic"]),
    Prompt(19,
           "Implement a connection pool in Python for database connections: min/max connections, health checks, acquire/release with context manager, and connection timeout. Thread-safe.",
           keywords=["class", "Pool", "acquire", "release", "Lock", "Queue", "context"]),

    # --- Debugging: give broken code (2) ---
    Prompt(20,
           """Fix this Python code that's supposed to find the k-th largest element using a min-heap but gives wrong results:
```python
import heapq
def kth_largest(nums, k):
    heap = []
    for n in nums:
        heapq.heappush(heap, -n)
        if len(heap) > k:
            heapq.heappop(heap)
    return -heap[0]
print(kth_largest([3,2,1,5,6,4], 2))  # should print 5, prints 1
```
Explain the bug and provide the corrected version.""",
           keywords=["heapq", "min", "max", "negate", "pop", "fix"], runnable=True),
]


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------

def set_lora_scale(scale):
    """Set the LoRA adapter scale via the llama-server API."""
    resp = requests.post(
        f"{BASE_URL}/lora-adapters",
        json=[{"id": 0, "scale": scale}],
        timeout=10,
    )
    resp.raise_for_status()
    time.sleep(0.3)


def chat_completion(prompt_text):
    """Send a chat completion request and return the assistant message."""
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
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
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def extract_python_code(text):
    """Extract fenced Python code blocks from text."""
    return re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)


def score_has_code(text):
    """1.0 if fenced code blocks present, 0.5 if inline code keywords, 0.0 otherwise."""
    if re.search(r"```", text):
        return 1.0
    if re.search(r"`[^`]+`", text):
        return 0.5
    return 0.0


def score_keywords(text, keywords):
    """Fraction of expected keywords found (case-sensitive)."""
    if not keywords:
        return 1.0
    found = sum(1 for kw in keywords if kw in text)
    return found / len(keywords)


def try_run_python(text):
    """Try to execute extracted Python code. Returns 1.0 if success, 0.0 if fail."""
    blocks = extract_python_code(text)
    if not blocks:
        return 0.0
    combined = "\n\n".join(blocks)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(combined)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, timeout=15, text=True,
        )
        return 1.0 if result.returncode == 0 else 0.0
    except (subprocess.TimeoutExpired, Exception):
        return 0.0
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def score_length(text, concise):
    """Score based on response length."""
    word_count = len(text.split())
    if concise:
        if word_count < 100:
            return 1.0
        elif word_count <= 200:
            return 0.5
        else:
            return 0.0
    return min(word_count / 100.0, 1.0)


@dataclass
class Score:
    has_code: float
    keywords: float
    runs: object   # float or None
    length: float
    overall: float


def score_response(text, prompt):
    """Score a single response against its prompt criteria."""
    hc = score_has_code(text)
    kw = score_keywords(text, prompt.keywords)
    ln = score_length(text, prompt.concise)

    runs = None
    if prompt.runnable is True:
        runs = try_run_python(text)

    # Average active dimensions
    dims = [hc, kw, ln]
    if runs is not None:
        dims.append(runs)
    overall = sum(dims) / len(dims) if dims else 0.0

    return Score(has_code=hc, keywords=kw, runs=runs, length=ln, overall=overall)


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_eval(scale, label):
    """Run all prompts at a given LoRA scale, return list of result dicts."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Running evaluation: {label} (scale={scale})")
    print(sep)

    set_lora_scale(scale)
    results = []

    for p in PROMPTS:
        tag = f"[{label}] Prompt {p.id:2d}"
        try:
            t0 = time.time()
            response = chat_completion(p.text)
            elapsed = time.time() - t0
            sc = score_response(response, p)
            print(f"  {tag}: overall={sc.overall:.2f}  ({elapsed:.1f}s)")
            results.append({
                "id": p.id,
                "prompt": p.text[:60] + "...",
                "score": sc,
                "response_len": len(response.split()),
                "elapsed": round(elapsed, 1),
                "error": None,
            })
        except Exception as e:
            print(f"  {tag}: ERROR - {e}")
            results.append({
                "id": p.id,
                "prompt": p.text[:60] + "...",
                "score": Score(0, 0, None, 0, 0),
                "response_len": 0,
                "elapsed": 0,
                "error": str(e),
            })

    return results


def print_comparison(base_results, lora_results):
    """Print side-by-side table and return verdict string."""
    sep = "=" * 80
    print(f"\n{sep}")
    print("  COMPARISON: Base (scale=0) vs LoRA (scale=1)")
    print(sep)
    header = f"{'#':>3}  {'Prompt':<50}  {'Base':>6}  {'LoRA':>6}  {'Delta':>7}"
    print(header)
    print("-" * len(header))

    degraded_count = 0

    for b, l in zip(base_results, lora_results):
        bs = b["score"].overall
        ls = l["score"].overall
        delta = ls - bs
        if delta < -0.15:
            degraded_count += 1
        marker = ""
        if delta > 0.05:
            marker = " +"
        elif delta < -0.15:
            marker = " !!"
        print(f"{b['id']:3d}  {b['prompt']:<50}  {bs:6.2f}  {ls:6.2f}  {delta:+7.2f}{marker}")

    avg_base = sum(r["score"].overall for r in base_results) / len(base_results)
    avg_lora = sum(r["score"].overall for r in lora_results) / len(lora_results)
    avg_delta = avg_lora - avg_base

    print("-" * len(header))
    print(f"{'AVG':>3}  {'':<50}  {avg_base:6.2f}  {avg_lora:6.2f}  {avg_delta:+7.2f}")
    print()

    # Verdict
    if degraded_count >= 3:
        verdict = "DEGRADED"
        desc = f"{degraded_count} prompts dropped >0.15 -- LoRA is hurting quality"
    elif degraded_count >= 1:
        verdict = "PARTIAL DEGRADATION"
        desc = f"{degraded_count} prompt(s) dropped >0.15 -- some regressions"
    elif avg_delta >= 0.05:
        verdict = "IMPROVEMENT"
        desc = f"Average +{avg_delta:.3f} -- LoRA is helping"
    else:
        verdict = "NEUTRAL"
        desc = f"Average delta {avg_delta:+.3f} -- no significant change"

    print(f"  VERDICT: {verdict}")
    print(f"  {desc}")
    print()

    return verdict


def to_json_output(base_results, lora_results):
    """Build a JSON-serializable output dict."""

    def serialize_results(results):
        out = []
        for r in results:
            s = r["score"]
            out.append({
                "id": r["id"],
                "prompt": r["prompt"],
                "has_code": s.has_code,
                "keywords": s.keywords,
                "runs": s.runs,
                "length": s.length,
                "overall": s.overall,
                "response_len": r["response_len"],
                "elapsed": r["elapsed"],
                "error": r["error"],
            })
        return out

    output = {}

    if base_results is not None:
        output["base"] = serialize_results(base_results)
        output["base_avg"] = sum(r["score"].overall for r in base_results) / len(base_results)

    if lora_results is not None:
        output["lora"] = serialize_results(lora_results)
        output["lora_avg"] = sum(r["score"].overall for r in lora_results) / len(lora_results)

    if base_results is not None and lora_results is not None:
        avg_delta = output["lora_avg"] - output["base_avg"]
        degraded = sum(
            1 for b, l in zip(base_results, lora_results)
            if l["score"].overall - b["score"].overall < -0.15
        )
        if degraded >= 3:
            output["verdict"] = "DEGRADED"
        elif degraded >= 1:
            output["verdict"] = "PARTIAL DEGRADATION"
        elif avg_delta >= 0.05:
            output["verdict"] = "IMPROVEMENT"
        else:
            output["verdict"] = "NEUTRAL"

    return output


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Quick A/B eval for Hive-AI LoRA vs base model (20 anchor prompts)")
    parser.add_argument("--base-only", action="store_true", help="Only run base model (scale=0)")
    parser.add_argument("--lora-only", action="store_true", help="Only run LoRA model (scale=1)")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()

    if args.base_only and args.lora_only:
        print("ERROR: --base-only and --lora-only are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    # Connectivity check
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
    except requests.ConnectionError:
        print(f"ERROR: Cannot reach llama-server at {BASE_URL}. Is it running?", file=sys.stderr)
        sys.exit(1)

    base_results = None
    lora_results = None

    try:
        if not args.lora_only:
            base_results = run_eval(0.0, "BASE")

        if not args.base_only:
            lora_results = run_eval(1.0, "LORA")

        # Print results
        if args.json:
            print(json.dumps(to_json_output(base_results, lora_results), indent=2))
        elif base_results is not None and lora_results is not None:
            print_comparison(base_results, lora_results)
        else:
            # Single-mode summary
            results = base_results if base_results is not None else lora_results
            label = "BASE" if base_results is not None else "LORA"
            avg = sum(r["score"].overall for r in results) / len(results)
            print(f"\n  {label} average score: {avg:.3f}")
            print()

    finally:
        # Always restore LoRA scale to 1.0
        try:
            set_lora_scale(1.0)
            print("  (LoRA scale restored to 1.0)")
        except Exception:
            print("  WARNING: Failed to restore LoRA scale to 1.0", file=sys.stderr)


if __name__ == "__main__":
    main()
