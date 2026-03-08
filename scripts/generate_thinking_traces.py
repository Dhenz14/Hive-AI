#!/usr/bin/env python3
"""Generate <think> block reasoning traces for the hardest training pairs.

Loads existing JSONL training data, scores each pair by difficulty, and uses
a local LLM to generate step-by-step reasoning traces for the hardest ones.
Output pairs have <think>...</think> blocks prepended to the output field.
"""

import argparse
import ast
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DIFFICULTY_KEYWORDS = {"implement", "optimize", "design", "debug", "refactor",
                       "architect", "migrate", "benchmark", "scale", "concurrent"}

DOMAIN_COMBOS = [
    {"rust", "async"}, {"rust", "unsafe"}, {"go", "concurrency"}, {"go", "goroutine"},
    {"c++", "template"}, {"c++", "move semantics"}, {"python", "metaclass"},
    {"typescript", "generics"}, {"distributed", "consensus"}, {"lock-free", "atomic"},
]

REASONING_MARKERS = {"because", "therefore", "first", "then", "however", "since",
                     "consequently", "the reason", "this means", "in order to",
                     "the key insight", "notice that", "consider", "alternatively",
                     "trade-off", "tradeoff", "the problem"}

THINKING_PROMPT = """You are an expert coding assistant. Given the following coding question, I want you to think through it step by step before providing your answer.

QUESTION:
{instruction}

Think carefully about:
- What concepts are involved
- What edge cases exist
- What the optimal approach would be
- Why certain design decisions matter

Wrap your reasoning in <think>...</think> tags, then provide the answer."""


def load_pairs(path: str) -> list[dict[str, Any]]:
    pairs = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                pairs.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping malformed JSON at line %d", i)
    log.info("Loaded %d pairs from %s", len(pairs), path)
    return pairs


def has_thinking(pair: dict) -> bool:
    meta = pair.get("metadata", {})
    if meta.get("has_thinking", False):
        return True
    output = pair.get("output", "")
    return "<think>" in output and "</think>" in output


def python_ast_depth(code: str) -> int:
    """Estimate AST depth for Python code. Returns 0 on parse failure."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0

    def _depth(node: ast.AST) -> int:
        children = list(ast.iter_child_nodes(node))
        if not children:
            return 1
        return 1 + max(_depth(c) for c in children)

    return _depth(tree)


def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```[\w]*\n(.*?)```", text, re.DOTALL)


def code_complexity(pair: dict) -> float:
    """Score code complexity 0-1 from output code blocks."""
    output = pair.get("output", "")
    blocks = extract_code_blocks(output)
    if not blocks:
        return 0.0

    total_lines = sum(len(b.strip().splitlines()) for b in blocks)
    max_depth = 0
    for block in blocks:
        depth = python_ast_depth(block)
        if depth > max_depth:
            max_depth = depth

    # Normalize: 100+ lines -> 1.0, AST depth 10+ -> 1.0
    line_score = min(total_lines / 100.0, 1.0)
    depth_score = min(max_depth / 10.0, 1.0)
    return max(line_score, depth_score)


def domain_combo_score(text: str) -> float:
    """Score multi-domain references 0-1."""
    text_lower = text.lower()
    matches = sum(1 for combo in DOMAIN_COMBOS if all(kw in text_lower for kw in combo))
    return min(matches / 2.0, 1.0)


def difficulty_keyword_score(text: str) -> float:
    """Score difficulty keywords 0-1."""
    text_lower = text.lower()
    hits = sum(1 for kw in DIFFICULTY_KEYWORDS if kw in text_lower)
    return min(hits / 3.0, 1.0)


def concept_count_score(pair: dict) -> float:
    """Score expected concepts from metadata 0-1."""
    meta = pair.get("metadata", {})
    concepts = meta.get("concepts", meta.get("expected_concepts", []))
    if isinstance(concepts, list):
        return min(len(concepts) / 5.0, 1.0)
    return 0.0


def compute_hardness(pair: dict) -> float:
    """Compute hardness score 0-1 as weighted combination of signals."""
    instruction = pair.get("instruction", "")
    full_text = instruction + " " + pair.get("output", "")

    # Instruction length: 200+ chars = 1.0
    length_score = min(len(instruction) / 200.0, 1.0)

    cc = code_complexity(pair)
    dc = domain_combo_score(full_text)
    dk = difficulty_keyword_score(instruction)
    cn = concept_count_score(pair)

    # Weighted average
    score = (
        0.20 * length_score
        + 0.30 * cc
        + 0.20 * dc
        + 0.20 * dk
        + 0.10 * cn
    )
    return round(score, 4)


def detect_model(base_url: str, timeout: int) -> str:
    """Auto-detect model name from the LLM endpoint."""
    try:
        resp = requests.get(f"{base_url}/models", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        if models:
            return models[0].get("id", "unknown")
    except Exception:
        pass
    return "unknown"


def generate_thinking_trace(
    instruction: str,
    base_url: str,
    model: str,
    timeout: int,
    max_retries: int,
) -> str | None:
    """Call local LLM to generate a <think> block for the given instruction."""
    prompt = THINKING_PROMPT.format(instruction=instruction)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if think_match:
                return think_match.group(1).strip()
            log.warning("No <think> block in response (attempt %d/%d)", attempt, max_retries)
        except requests.Timeout:
            log.warning("Timeout on attempt %d/%d", attempt, max_retries)
        except Exception as e:
            log.warning("Error on attempt %d/%d: %s", attempt, max_retries, e)

        if attempt < max_retries:
            time.sleep(2)

    return None


def validate_trace(trace: str, instruction: str) -> bool:
    """Validate quality of a generated thinking trace."""
    if len(trace) < 50:
        return False

    trace_lower = trace.lower()
    marker_hits = sum(1 for m in REASONING_MARKERS if m in trace_lower)
    if marker_hits < 2:
        return False

    # Check for repetitive content: split into sentences, check uniqueness
    sentences = [s.strip() for s in re.split(r'[.!?\n]', trace) if len(s.strip()) > 10]
    if sentences:
        unique_ratio = len(set(sentences)) / len(sentences)
        if unique_ratio < 0.4:
            return False

    # Check it's not just restating the question
    instruction_words = set(instruction.lower().split())
    trace_words = set(trace_lower.split())
    if instruction_words and trace_words:
        overlap = len(instruction_words & trace_words) / max(len(trace_words), 1)
        if overlap > 0.8:
            return False

    return True


def print_stats(pairs: list[dict], scores: list[float]) -> None:
    """Print hardness distribution statistics."""
    if not scores:
        print("No scores to display.")
        return

    sorted_scores = sorted(scores, reverse=True)
    n = len(sorted_scores)
    print(f"\n{'='*50}")
    print(f"Hardness Distribution ({n} pairs)")
    print(f"{'='*50}")
    print(f"  Max:    {sorted_scores[0]:.4f}")
    print(f"  P90:    {sorted_scores[int(n*0.1)]:.4f}")
    print(f"  P75:    {sorted_scores[int(n*0.25)]:.4f}")
    print(f"  Median: {sorted_scores[n//2]:.4f}")
    print(f"  P25:    {sorted_scores[int(n*0.75)]:.4f}")
    print(f"  Min:    {sorted_scores[-1]:.4f}")

    # Histogram buckets
    buckets = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    print(f"\n{'Range':<12} {'Count':>6} {'Bar'}")
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        count = sum(1 for s in scores if lo <= s < hi)
        bar = "#" * (count * 40 // max(n, 1))
        print(f"  [{lo:.1f}-{hi:.1f})  {count:>5}  {bar}")

    with_thinking = sum(1 for p in pairs if has_thinking(p))
    without = n - with_thinking
    print(f"\nWith <think> blocks:    {with_thinking}")
    print(f"Without <think> blocks: {without}")
    print(f"{'='*50}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate <think> reasoning traces for hard training pairs"
    )
    parser.add_argument("--input", default="loras/training_data/v7.jsonl",
                        help="Input JSONL file (default: loras/training_data/v7.jsonl)")
    parser.add_argument("--output", default="loras/training_data/thinking_traces.jsonl",
                        help="Output JSONL file (default: loras/training_data/thinking_traces.jsonl)")
    parser.add_argument("--top-n", type=int, default=500,
                        help="Number of hardest pairs to process (default: 500)")
    parser.add_argument("--hardness-threshold", type=float, default=0.5,
                        help="Minimum hardness score 0-1 (default: 0.5)")
    parser.add_argument("--base-url", default="http://localhost:11435/v1",
                        help="LLM endpoint base URL (default: http://localhost:11435/v1)")
    parser.add_argument("--model", default=None,
                        help="Model name (auto-detected from endpoint if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show hardest pairs without generating traces")
    parser.add_argument("--stats", action="store_true",
                        help="Print hardness distribution and exit")
    parser.add_argument("--max-retries", type=int, default=2,
                        help="Max retries per LLM call (default: 2)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Timeout in seconds per LLM call (default: 120)")
    args = parser.parse_args()

    pairs = load_pairs(args.input)
    if not pairs:
        log.error("No pairs loaded. Exiting.")
        sys.exit(1)

    # Filter to pairs without existing thinking blocks
    candidates = [p for p in pairs if not has_thinking(p)]
    log.info("Candidates without <think> blocks: %d / %d", len(candidates), len(pairs))

    # Score all candidates
    scored = [(p, compute_hardness(p)) for p in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    if args.stats:
        all_scores = [compute_hardness(p) for p in pairs]
        print_stats(pairs, all_scores)
        sys.exit(0)

    # Apply threshold and top-N
    filtered = [(p, s) for p, s in scored if s >= args.hardness_threshold]
    selected = filtered[:args.top_n]
    log.info("Selected %d pairs (threshold=%.2f, top-n=%d)",
             len(selected), args.hardness_threshold, args.top_n)

    if not selected:
        log.warning("No pairs meet the hardness threshold. Try lowering --hardness-threshold.")
        sys.exit(0)

    if args.dry_run:
        print(f"\nTop {len(selected)} hardest pairs (dry run):\n")
        for i, (pair, score) in enumerate(selected[:20], 1):
            instr = pair["instruction"][:100].replace("\n", " ")
            source = pair.get("metadata", {}).get("source", "unknown")
            print(f"  {i:>3}. [{score:.4f}] ({source}) {instr}...")
        if len(selected) > 20:
            print(f"  ... and {len(selected) - 20} more")
        sys.exit(0)

    # Detect model
    model = args.model or detect_model(args.base_url, args.timeout)
    log.info("Using model: %s at %s", model, args.base_url)

    # Generate traces
    results = []
    success = 0
    failed = 0
    start_time = time.time()

    for i, (pair, score) in enumerate(selected, 1):
        instruction = pair["instruction"]
        input_text = pair.get("input", "")
        full_instruction = instruction
        if input_text:
            full_instruction += f"\n\n{input_text}"

        elapsed = time.time() - start_time
        rate = i / max(elapsed, 1)
        eta = (len(selected) - i) / max(rate, 0.01)
        log.info("[%d/%d] Generating trace (hardness=%.4f, ETA=%.0fs) %s",
                 i, len(selected), score, eta, instruction[:80].replace("\n", " "))

        trace = generate_thinking_trace(
            full_instruction, args.base_url, model, args.timeout, args.max_retries
        )

        if trace and validate_trace(trace, instruction):
            # Build output with think block prepended
            original_output = pair.get("output", "")
            new_output = f"<think>\n{trace}\n</think>\n\n{original_output}"

            original_meta = pair.get("metadata", {})
            new_meta = {
                "source": "thinking_trace_gen",
                "has_thinking": True,
                "original_source": original_meta.get("source", "unknown"),
                "hardness_score": score,
            }
            # Preserve useful original metadata
            for key in ("tag", "topic", "domain", "difficulty", "category"):
                if key in original_meta:
                    new_meta[key] = original_meta[key]

            result = {
                "instruction": instruction,
                "input": input_text,
                "output": new_output,
                "metadata": new_meta,
            }
            results.append(result)
            success += 1
        else:
            reason = "validation failed" if trace else "generation failed"
            log.warning("  Skipped (%s): %s", reason, instruction[:60].replace("\n", " "))
            failed += 1

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    total_time = time.time() - start_time
    log.info("Done in %.1fs. Generated %d traces, %d failed. Output: %s",
             total_time, success, failed, args.output)


if __name__ == "__main__":
    main()
