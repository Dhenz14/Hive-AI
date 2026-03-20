#!/usr/bin/env python3
"""
Model Shootout — 5 hard coding questions, head-to-head.

Single-GPU mode: starts each model sequentially on the same port, tests, swaps.

Usage:
    python3 scripts/model_shootout.py
    python3 scripts/model_shootout.py --models v5-think claude-distill
    python3 scripts/model_shootout.py --models v5-think   # single model
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

SERVER_BIN = "/opt/hiveai/llama-cpp-build/build/bin/llama-server"
PORT = 11435
URL = f"http://localhost:{PORT}"

MODELS = {
    "v5-think": "/opt/hiveai/project/models/deploy/current_base.gguf",
    "claude-distill": "/opt/hiveai/project/models/deploy/qwen3-14b-claude-distill-q6k.gguf",
}

# 5 hard, practical coding questions — diverse domains
QUESTIONS = [
    {
        "id": "q1-async-pool",
        "language": "python",
        "prompt": (
            "Write a Python async connection pool that supports max connections, "
            "waiters queue, health checks, and graceful shutdown. "
            "Include type hints and error handling."
        ),
    },
    {
        "id": "q2-rust-btree",
        "language": "rust",
        "prompt": (
            "Implement a B-tree in Rust with insert, search, and split operations. "
            "Use generics with Ord bound. Include tests."
        ),
    },
    {
        "id": "q3-go-raft",
        "language": "go",
        "prompt": (
            "Write a simplified Raft leader election in Go. Include heartbeat, "
            "election timeout, vote request/response, and state transitions "
            "between follower/candidate/leader."
        ),
    },
    {
        "id": "q4-cpp-lockfree",
        "language": "cpp",
        "prompt": (
            "Implement a lock-free MPMC queue in C++ using std::atomic. "
            "Support push, pop, and empty check. Explain the memory ordering choices."
        ),
    },
    {
        "id": "q5-ts-eventsource",
        "language": "typescript",
        "prompt": (
            "Design and implement the core of an event sourcing system in TypeScript. "
            "Include: 1) Event store with append-only persistence, "
            "2) Aggregate root base class with apply/replay, "
            "3) Snapshot support every N events, "
            "4) Concrete BankAccount aggregate with deposit/withdraw/transfer."
        ),
    },
]

SYSTEM_PROMPT = (
    "You are an expert programmer. Write clean, correct, production-quality code. "
    "Be concise but complete."
)


def stop_server():
    """Kill any running llama-server."""
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    time.sleep(3)


def start_server(model_path):
    """Start llama-server and wait for it to be healthy."""
    stop_server()

    cmd = [
        SERVER_BIN,
        "-m", model_path,
        "--port", str(PORT),
        "--ctx-size", "4096",
        "--flash-attn", "auto",
        "-t", "12",
        "--n-gpu-layers", "99",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"  Server PID {proc.pid}, loading model...")

    # Wait for healthy
    for _ in range(60):
        try:
            r = requests.get(f"{URL}/health", timeout=3)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print("  Server ready!")
                return proc
        except Exception:
            pass
        time.sleep(2)

    print("  ERROR: Server failed to start after 120s")
    proc.kill()
    return None


def query_model(prompt, timeout=300):
    """Send a question and return the raw response."""
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 3500,
        "temperature": 0.1,
        "stream": False,
    }
    try:
        t0 = time.time()
        resp = requests.post(f"{URL}/v1/chat/completions", json=payload, timeout=timeout)
        elapsed = time.time() - t0
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "content": content,
            "elapsed": round(elapsed, 1),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    except requests.exceptions.Timeout:
        return {"content": "", "error": f"Timeout after {timeout}s", "elapsed": timeout}
    except Exception as e:
        return {"content": "", "error": str(e), "elapsed": 0}


def strip_think(text):
    """Remove <think>...</think> blocks for analysis."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def basic_score(content):
    """Simple quality metrics — not a judge, just signals for the human."""
    clean = strip_think(content)
    code_blocks = len(re.findall(r"```\w*\n", clean))
    code_lines = 0
    in_block = False
    for line in clean.split("\n"):
        if line.strip().startswith("```") and not in_block:
            in_block = True
        elif line.strip().startswith("```") and in_block:
            in_block = False
        elif in_block and line.strip():
            code_lines += 1

    has_error_handling = bool(re.search(r"(Error|Err|error|panic|unwrap|Result|try|catch|except)", clean))
    has_types = bool(re.search(r"(->|: \w+|<\w+>|impl |fn |struct |interface )", clean))
    has_tests = bool(re.search(r"(#\[test\]|func Test|test_|assert|describe\(|it\()", clean))

    return {
        "code_blocks": code_blocks,
        "code_lines": code_lines,
        "total_chars": len(clean),
        "has_error_handling": has_error_handling,
        "has_types": has_types,
        "has_tests": has_tests,
    }


def main():
    parser = argparse.ArgumentParser(description="Model shootout: 5 hard coding questions")
    parser.add_argument("--models", nargs="+", default=list(MODELS.keys()),
                        help="Models to test (default: all)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout per question in seconds")
    parser.add_argument("--save-responses", action="store_true", default=True,
                        help="Save full responses to file")
    args = parser.parse_args()

    # Validate models
    for m in args.models:
        if m not in MODELS:
            print(f"Unknown model: {m}. Available: {list(MODELS.keys())}")
            sys.exit(1)
        if not os.path.exists(MODELS[m]):
            print(f"Model file not found: {MODELS[m]}")
            sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = {}

    for model_name in args.models:
        model_path = MODELS[model_name]
        print(f"\n{'='*70}")
        print(f"  MODEL: {model_name}")
        print(f"  File:  {model_path}")
        print(f"  Size:  {os.path.getsize(model_path) / 1e9:.1f} GB")
        print(f"{'='*70}")

        proc = start_server(model_path)
        if not proc:
            continue

        model_results = []
        for i, q in enumerate(QUESTIONS):
            print(f"\n  [{i+1}/{len(QUESTIONS)}] {q['id']} ({q['language']})...", end=" ", flush=True)
            resp = query_model(q["prompt"], timeout=args.timeout)

            if "error" in resp:
                print(f"ERROR: {resp['error'][:60]}")
            else:
                metrics = basic_score(resp["content"])
                think_len = len(resp["content"]) - len(strip_think(resp["content"]))
                print(
                    f"{resp['elapsed']}s, {resp['completion_tokens']} tok, "
                    f"{metrics['code_lines']} code lines, "
                    f"{metrics['code_blocks']} blocks"
                    f"{' +think' if think_len > 100 else ''}"
                )

            model_results.append({
                "id": q["id"],
                "language": q["language"],
                "prompt": q["prompt"],
                "response": resp.get("content", ""),
                "elapsed": resp.get("elapsed", 0),
                "tokens": resp.get("completion_tokens", 0),
                "error": resp.get("error"),
                "metrics": basic_score(resp.get("content", "")),
            })

        all_results[model_name] = model_results
        stop_server()

    # ── Summary table ──
    print(f"\n{'='*70}")
    print("SHOOTOUT RESULTS")
    print(f"{'='*70}")

    # Header
    header = f"{'Question':<20} {'Lang':<5}"
    for m in args.models:
        header += f" | {m:>20}"
    print(header)
    print("-" * len(header))

    # Per-question
    for i, q in enumerate(QUESTIONS):
        row = f"{q['id']:<20} {q['language']:<5}"
        for m in args.models:
            r = all_results.get(m, [{}])[i] if m in all_results and i < len(all_results[m]) else {}
            if r.get("error"):
                row += f" | {'ERROR':>20}"
            else:
                met = r.get("metrics", {})
                row += f" | {r.get('elapsed',0):>5.0f}s {met.get('code_lines',0):>3}L {r.get('tokens',0):>4}t"
        print(row)

    # Totals
    print("-" * len(header))
    row = f"{'TOTAL':<20} {'':5}"
    for m in args.models:
        results = all_results.get(m, [])
        total_time = sum(r.get("elapsed", 0) for r in results)
        total_lines = sum(r.get("metrics", {}).get("code_lines", 0) for r in results)
        total_tokens = sum(r.get("tokens", 0) for r in results)
        row += f" | {total_time:>5.0f}s {total_lines:>3}L {total_tokens:>4}t"
    print(row)

    # Quality signals
    print(f"\n{'Signal':<20}", end="")
    for m in args.models:
        print(f" | {m:>20}", end="")
    print()
    for signal in ["has_error_handling", "has_types", "has_tests"]:
        row = f"{signal:<20}"
        for m in args.models:
            results = all_results.get(m, [])
            count = sum(1 for r in results if r.get("metrics", {}).get(signal, False))
            row += f" | {count:>16}/{len(QUESTIONS)}"
        print(row)

    # Save full responses
    if args.save_responses:
        out_dir = Path("/opt/hiveai/project/evidence/model-evals")
        out_dir.mkdir(parents=True, exist_ok=True)

        # JSON for machine
        out_json = out_dir / f"shootout_{ts}.json"
        with open(out_json, "w") as f:
            json.dump(all_results, f, indent=2)

        # Readable for human
        out_txt = out_dir / f"shootout_{ts}.txt"
        with open(out_txt, "w") as f:
            for i, q in enumerate(QUESTIONS):
                f.write(f"\n{'='*80}\n")
                f.write(f"Q{i+1} [{q['language']}]: {q['prompt']}\n")
                f.write(f"{'='*80}\n")
                for m in args.models:
                    results = all_results.get(m, [])
                    if i < len(results):
                        r = results[i]
                        f.write(f"\n--- {m} ({r.get('elapsed',0)}s, {r.get('tokens',0)} tok) ---\n")
                        f.write(strip_think(r.get("response", "N/A")))
                        f.write("\n")

        print(f"\nResults:  {out_json}")
        print(f"Readable: {out_txt}")
        print("\nReview the readable file to judge quality. Numbers are signals, not scores.")


if __name__ == "__main__":
    main()
