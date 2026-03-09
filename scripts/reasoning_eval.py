"""Reasoning Quality Eval: Measures thinking depth, not just keyword presence.

Tests whether the model actually REASONS through problems vs pattern-matching.
Uses problems with known correct answers that require multi-step thinking.

Scoring dimensions:
  1. Think block presence (does it show its work?)
  2. Reasoning depth (steps, backtracking, edge cases)
  3. Answer correctness (does it get the RIGHT answer?)
  4. Reasoning-answer coherence (does the reasoning lead to the answer?)

Usage:
    python scripts/reasoning_eval.py --server-url http://localhost:11435
    python scripts/reasoning_eval.py --server-url http://localhost:11435 --model-version v2-think
"""
import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Think step-by-step before answering."
# Temperature scales with difficulty: harder problems get lower temperature
# for more deterministic output, easier ones allow more variation
TEMPERATURE_BY_DIFFICULTY = {1: 0.3, 2: 0.2, 3: 0.15, 4: 0.1, 5: 0.05}
DEFAULT_TEMPERATURE = 0.1
MAX_TOKENS = 1500  # Longer — we want reasoning
TIMEOUT = 180


@dataclass
class ReasoningProbe:
    """A problem that requires genuine reasoning to solve correctly."""
    category: str
    prompt: str
    correct_answer: str  # The actual correct answer (for verification)
    answer_check: str  # Regex or substring that must appear in a correct answer
    difficulty: int  # 1-5
    reasoning_hints: list = field(default_factory=list)  # Keywords that indicate real reasoning


PROBES = [
    # --- Logic / Algorithm (require step-by-step) ---
    ReasoningProbe(
        "logic",
        "A function processes a list of integers and should return the second largest "
        "UNIQUE value. Given [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5], what does it return? "
        "Show your reasoning step by step, then write the Python function.",
        correct_answer="6",
        answer_check=r"\b6\b",
        difficulty=2,
        reasoning_hints=["unique", "sort", "deduplicate", "remove", "second"],
    ),
    ReasoningProbe(
        "logic",
        "You have a race condition: two threads both read balance=100, then each "
        "subtracts 60 and writes back. What is the final balance? What SHOULD it be? "
        "Explain the bug step-by-step and show how to fix it with a mutex.",
        correct_answer="40 (bug gives 40, should be -20 or error)",
        answer_check=r"40|race|mutex|lock",
        difficulty=3,
        reasoning_hints=["read", "write", "interleave", "critical section", "atomic",
                         "before", "after", "thread 1", "thread 2", "sequence"],
    ),
    ReasoningProbe(
        "logic",
        "A recursive function computes fibonacci(5). Trace the EXACT call tree showing "
        "every recursive call, which calls return first, and identify the redundant "
        "computations. How many total function calls are made?",
        correct_answer="15 calls",
        answer_check=r"1[45]|fifteen",
        difficulty=3,
        reasoning_hints=["fib(4)", "fib(3)", "fib(2)", "fib(1)", "fib(0)",
                         "redundant", "memoize", "cache", "tree", "returns"],
    ),

    # --- Debugging (require tracing through code) ---
    ReasoningProbe(
        "debug",
        "This Python code is supposed to flatten a nested list but has a bug:\n"
        "```python\n"
        "def flatten(lst):\n"
        "    result = []\n"
        "    for item in lst:\n"
        "        if isinstance(item, list):\n"
        "            flatten(item)\n"
        "        else:\n"
        "            result.append(item)\n"
        "    return result\n"
        "```\n"
        "What is the bug? Trace through flatten([[1, 2], [3, [4, 5]]]) step by step "
        "to show exactly where it fails, then fix it.",
        correct_answer="Recursive call result is discarded (not extended into result)",
        answer_check=r"extend|result.*flatten|return.*ignored|discard",
        difficulty=2,
        reasoning_hints=["recursive call", "return value", "discarded", "lost",
                         "extend", "result.extend", "trace", "step"],
    ),
    ReasoningProbe(
        "debug",
        "This async Python code has a subtle bug:\n"
        "```python\n"
        "async def fetch_all(urls):\n"
        "    results = []\n"
        "    for url in urls:\n"
        "        result = await fetch(url)\n"
        "        results.append(result)\n"
        "    return results\n"
        "```\n"
        "It works correctly but is slow. Why? What's the fix? Show the corrected "
        "version and explain WHY it's faster with a concrete timing example.",
        correct_answer="Sequential awaits instead of concurrent (gather/TaskGroup)",
        answer_check=r"gather|sequential|concurrent|TaskGroup|parallel",
        difficulty=2,
        reasoning_hints=["sequential", "one at a time", "waiting", "concurrent",
                         "gather", "asyncio", "parallel", "total time"],
    ),

    # --- Architecture (require trade-off analysis) ---
    ReasoningProbe(
        "architecture",
        "You need to design a rate limiter that allows 100 requests per minute per user. "
        "Compare token bucket vs sliding window approaches. Which has lower memory usage? "
        "Which is more accurate? Show the trade-off analysis and recommend one with "
        "justification. Include the data structure you'd use.",
        correct_answer="Token bucket: lower memory. Sliding window: more accurate.",
        answer_check=r"token.bucket|sliding.window|trade.?off",
        difficulty=4,
        reasoning_hints=["memory", "accuracy", "trade-off", "burst", "refill",
                         "window", "timestamp", "counter", "pros", "cons"],
    ),
    ReasoningProbe(
        "architecture",
        "Your API returns paginated results. A client requests page 5 with 20 items per "
        "page, but between their page 4 and page 5 requests, 3 new items were inserted "
        "at the beginning. What happens? What items do they miss or see duplicated? "
        "Propose a solution using cursor-based pagination.",
        correct_answer="3 items duplicated from page 4, cursor-based pagination solves this",
        answer_check=r"duplicat|cursor|offset.*shift|inconsisten",
        difficulty=3,
        reasoning_hints=["offset", "shift", "duplicate", "cursor", "id", "created_at",
                         "before", "after", "stable", "insert"],
    ),

    # --- Edge Cases (require careful enumeration) ---
    ReasoningProbe(
        "edge_cases",
        "Write a function that safely divides two numbers and handles ALL edge cases. "
        "List every edge case you can think of BEFORE writing the code. Then write the "
        "function handling each one.",
        correct_answer="Zero division, None/null, non-numeric, infinity, NaN, overflow",
        answer_check=r"zero|nan|infini|none|null|overflow|type",
        difficulty=2,
        reasoning_hints=["zero", "None", "NaN", "infinity", "string", "type",
                         "negative", "overflow", "edge case", "what if"],
    ),
    ReasoningProbe(
        "edge_cases",
        "You're implementing a cache with TTL (time-to-live). Walk through these "
        "scenarios step by step:\n"
        "1. Set key 'a' with TTL=5s at t=0\n"
        "2. Get key 'a' at t=3 — what happens?\n"
        "3. Get key 'a' at t=6 — what happens?\n"
        "4. Set key 'a' with TTL=5s at t=4, then get at t=6 — what happens?\n"
        "5. What if TTL=0? What if TTL is negative?\n"
        "Show your reasoning for each scenario.",
        correct_answer="t=3: hit, t=6: expired/miss, t=4+6: hit (renewed), TTL=0: immediate expire",
        answer_check=r"expir|miss|hit|renew|stale",
        difficulty=3,
        reasoning_hints=["t=0", "t=3", "t=6", "expired", "hit", "miss", "renew",
                         "negative", "zero", "scenario"],
    ),

    # --- Complex Multi-step (the hardest) ---
    ReasoningProbe(
        "complex",
        "Design a function that detects if a linked list has a cycle. First, explain "
        "why the naive approach (storing visited nodes) uses O(n) space. Then derive "
        "Floyd's cycle detection algorithm from scratch — don't just state it, prove "
        "WHY the fast and slow pointers are guaranteed to meet if a cycle exists.",
        correct_answer="Floyd's: slow moves 1, fast moves 2, they must meet in cycle",
        answer_check=r"floyd|slow.*fast|fast.*slow|tortoise.*hare|two.pointer",
        difficulty=4,
        reasoning_hints=["O(n) space", "visited", "set", "slow", "fast", "meet",
                         "guaranteed", "proof", "modular", "cycle length", "catch up"],
    ),
]


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks to avoid false-positive marker matches in code."""
    return re.sub(r"```[\s\S]*?```", "", text)


def score_think_block(response: str, difficulty: int = 3) -> dict:
    """Analyze the quality of reasoning in the response.

    Strips code blocks before scanning for reasoning markers to prevent
    false positives from code comments, variable names, etc.
    Length threshold scales with difficulty (harder = expect more reasoning).
    """
    text = response.strip()
    scores = {}

    # 1. Think block presence
    think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    has_think = bool(think_match)
    scores["think_present"] = 1.0 if has_think else 0.0

    # Use think block content if present, otherwise analyze full response
    reasoning_text = think_match.group(1) if think_match else text

    # Strip code blocks — reasoning markers inside code are false positives
    prose_text = _strip_code_blocks(reasoning_text)

    # 2. Reasoning depth — count reasoning markers (in prose only)
    # These patterns require sentence-boundary context to avoid matching
    # code identifiers like `step_count` or `first_element`
    depth_markers = [
        r"(?:^|\.\s+)step \d",         # "Step 1" at sentence start
        r"(?:^|\.\s+)first(?:ly)?[,.]", # "First," not "first_element"
        r"(?:^|\.\s+)second(?:ly)?[,.]",
        r"(?:^|\.\s+)third(?:ly)?[,.]",
        r"(?:^|\.\s+)next[,.]",
        r"(?:^|\.\s+)then[,.]",
        r"(?:^|\.\s+)finally[,.]",
        r"\bbecause\b",
        r"\btherefore\b",
        r"\bthis means\b",
        r"\bso we\b",
        r"\bwhich gives\b",
        r"\blet me\b",
        r"\blet's\b",
        r"(?:^|\.\s+)consider\b",       # "Consider X" not "considered = true"
        r"\bnotice that\b",
        r"\bthe reason\b",
        r"\bthis is because\b",
    ]
    depth_count = sum(1 for m in depth_markers
                      if re.search(m, prose_text, re.IGNORECASE | re.MULTILINE))
    scores["reasoning_depth"] = min(depth_count / 8.0, 1.0)  # 8+ markers = full score

    # 3. Backtracking / self-correction (prose only)
    # These are inherently prose-like and less prone to code false positives,
    # but we still scan prose_text for consistency
    backtrack_markers = [
        r"\bwait[,.!]\s",               # "Wait, " not "wait()" in code
        r"\bactually[,.]\s",            # "Actually, " not "actually_valid"
        r"\bno[,.]\s.*that's wrong",
        r"\blet me reconsider\b",
        r"\bon second thought\b",
        r"\bI made (?:a |an )?mistake\b",
        r"\bcorrection:\s",             # "Correction: " not "correction_factor"
        r"\bbut wait\b",
        r"\bhmm\b",
        r"\bthat's not right\b",
        r"\blet me re-?think\b",
    ]
    backtrack_count = sum(1 for m in backtrack_markers
                         if re.search(m, prose_text, re.IGNORECASE))
    scores["self_correction"] = min(backtrack_count / 2.0, 1.0)  # 2+ = full score

    # 4. Edge case awareness (prose only)
    edge_markers = [
        r"\bedge case\b",
        r"\bwhat if\b",
        r"\bcorner case\b",
        r"\bempty\b",
        r"\bnull\b|\bnone\b|\bnil\b",
        r"\bboundary\b",
        r"\boverflow\b",
        r"\bnegative\b",
        r"\bzero\b",
        r"\bspecial case\b",
    ]
    edge_count = sum(1 for m in edge_markers
                     if re.search(m, prose_text, re.IGNORECASE))
    scores["edge_awareness"] = min(edge_count / 3.0, 1.0)  # 3+ = full score

    # 5. Concrete examples (traces values, not just abstract) — check full text
    # since examples often appear inside code blocks
    has_concrete = bool(re.search(
        r"(for example|e\.g\.|given|input.*output|returns? \d|= \d|\[.*\d.*\])",
        reasoning_text, re.IGNORECASE
    ))
    scores["concrete_examples"] = 1.0 if has_concrete else 0.0

    # 6. Reasoning length — scale threshold by difficulty
    # D1-D2: 10 lines is deep enough. D4-D5: expect 25+ lines.
    length_threshold = 10 + (difficulty * 3)  # D1=13, D2=16, D3=19, D4=22, D5=25
    reasoning_lines = len([l for l in prose_text.split("\n") if l.strip()])
    scores["reasoning_length"] = min(reasoning_lines / length_threshold, 1.0)

    return scores


def run_probe(probe: ReasoningProbe, server_url: str) -> dict:
    """Run a single reasoning probe and score it."""
    temperature = TEMPERATURE_BY_DIFFICULTY.get(probe.difficulty, DEFAULT_TEMPERATURE)
    try:
        resp = requests.post(
            f"{server_url}/v1/chat/completions",
            json={
                "model": "hiveai",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": probe.prompt},
                ],
                "temperature": temperature,
                "max_tokens": MAX_TOKENS,
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "scores": {}}

        content = resp.json()["choices"][0]["message"]["content"]

        # Score reasoning quality (pass difficulty for length scaling)
        reasoning_scores = score_think_block(content, probe.difficulty)

        # Score answer correctness
        answer_correct = bool(re.search(probe.answer_check, content, re.IGNORECASE))
        reasoning_scores["answer_correct"] = 1.0 if answer_correct else 0.0

        # Score reasoning hint coverage
        text_lower = content.lower()
        hints_found = sum(1 for h in probe.reasoning_hints if h.lower() in text_lower)
        reasoning_scores["hint_coverage"] = (
            hints_found / len(probe.reasoning_hints) if probe.reasoning_hints else 0.0
        )

        # Overall reasoning score (weighted)
        overall = (
            reasoning_scores.get("think_present", 0) * 0.10 +
            reasoning_scores.get("reasoning_depth", 0) * 0.25 +
            reasoning_scores.get("self_correction", 0) * 0.10 +
            reasoning_scores.get("edge_awareness", 0) * 0.10 +
            reasoning_scores.get("concrete_examples", 0) * 0.10 +
            reasoning_scores.get("reasoning_length", 0) * 0.10 +
            reasoning_scores.get("answer_correct", 0) * 0.15 +
            reasoning_scores.get("hint_coverage", 0) * 0.10
        )
        reasoning_scores["overall"] = round(overall, 4)

        return {
            "response": content,
            "scores": reasoning_scores,
            "response_length": len(content),
        }

    except requests.RequestException as e:
        return {"error": str(e), "scores": {}}


def main():
    parser = argparse.ArgumentParser(description="Reasoning quality evaluation")
    parser.add_argument("--server-url", default="http://localhost:11435")
    parser.add_argument("--model-version", default="unknown")
    parser.add_argument("--output", default=None,
                        help="Save detailed results to JSON file")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Reasoning Quality Eval — {args.model_version}")
    print("=" * 60)
    print(f"  Server: {args.server_url}")
    print(f"  Probes: {len(PROBES)}")
    print("=" * 60)

    # Check server
    try:
        resp = requests.get(f"{args.server_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"ERROR: Server health check failed")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"ERROR: Cannot reach server: {e}")
        sys.exit(1)

    results = []
    category_scores = {}
    start = time.time()

    for i, probe in enumerate(PROBES):
        print(f"\n  [{i+1}/{len(PROBES)}] {probe.category} (D{probe.difficulty}): "
              f"{probe.prompt[:70]}...")
        result = run_probe(probe, args.server_url)

        if "error" in result:
            print(f"    ERROR: {result['error']}")
            continue

        scores = result["scores"]
        print(f"    Overall: {scores['overall']:.3f}")
        print(f"    Think block: {'YES' if scores['think_present'] else 'no'} | "
              f"Depth: {scores['reasoning_depth']:.2f} | "
              f"Self-correct: {scores['self_correction']:.2f} | "
              f"Edges: {scores['edge_awareness']:.2f}")
        print(f"    Answer correct: {'YES' if scores['answer_correct'] else 'NO'} | "
              f"Hints: {scores['hint_coverage']:.2f} | "
              f"Examples: {'YES' if scores['concrete_examples'] else 'no'}")

        result["probe"] = {
            "category": probe.category,
            "difficulty": probe.difficulty,
            "prompt": probe.prompt[:100],
        }
        results.append(result)

        # Aggregate by category
        cat = probe.category
        if cat not in category_scores:
            category_scores[cat] = []
        category_scores[cat].append(scores["overall"])

    elapsed = time.time() - start

    # Summary
    print("\n" + "=" * 60)
    print("  REASONING QUALITY SUMMARY")
    print("=" * 60)

    all_scores = [r["scores"]["overall"] for r in results if "scores" in r and r["scores"]]
    all_think = [r["scores"]["think_present"] for r in results if "scores" in r and r["scores"]]
    all_correct = [r["scores"]["answer_correct"] for r in results if "scores" in r and r["scores"]]
    all_depth = [r["scores"]["reasoning_depth"] for r in results if "scores" in r and r["scores"]]

    if all_scores:
        print(f"\n  Overall reasoning score: {sum(all_scores)/len(all_scores):.3f}")
        print(f"  Think blocks present:    {sum(all_think)}/{len(all_think)} "
              f"({sum(all_think)/len(all_think):.0%})")
        print(f"  Answers correct:         {sum(all_correct)}/{len(all_correct)} "
              f"({sum(all_correct)/len(all_correct):.0%})")
        print(f"  Avg reasoning depth:     {sum(all_depth)/len(all_depth):.3f}")

        print(f"\n  By category:")
        for cat, scores in sorted(category_scores.items()):
            avg = sum(scores) / len(scores)
            bar = "#" * int(avg * 30)
            print(f"    {cat:15s}: {avg:.3f}  |{bar}")

    print(f"\n  Time: {elapsed:.0f}s ({len(PROBES)} probes)")
    print("=" * 60)

    # Save detailed results
    if args.output:
        output_data = {
            "model_version": args.model_version,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "overall": round(sum(all_scores)/len(all_scores), 4) if all_scores else 0,
                "think_rate": round(sum(all_think)/len(all_think), 4) if all_think else 0,
                "correct_rate": round(sum(all_correct)/len(all_correct), 4) if all_correct else 0,
                "avg_depth": round(sum(all_depth)/len(all_depth), 4) if all_depth else 0,
                "by_category": {cat: round(sum(s)/len(s), 4)
                                for cat, s in category_scores.items()},
            },
            "probes": results,
        }
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"  Detailed results: {args.output}")

    return 0 if all_scores and sum(all_scores)/len(all_scores) > 0.3 else 1


if __name__ == "__main__":
    sys.exit(main())
