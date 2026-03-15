#!/usr/bin/env python3
"""
v1.1 Brain Smoke Test: gpt-oss-20b vs v5-think
Tests assertion hygiene, executable correctness, and Hive sanity.

Usage:
    python scripts/brain_smoke_test.py --model-path /path/to/model.gguf --port 11435

The script:
1. Sends coding prompts directly to llama-server (bypasses Flask/RAG)
2. Extracts code blocks from responses
3. Executes them and classifies failures
4. Reports assertion hygiene vs generation quality metrics
"""
import argparse
import json
import re
import subprocess
import sys
import time
import requests
import ast

# --- Test prompts: designed to expose assertion-hygiene failures ---
PROMPTS = [
    {
        "id": "merge_sorted",
        "category": "algorithm",
        "prompt": "Write a Python function called merge_sorted that takes two sorted lists and returns a single sorted list using the two-pointer technique. Do not use built-in sort. Include at least 5 test assertions covering: empty lists, single elements, duplicates, different lengths, and already-merged input.",
    },
    {
        "id": "lru_cache",
        "category": "data_structure",
        "prompt": "Write a Python class LRUCache with get(key) and put(key, value) methods. Use collections.OrderedDict. It should have a max_size parameter. Include assertions testing: capacity eviction, get updates recency, overwrite existing key, get missing key returns -1, and empty cache.",
    },
    {
        "id": "graph_paths",
        "category": "algorithm",
        "prompt": "Write a Python function find_all_paths(graph, start, end) that returns all paths between two nodes in a graph represented as an adjacency dict. Use DFS. Handle cycles. Include assertions for: simple path, multiple paths, no path exists, and self-loop.",
    },
    {
        "id": "retry_decorator",
        "category": "pattern",
        "prompt": "Write a Python decorator called retry that takes max_retries and base_delay parameters. It should retry the decorated function with exponential backoff when it raises an exception. Include assertions showing: successful retry after transient failure, max retries exceeded, and immediate success with zero retries.",
    },
    {
        "id": "bracket_validator",
        "category": "algorithm",
        "prompt": "Write a Python function validate_brackets(s) that returns True if the string has balanced brackets (), [], {}. Use a stack. Include assertions for: empty string, single type, mixed nested, unbalanced open, unbalanced close, and interleaved brackets.",
    },
    {
        "id": "deep_merge",
        "category": "utility",
        "prompt": "Write a Python function deep_merge(a, b) that recursively merges two nested dicts. When both are dicts merge recursively, when both are lists concatenate, otherwise b wins. Include assertions for: flat merge, nested merge, list concat, type conflict, and empty dicts.",
    },
    {
        "id": "binary_search",
        "category": "algorithm",
        "prompt": "Write a Python function binary_search(arr, target) that returns the index of target in a sorted list, or -1 if not found. Include assertions for: found at start, found at end, found in middle, not found, empty list, single element found, single element not found.",
    },
    {
        "id": "rate_limiter",
        "category": "pattern",
        "prompt": "Write a Python class TokenBucket with capacity, refill_rate, and a consume(n) method that returns True if tokens available, False otherwise. Include time-based refill. Include assertions for: consume within limit, exceed limit, and refill after waiting.",
    },
    {
        "id": "trie",
        "category": "data_structure",
        "prompt": "Write a Python class Trie with insert(word), search(word), and starts_with(prefix) methods. Include assertions for: insert and find, prefix match, word not found, empty trie, and overlapping prefixes.",
    },
    {
        "id": "matrix_rotate",
        "category": "algorithm",
        "prompt": "Write a Python function rotate_90(matrix) that rotates an NxN matrix 90 degrees clockwise in-place. Include assertions for: 1x1, 2x2, 3x3, and 4x4 matrices with expected outputs.",
    },
]

# Hive-specific sanity checks
HIVE_PROMPTS = [
    {
        "id": "hive_template",
        "prompt": "Write a HiveAI HAF template YAML for a simple REST API indexer that fetches JSON from an endpoint and extracts text fields. Include the required fields: name, version, source, parser, and output sections.",
    },
    {
        "id": "hive_dbc",
        "prompt": "Explain what a DBC (Domain Boundary Contract) is in the HiveAI system and write a minimal Python example showing how a DBC validator checks a response before it enters the knowledge base.",
    },
]


def query_llm(prompt: str, port: int, temperature: float = 0.1) -> str:
    """Send a prompt to llama-server and return the response text."""
    messages = [
        {"role": "system", "content": "You are a coding assistant. Write clean, correct, executable Python code. Always include the test assertions directly in the code block so the entire block can be run as a single script."},
        {"role": "user", "content": prompt},
    ]
    try:
        r = requests.post(
            f"http://localhost:{port}/v1/chat/completions",
            json={"messages": messages, "temperature": temperature, "max_tokens": 2048},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def extract_python_code(text: str) -> str:
    """Extract the first Python code block from markdown response."""
    # Try closed fences first
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try unclosed fence
    m = re.search(r"```python\s*\n(.+)", text, re.DOTALL)
    if m:
        code = m.group(1).strip()
        # Trim trailing prose
        lines = code.split('\n')
        while lines and re.match(r'^[A-Z].*[.!?:]$', lines[-1].strip()):
            lines.pop()
        return '\n'.join(lines)
    return ""


def execute_code(code: str, timeout: int = 30) -> dict:
    """Execute Python code and classify the result."""
    if not code:
        return {"status": "no_code", "error": "No code block extracted"}
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return {"status": "pass", "stdout": result.stdout}
        stderr = result.stderr
        # Classify the failure
        if "AssertionError" in stderr or "AssertionError" in stderr.replace("Assertion", "Assertion"):
            # Check: is the assertion wrong, or the code wrong?
            return {"status": "assertion_fail", "error": stderr}
        elif "SyntaxError" in stderr:
            return {"status": "syntax_error", "error": stderr}
        elif "NameError" in stderr or "ImportError" in stderr:
            return {"status": "import_error", "error": stderr}
        elif "TypeError" in stderr or "AttributeError" in stderr:
            return {"status": "type_error", "error": stderr}
        else:
            return {"status": "runtime_error", "error": stderr}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Execution timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_smoke_test(port: int, model_name: str):
    """Run all prompts and report results."""
    results = []

    print(f"\n{'='*70}")
    print(f"  BRAIN SMOKE TEST: {model_name}")
    print(f"  Port: {port}")
    print(f"  Prompts: {len(PROMPTS)} coding + {len(HIVE_PROMPTS)} Hive sanity")
    print(f"{'='*70}\n")

    # Coding prompts
    for p in PROMPTS:
        sys.stdout.write(f"  {p['id']:<20} ... ")
        sys.stdout.flush()

        t0 = time.time()
        response = query_llm(p["prompt"], port)
        gen_time = time.time() - t0

        code = extract_python_code(response)
        exec_result = execute_code(code)

        result = {
            "id": p["id"],
            "category": p["category"],
            "status": exec_result["status"],
            "gen_time_s": round(gen_time, 1),
            "response_len": len(response),
            "code_len": len(code),
            "error": exec_result.get("error", ""),
        }
        results.append(result)

        status_icon = {
            "pass": "PASS",
            "assertion_fail": "ASSERT_FAIL",
            "no_code": "NO_CODE",
            "syntax_error": "SYNTAX",
            "timeout": "TIMEOUT",
        }.get(exec_result["status"], "FAIL")

        print(f"{status_icon:<14} {gen_time:.1f}s  {len(code)} chars")

    # Hive sanity prompts (no execution, just check response quality)
    print(f"\n  {'--- Hive Sanity ---':<20}")
    for p in HIVE_PROMPTS:
        sys.stdout.write(f"  {p['id']:<20} ... ")
        sys.stdout.flush()

        t0 = time.time()
        response = query_llm(p["prompt"], port)
        gen_time = time.time() - t0

        has_code = bool(re.search(r"```", response))
        has_substance = len(response) > 200

        result = {
            "id": p["id"],
            "category": "hive_sanity",
            "status": "pass" if has_substance else "weak",
            "gen_time_s": round(gen_time, 1),
            "response_len": len(response),
            "code_len": 0,
            "has_code": has_code,
        }
        results.append(result)
        print(f"{'OK' if has_substance else 'WEAK':<14} {gen_time:.1f}s  {len(response)} chars  code={'Y' if has_code else 'N'}")

    # Summary
    coding_results = [r for r in results if r["category"] != "hive_sanity"]
    passes = sum(1 for r in coding_results if r["status"] == "pass")
    assertion_fails = sum(1 for r in coding_results if r["status"] == "assertion_fail")
    other_fails = sum(1 for r in coding_results if r["status"] not in ("pass", "assertion_fail"))
    no_code = sum(1 for r in coding_results if r["status"] == "no_code")
    avg_gen = sum(r["gen_time_s"] for r in coding_results) / max(len(coding_results), 1)

    print(f"\n{'='*70}")
    print(f"  RESULTS: {model_name}")
    print(f"{'='*70}")
    print(f"  Executable pass:       {passes}/{len(coding_results)}")
    print(f"  Assertion hygiene fail: {assertion_fails}/{len(coding_results)}")
    print(f"  Other failures:         {other_fails}/{len(coding_results)}")
    print(f"  No code extracted:      {no_code}/{len(coding_results)}")
    print(f"  Avg generation time:    {avg_gen:.1f}s")
    print(f"  Hive sanity:            {sum(1 for r in results if r.get('category')=='hive_sanity' and r['status']=='pass')}/{len(HIVE_PROMPTS)}")
    print(f"{'='*70}\n")

    # Write detailed results
    out_path = f"/tmp/brain_smoke_{model_name.replace(' ', '_').replace('/', '_')}.json"
    with open(out_path, "w") as f:
        json.dump({"model": model_name, "results": results, "summary": {
            "pass": passes, "assertion_fail": assertion_fails,
            "other_fail": other_fails, "no_code": no_code,
            "avg_gen_s": avg_gen, "total": len(coding_results),
        }}, f, indent=2)
    print(f"  Detailed results: {out_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brain smoke test")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--model-name", type=str, default="unknown")
    args = parser.parse_args()

    # Verify server is up
    try:
        r = requests.get(f"http://localhost:{args.port}/health", timeout=5)
        print(f"Server on port {args.port}: OK")
    except:
        print(f"ERROR: No server on port {args.port}")
        sys.exit(1)

    run_smoke_test(args.port, args.model_name)
