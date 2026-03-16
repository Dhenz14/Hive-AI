"""Executable Evaluation: Code generation + sandbox verification.

Instead of keyword-matching probes, this eval:
1. Sends coding prompts to llama-server
2. Extracts code blocks from the response
3. Runs them through the sandbox (compile/execute/test)
4. Scores: pass_rate = passed_blocks / total_blocks

This is the v1 executable eval — keyword probes are demoted to smoke tests,
this becomes the primary eval for code quality.

Usage:
    # Run all eval prompts against llama-server
    python scripts/executable_eval.py --server-url http://localhost:11435

    # Run specific language only
    python scripts/executable_eval.py --language python

    # Run specific prompt by index
    python scripts/executable_eval.py --prompt 0

    # Save results to JSON
    python scripts/executable_eval.py --output results/exec_eval.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hiveai.sandbox import verify_response_code, extract_code_blocks

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are HiveAI, an expert coding assistant. "
    "Write clean, correct, runnable code. Include all necessary imports. "
    "Use code fences with the language tag (```python, ```cpp, etc.)."
)
TEMPERATURE = 0.0
MAX_TOKENS = 2048
TIMEOUT = 120

# ---------------------------------------------------------------------------
# Eval prompts — each is a coding task with expected language
# ---------------------------------------------------------------------------
EVAL_PROMPTS = [
    # --- Python (0-9) ---
    {
        "id": "py-fibonacci",
        "language": "python",
        "prompt": "Write a Python function `fibonacci(n)` that returns the nth Fibonacci number using iteration. Include a test: assert fibonacci(10) == 55",
    },
    {
        "id": "py-binary-search",
        "language": "python",
        "prompt": "Write a Python function `binary_search(arr, target)` that returns the index of target in a sorted array, or -1 if not found. Include test assertions.",
    },
    {
        "id": "py-flatten",
        "language": "python",
        "prompt": "Write a Python function `flatten(nested)` that recursively flattens a nested list. Example: flatten([1, [2, [3, 4]], 5]) should return [1, 2, 3, 4, 5]. Include test assertions.",
    },
    {
        "id": "py-lru-cache",
        "language": "python",
        "prompt": "Write a Python class `LRUCache` with `get(key)` and `put(key, value)` methods and a capacity limit. Include test assertions demonstrating eviction.",
    },
    {
        "id": "py-merge-sort",
        "language": "python",
        "prompt": "Write a Python function `merge_sort(arr)` that sorts a list using merge sort. Include assertions testing edge cases (empty, single element, already sorted, reverse sorted).",
    },
    {
        "id": "py-decorator",
        "language": "python",
        "prompt": "Write a Python decorator `@retry(max_attempts=3, delay=0.01)` that retries a function on exception. Include a test that shows it retries and eventually succeeds.",
    },
    {
        "id": "py-context-manager",
        "language": "python",
        "prompt": "Write a Python context manager class `Timer` that measures execution time of a code block and stores it in a `.elapsed` attribute. Include a test using `with Timer() as t:`.",
    },
    {
        "id": "py-dataclass",
        "language": "python",
        "prompt": "Write a Python dataclass `Point` with x, y coordinates, a `distance_to(other)` method, and a `from_tuple(t)` classmethod. Include test assertions.",
    },
    {
        "id": "py-generator",
        "language": "python",
        "prompt": "Write a Python generator function `prime_sieve(limit)` that yields all prime numbers up to `limit` using the Sieve of Eratosthenes. Include assertions: list(prime_sieve(20)) == [2, 3, 5, 7, 11, 13, 17, 19].",
    },
    {
        "id": "py-async",
        "language": "python",
        "prompt": "Write Python async functions using asyncio: an async `fetch(url, delay)` that simulates a delay and returns a string, and a `gather_all(urls)` that runs multiple fetches concurrently. Include a test using asyncio.run().",
    },

    # --- C++ (10-14) ---
    {
        "id": "cpp-vector-sort",
        "language": "cpp",
        "prompt": "Write a C++ program that creates a vector of integers, sorts it, and uses binary_search to check membership. Use #include <iostream>, <vector>, <algorithm>. Print PASS if all checks succeed.",
    },
    {
        "id": "cpp-smart-ptr",
        "language": "cpp",
        "prompt": "Write a C++ program demonstrating unique_ptr: create a class with a constructor/destructor that prints messages, create unique_ptr instances, transfer ownership with std::move. Print PASS at the end.",
    },
    {
        "id": "cpp-template",
        "language": "cpp",
        "prompt": "Write a C++ template function `max_of_three(a, b, c)` that returns the maximum. Test it with int and double types. Print PASS if all assertions hold.",
    },
    {
        "id": "cpp-string-ops",
        "language": "cpp",
        "prompt": "Write a C++ program that: splits a comma-separated string into a vector<string>, joins them back with ' | ', and verifies the round-trip. Print PASS if correct.",
    },
    {
        "id": "cpp-map-count",
        "language": "cpp",
        "prompt": "Write a C++ program that counts word frequencies in a string using unordered_map, finds the most common word, and prints PASS if the result is correct. Use: 'the cat sat on the mat the cat'.",
    },

    # --- TypeScript/JavaScript (15-19) ---
    {
        "id": "js-promise-all",
        "language": "javascript",
        "prompt": "Write a JavaScript function `fetchAll(urls)` that returns a Promise resolving to an array of results. Simulate async work with setTimeout wrapped in Promise. Include a test with console.log('PASS') on success.",
    },
    {
        "id": "js-debounce",
        "language": "javascript",
        "prompt": "Write a JavaScript `debounce(fn, delay)` function. Include a test that calls the debounced function multiple times rapidly and verifies it only executes once. Print 'PASS'.",
    },
    {
        "id": "js-deep-clone",
        "language": "javascript",
        "prompt": "Write a JavaScript function `deepClone(obj)` that handles objects, arrays, dates, and nested structures. Include test assertions comparing original and clone. Print 'PASS' if all pass.",
    },
    {
        "id": "js-event-emitter",
        "language": "javascript",
        "prompt": "Write a JavaScript class `EventEmitter` with `on(event, cb)`, `off(event, cb)`, and `emit(event, ...args)` methods. Include tests that verify listener registration, removal, and emission. Print 'PASS'.",
    },
    {
        "id": "js-array-methods",
        "language": "javascript",
        "prompt": "Write JavaScript functions `myMap(arr, fn)`, `myFilter(arr, fn)`, and `myReduce(arr, fn, init)` that replicate Array.prototype methods without using them. Include test assertions and print 'PASS'.",
    },
]


def query_server(prompt: str, server_url: str) -> str:
    """Send a coding prompt to llama-server and return the response text."""
    payload = {
        "model": "hiveai",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{server_url}/v1/chat/completions",
            json=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def run_eval(
    server_url: str,
    language: str = "",
    prompt_index: int = -1,
    verbose: bool = False,
) -> dict:
    """Run executable eval and return structured results."""
    prompts = EVAL_PROMPTS
    if language:
        prompts = [p for p in prompts if p["language"] == language]
    if prompt_index >= 0:
        prompts = [prompts[prompt_index]] if prompt_index < len(prompts) else []

    results = []
    total_passed = 0
    total_blocks = 0
    total_prompts = len(prompts)

    print(f"\n{'='*60}")
    print(f"Executable Eval — {total_prompts} prompts")
    print(f"Server: {server_url}")
    print(f"{'='*60}\n")

    for i, p in enumerate(prompts):
        pid = p["id"]
        lang = p["language"]
        print(f"[{i+1}/{total_prompts}] {pid} ({lang})...", end=" ", flush=True)

        t_start = time.time()
        response = query_server(p["prompt"], server_url)
        t_gen = time.time() - t_start

        if response.startswith("ERROR:"):
            print(f"FAIL (server error: {response[:80]})")
            results.append({
                "id": pid, "language": lang, "status": "error",
                "error": response, "gen_time_s": round(t_gen, 1),
            })
            continue

        # Verify through sandbox
        t_start = time.time()
        verification = verify_response_code(response, timeout=30)
        t_verify = time.time() - t_start

        passed = verification.get("passed", 0)
        failed = verification.get("failed", 0)
        blocks = verification.get("total_blocks", 0)
        total_passed += passed
        total_blocks += blocks

        if blocks == 0:
            status = "no_code"
            print(f"SKIP (no code blocks found)")
        elif failed == 0 and passed > 0:
            status = "pass"
            print(f"PASS ({passed} blocks, {t_gen:.1f}s gen + {t_verify:.1f}s verify)")
        else:
            status = "fail"
            # Show first error
            first_err = ""
            for r in verification.get("results", []):
                if not r.get("success"):
                    first_err = f" — {r.get('error_type', '')}: {r.get('stderr', '')[:80]}"
                    break
            print(f"FAIL ({passed}/{blocks} pass{first_err})")

        result_entry = {
            "id": pid,
            "language": lang,
            "status": status,
            "blocks": blocks,
            "passed": passed,
            "failed": failed,
            "gen_time_s": round(t_gen, 1),
            "verify_time_s": round(t_verify, 1),
        }

        if verbose and status == "fail":
            result_entry["response_preview"] = response[:500]
            result_entry["verification_details"] = verification.get("results", [])

        results.append(result_entry)

    # Summary
    pass_rate = total_passed / max(total_blocks, 1)
    prompt_pass = sum(1 for r in results if r["status"] == "pass")

    print(f"\n{'='*60}")
    print(f"RESULTS: {prompt_pass}/{total_prompts} prompts fully passing")
    print(f"Blocks:  {total_passed}/{total_blocks} ({pass_rate:.1%}) pass")

    # Per-language breakdown
    by_lang = {}
    for r in results:
        lang = r["language"]
        if lang not in by_lang:
            by_lang[lang] = {"total": 0, "pass": 0, "blocks": 0, "blocks_pass": 0}
        by_lang[lang]["total"] += 1
        if r["status"] == "pass":
            by_lang[lang]["pass"] += 1
        by_lang[lang]["blocks"] += r.get("blocks", 0)
        by_lang[lang]["blocks_pass"] += r.get("passed", 0)

    print(f"\nPer-language:")
    for lang, stats in sorted(by_lang.items()):
        bp = stats["blocks_pass"] / max(stats["blocks"], 1)
        print(f"  {lang:12s}: {stats['pass']}/{stats['total']} prompts, "
              f"{stats['blocks_pass']}/{stats['blocks']} blocks ({bp:.0%})")

    print(f"{'='*60}\n")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "server_url": server_url,
        "total_prompts": total_prompts,
        "prompts_passing": prompt_pass,
        "total_blocks": total_blocks,
        "blocks_passing": total_passed,
        "pass_rate": round(pass_rate, 4),
        "by_language": by_lang,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Executable Eval — sandbox-verified code generation")
    parser.add_argument("--server-url", default="http://localhost:11435",
                        help="llama-server URL (default: http://localhost:11435)")
    parser.add_argument("--language", default="", choices=["", "python", "cpp", "javascript"],
                        help="Filter to specific language")
    parser.add_argument("--prompt", type=int, default=-1,
                        help="Run single prompt by index")
    parser.add_argument("--output", default="",
                        help="Save results to JSON file")
    parser.add_argument("--verbose", action="store_true",
                        help="Include response previews and error details in output")
    args = parser.parse_args()

    results = run_eval(
        server_url=args.server_url,
        language=args.language,
        prompt_index=args.prompt,
        verbose=args.verbose,
    )

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
