#!/usr/bin/env python3
"""
Audit training data: generation vs understanding ratio + experiment tracking.

Classifies each training pair as "generation" (code/implementation) or
"understanding" (explanation/analysis) and reports the ratio. Optionally
exports a balanced subset.

Usage:
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --output balanced.jsonl
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --test-rank 32

Linux-targeted (WSL2 training environment).
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Keywords that signal generation tasks (implementation-focused)
GENERATION_SIGNALS = re.compile(
    r"\b(implement|write|create|build|code|function|class|struct|"
    r"program|script|module|api|endpoint|handler|server|client|"
    r"algorithm|data structure|parser|compiler|convert|generate|"
    r"template|boilerplate|scaffold|setup|configure|deploy)\b",
    re.IGNORECASE,
)

# Keywords that signal understanding tasks (explanation-focused)
UNDERSTANDING_SIGNALS = re.compile(
    r"\b(explain|describe|what is|what are|how does|why does|"
    r"compare|contrast|difference|advantage|disadvantage|"
    r"when to use|trade.?off|pros and cons|best practice|"
    r"review|analyze|evaluate|assess|critique|verify|"
    r"debug|troubleshoot|diagnose|what.?s wrong|"
    r"concept|principle|pattern|architecture|design|"
    r"summarize|overview|introduction|tutorial)\b",
    re.IGNORECASE,
)


def load_jsonl(path: str) -> list[dict]:
    """Load JSONL training data."""
    pairs = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                pairs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping line {line_num}: {e}", file=sys.stderr)
    return pairs


def classify_pair(pair: dict) -> str:
    """Classify a training pair as 'generation' or 'understanding'.

    Uses instruction text primarily. Falls back to output analysis
    if instruction is ambiguous.
    """
    instruction = pair.get("instruction", "") + " " + pair.get("input", "")
    output = pair.get("output", "")

    gen_score = len(GENERATION_SIGNALS.findall(instruction))
    und_score = len(UNDERSTANDING_SIGNALS.findall(instruction))

    # If instruction is ambiguous, check output characteristics
    if gen_score == und_score:
        # Code-heavy outputs suggest generation
        code_blocks = output.count("```")
        code_lines = sum(1 for line in output.split("\n")
                         if line.strip().startswith(("def ", "fn ", "func ",
                                                     "class ", "import ", "#include",
                                                     "pub ", "const ", "let ", "var ")))
        text_lines = sum(1 for line in output.split("\n")
                         if len(line.strip()) > 20 and not line.strip().startswith(("```", "//", "#", "/*")))

        if code_blocks >= 2 or code_lines > text_lines:
            return "generation"
        elif text_lines > code_lines * 2:
            return "understanding"
        return "generation"  # default to generation when truly ambiguous

    return "generation" if gen_score > und_score else "understanding"


def audit(pairs: list[dict]) -> dict:
    """Analyze the generation vs understanding ratio."""
    classifications = Counter()
    classified_pairs = []

    for pair in pairs:
        label = classify_pair(pair)
        classifications[label] += 1
        classified_pairs.append({**pair, "_classification": label})

    total = len(pairs)
    gen_count = classifications["generation"]
    und_count = classifications["understanding"]

    return {
        "total": total,
        "generation": gen_count,
        "understanding": und_count,
        "gen_pct": round(100 * gen_count / max(total, 1), 1),
        "und_pct": round(100 * und_count / max(total, 1), 1),
        "ratio": f"{gen_count}:{und_count}",
        "classified_pairs": classified_pairs,
    }


def balance_subset(classified_pairs: list[dict], target_ratio: float = 0.5) -> list[dict]:
    """Export a balanced subset targeting the given understanding ratio.

    Keeps all understanding pairs and randomly samples generation pairs
    to match the target ratio.
    """
    import random

    gen_pairs = [p for p in classified_pairs if p["_classification"] == "generation"]
    und_pairs = [p for p in classified_pairs if p["_classification"] == "understanding"]

    # Target: und_count / total = target_ratio
    # So gen_count = und_count * (1 - target_ratio) / target_ratio
    target_gen = int(len(und_pairs) * (1 - target_ratio) / target_ratio)
    target_gen = min(target_gen, len(gen_pairs))

    random.shuffle(gen_pairs)
    balanced = und_pairs + gen_pairs[:target_gen]
    random.shuffle(balanced)

    # Remove classification metadata
    return [{k: v for k, v in p.items() if not k.startswith("_")} for p in balanced]


def print_report(result: dict, rank: int | None = None):
    """Print human-readable audit report."""
    print("=" * 60)
    print("TRAINING DATA AUDIT REPORT")
    print("=" * 60)
    print(f"Total pairs:    {result['total']}")
    print(f"Generation:     {result['generation']} ({result['gen_pct']}%)")
    print(f"Understanding:  {result['understanding']} ({result['und_pct']}%)")
    print(f"Ratio:          {result['ratio']}")
    print()

    # Recommendations
    if result["und_pct"] < 35:
        needed = int(result["generation"] * 0.5) - result["understanding"]
        print(f"RECOMMENDATION: Add ~{max(0, needed)} understanding pairs to reach 50/50")
        print("  Focus: 'explain this code', 'compare X vs Y', 'review this function'")
    elif result["und_pct"] < 45:
        needed = int(result["generation"] * 0.67) - result["understanding"]
        print(f"SUGGESTION: Add ~{max(0, needed)} understanding pairs to reach 40/60 gen/und")
    else:
        print("BALANCED: Ratio is within acceptable range (40-60%)")

    if rank is not None:
        print(f"\n--- LoRA Rank Experiment Tracking ---")
        print(f"Current rank (r): {rank}")
        if rank == 16:
            print("  Standard config. If eval shows underfitting, try r=32.")
            print("  Reference: LLM4SVG used r=32, alpha=32 and matched full fine-tune.")
        elif rank == 32:
            print("  Doubled rank. Monitor for overfitting (train loss << eval).")
            print("  If no improvement over r=16, revert (more params != better).")
        elif rank == 64:
            print("  WARNING: Very high rank. Risk of overfitting on small datasets.")
        print(f"  Log: rank={rank}, data_size={result['total']}, "
              f"gen_ratio={result['gen_pct']}%")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Audit training data: generation vs understanding ratio"
    )
    parser.add_argument("--data", type=str, required=True,
                        help="Path to JSONL training data")
    parser.add_argument("--output", type=str, default=None,
                        help="Export balanced subset to this JSONL path")
    parser.add_argument("--target-ratio", type=float, default=0.5,
                        help="Target understanding ratio for balanced output (default: 0.5)")
    parser.add_argument("--test-rank", type=int, default=None,
                        help="LoRA rank to track for experiment logging (e.g., 32)")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading data from {data_path}...")
    pairs = load_jsonl(str(data_path))
    if not pairs:
        print("ERROR: No valid training pairs found", file=sys.stderr)
        sys.exit(1)

    result = audit(pairs)
    print_report(result, rank=args.test_rank)

    if args.output:
        balanced = balance_subset(result["classified_pairs"], args.target_ratio)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in balanced:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        gen_count = sum(1 for p in result["classified_pairs"]
                        if p["_classification"] == "generation"
                        and {k: v for k, v in p.items() if not k.startswith("_")} in balanced)
        print(f"\nExported {len(balanced)} balanced pairs to {output_path}")
        print(f"  (from {result['total']} total, targeting {args.target_ratio:.0%} understanding)")


if __name__ == "__main__":
    main()
