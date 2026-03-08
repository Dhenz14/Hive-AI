#!/usr/bin/env python3
"""
scripts/score_training_data.py — Score training pairs by difficulty, novelty, and quality.

Implements the importance scoring concept from improvement_notes.md §6:
Score each training pair 0-1 for difficulty/novelty/quality. Identify redundant
easy pairs and highlight unique hard ones for v9 curation.

Scoring dimensions:
  - Difficulty (0-1): response complexity, code nesting depth, concept density
  - Novelty (0-1): uniqueness vs other pairs (inverse cosine similarity)
  - Quality (0-1): response structure, code presence, explanation depth
  - Importance = weighted combination (used for filtering)

Usage:
    python scripts/score_training_data.py loras/training_data/v7.jsonl
    python scripts/score_training_data.py loras/training_data/v9_research_pairs.jsonl --top 20
    python scripts/score_training_data.py loras/training_data/v7.jsonl --drop-below 0.3 --output filtered.jsonl
    python scripts/score_training_data.py loras/training_data/v7.jsonl --json --top 50
"""

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

# Weights for final importance score
W_DIFFICULTY = 0.35
W_NOVELTY = 0.35
W_QUALITY = 0.30


# ---------------------------------------------------------------------------
# Difficulty scoring
# ---------------------------------------------------------------------------

# Language keywords indicating advanced concepts
ADVANCED_CONCEPTS = {
    # Concurrency
    "async", "await", "goroutine", "channel", "mutex", "semaphore", "atomic",
    "thread", "spawn", "select!", "tokio", "WaitGroup", "errgroup",
    # Advanced type systems
    "generic", "trait", "impl", "lifetime", "borrow", "ownership", "SFINAE",
    "concepts", "constexpr", "enable_if", "void_t", "PhantomData",
    # Design patterns
    "circuit_breaker", "factory", "observer", "strategy", "decorator",
    "singleton", "builder", "middleware",
    # Systems
    "RAII", "move_semantic", "smart_pointer", "unique_ptr", "shared_ptr",
    "Arc", "Rc", "Box", "Pin",
    # Error handling
    "Result", "Option", "Either", "thiserror", "anyhow",
    # Advanced Python
    "metaclass", "__new__", "__init_subclass__", "descriptor", "contextvars",
    "asynccontextmanager",
}

EASY_INDICATORS = {
    "hello world", "print(", "console.log", "fmt.Println",
    "for i in range", "basic", "simple", "beginner",
}


def score_difficulty(instruction: str, output: str) -> float:
    """Score difficulty of a training pair (0=trivial, 1=expert)."""
    combined = f"{instruction} {output}".lower()

    score = 0.0

    # 1. Advanced concept density (0-0.3)
    concept_hits = sum(1 for c in ADVANCED_CONCEPTS if c.lower() in combined)
    score += min(concept_hits / 8, 1.0) * 0.3

    # 2. Code complexity — nesting depth proxy (0-0.2)
    indent_levels = [len(line) - len(line.lstrip()) for line in output.split("\n") if line.strip()]
    if indent_levels:
        max_indent = max(indent_levels)
        avg_indent = sum(indent_levels) / len(indent_levels)
        # Deep nesting = more complex
        score += min(max_indent / 24, 1.0) * 0.1
        score += min(avg_indent / 8, 1.0) * 0.1

    # 3. Response length — longer usually = harder (0-0.2)
    word_count = len(output.split())
    score += min(word_count / 500, 1.0) * 0.2

    # 4. Multi-language or multi-concept (0-0.15)
    lang_markers = ["```python", "```rust", "```go", "```cpp", "```c++",
                     "```javascript", "```typescript", "```java", "```sql"]
    langs_used = sum(1 for m in lang_markers if m in output.lower())
    if langs_used >= 2:
        score += 0.15
    elif langs_used == 1:
        score += 0.05

    # 5. Reasoning traces present (0-0.15)
    if "<think>" in output:
        think_match = re.search(r"<think>(.*?)</think>", output, re.DOTALL)
        if think_match and len(think_match.group(1)) > 100:
            score += 0.15
        elif think_match:
            score += 0.08

    # Penalize trivial pairs
    easy_hits = sum(1 for e in EASY_INDICATORS if e in combined)
    if easy_hits >= 2 and word_count < 100:
        score *= 0.5

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def score_quality(instruction: str, output: str) -> float:
    """Score quality of the output (0=garbage, 1=excellent)."""
    score = 0.0

    # 1. Code presence and structure (0-0.3)
    code_blocks = re.findall(r"```[\w]*\n.*?```", output, re.DOTALL)
    if code_blocks:
        total_code_len = sum(len(b) for b in code_blocks)
        score += min(total_code_len / 500, 1.0) * 0.2
        # Language-tagged code blocks are better
        tagged = sum(1 for b in code_blocks if re.match(r"```\w+", b))
        if tagged >= 1:
            score += 0.1

    # 2. Explanation presence — text outside code blocks (0-0.25)
    text_only = re.sub(r"```.*?```", "", output, flags=re.DOTALL)
    text_words = len(text_only.split())
    if text_words > 50:
        score += 0.25
    elif text_words > 20:
        score += 0.15
    elif text_words > 5:
        score += 0.05

    # 3. Structure — headings, lists, organized output (0-0.15)
    has_headings = bool(re.search(r"^#{1,4}\s", output, re.MULTILINE))
    has_lists = bool(re.search(r"^[\-\*]\s", output, re.MULTILINE))
    has_numbered = bool(re.search(r"^\d+\.\s", output, re.MULTILINE))
    structure_count = sum([has_headings, has_lists, has_numbered])
    score += min(structure_count / 2, 1.0) * 0.15

    # 4. Instruction-output alignment (0-0.15)
    # Check if key terms from instruction appear in output
    inst_words = set(w.lower() for w in instruction.split() if len(w) > 4)
    if inst_words:
        out_lower = output.lower()
        alignment = sum(1 for w in inst_words if w in out_lower) / len(inst_words)
        score += alignment * 0.15

    # 5. Not repetitive (0-0.15)
    sentences = re.split(r"[.!?]\n", output)
    if len(sentences) > 3:
        unique = len(set(s.strip().lower()[:50] for s in sentences if s.strip()))
        ratio = unique / len(sentences)
        score += min(ratio, 1.0) * 0.15
    else:
        score += 0.10  # Short outputs get partial credit

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Novelty scoring (batch-level — requires all pairs)
# ---------------------------------------------------------------------------

def compute_novelty_scores(pairs: list[dict]) -> list[float]:
    """Score novelty of each pair relative to all others.

    Uses instruction fingerprinting (trigram overlap) for fast similarity.
    Novel pairs that cover unique topics score high; redundant pairs score low.
    """
    if len(pairs) <= 1:
        return [1.0] * len(pairs)

    # Build trigram fingerprints for each instruction
    def trigrams(text: str) -> set:
        words = text.lower().split()
        if len(words) < 3:
            return set(words)
        return {f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words) - 2)}

    fingerprints = [trigrams(p.get("instruction", "")) for p in pairs]

    novelty_scores = []
    for i, fp_i in enumerate(fingerprints):
        if not fp_i:
            novelty_scores.append(0.5)
            continue

        # Find max similarity to any other pair
        max_sim = 0.0
        for j, fp_j in enumerate(fingerprints):
            if i == j or not fp_j:
                continue
            # Jaccard similarity
            intersection = len(fp_i & fp_j)
            union = len(fp_i | fp_j)
            sim = intersection / union if union > 0 else 0.0
            max_sim = max(max_sim, sim)

        # Novelty = inverse of max similarity
        novelty_scores.append(1.0 - max_sim)

    return novelty_scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def score_file(input_path: str, top_n: int = 0, drop_below: float = 0.0,
               output_path: str = None, json_output: bool = False):
    """Score all pairs in a JSONL file."""
    pairs = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    if not pairs:
        print("No pairs found.", file=sys.stderr)
        return

    # Score each pair
    difficulties = [score_difficulty(p.get("instruction", ""), p.get("output", "")) for p in pairs]
    qualities = [score_quality(p.get("instruction", ""), p.get("output", "")) for p in pairs]
    novelties = compute_novelty_scores(pairs)

    # Compute importance
    scored = []
    for i, pair in enumerate(pairs):
        importance = (W_DIFFICULTY * difficulties[i] +
                     W_NOVELTY * novelties[i] +
                     W_QUALITY * qualities[i])
        scored.append({
            "index": i,
            "instruction_preview": pair.get("instruction", "")[:80],
            "difficulty": round(difficulties[i], 3),
            "novelty": round(novelties[i], 3),
            "quality": round(qualities[i], 3),
            "importance": round(importance, 3),
            "output_len": len(pair.get("output", "").split()),
        })

    # Sort by importance descending
    scored.sort(key=lambda x: -x["importance"])

    # Stats
    avg_diff = sum(difficulties) / len(difficulties)
    avg_nov = sum(novelties) / len(novelties)
    avg_qual = sum(qualities) / len(qualities)
    avg_imp = sum(s["importance"] for s in scored) / len(scored)

    if json_output:
        output = {
            "file": str(input_path),
            "total_pairs": len(pairs),
            "stats": {
                "avg_difficulty": round(avg_diff, 3),
                "avg_novelty": round(avg_nov, 3),
                "avg_quality": round(avg_qual, 3),
                "avg_importance": round(avg_imp, 3),
            },
            "distribution": {
                "high_importance": sum(1 for s in scored if s["importance"] >= 0.6),
                "medium_importance": sum(1 for s in scored if 0.3 <= s["importance"] < 0.6),
                "low_importance": sum(1 for s in scored if s["importance"] < 0.3),
            },
            "pairs": scored[:top_n] if top_n else scored,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*75}")
        print(f"  TRAINING DATA IMPORTANCE SCORES: {Path(input_path).name}")
        print(f"{'='*75}")
        print(f"  Total pairs:      {len(pairs)}")
        print(f"  Avg difficulty:   {avg_diff:.3f}")
        print(f"  Avg novelty:      {avg_nov:.3f}")
        print(f"  Avg quality:      {avg_qual:.3f}")
        print(f"  Avg importance:   {avg_imp:.3f}")
        print()

        # Distribution
        high = sum(1 for s in scored if s["importance"] >= 0.6)
        med = sum(1 for s in scored if 0.3 <= s["importance"] < 0.6)
        low = sum(1 for s in scored if s["importance"] < 0.3)
        print(f"  Distribution: {high} high (>=0.6)  |  {med} medium  |  {low} low (<0.3)")
        print()

        # Top/bottom table
        display = scored[:top_n] if top_n else scored[:20]
        print(f"  {'#':>4}  {'Diff':>5}  {'Nov':>5}  {'Qual':>5}  {'IMP':>5}  {'Words':>5}  Instruction")
        print(f"  {'-'*70}")
        for s in display:
            print(f"  {s['index']:4d}  {s['difficulty']:5.3f}  {s['novelty']:5.3f}  "
                  f"{s['quality']:5.3f}  {s['importance']:5.3f}  {s['output_len']:5d}  "
                  f"{s['instruction_preview'][:50]}")

        if not top_n:
            print(f"\n  ... showing top 20 of {len(scored)} (use --top N for more)")

        # Bottom 5 (candidates for removal)
        print(f"\n  LOWEST IMPORTANCE (candidates for removal):")
        print(f"  {'#':>4}  {'Diff':>5}  {'Nov':>5}  {'Qual':>5}  {'IMP':>5}  Instruction")
        print(f"  {'-'*70}")
        for s in scored[-5:]:
            print(f"  {s['index']:4d}  {s['difficulty']:5.3f}  {s['novelty']:5.3f}  "
                  f"{s['quality']:5.3f}  {s['importance']:5.3f}  "
                  f"{s['instruction_preview'][:50]}")

    # Export filtered file if requested
    if drop_below > 0 and output_path:
        kept = [pairs[s["index"]] for s in scored if s["importance"] >= drop_below]
        dropped = len(pairs) - len(kept)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in kept:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        print(f"\n  Exported {len(kept)} pairs (dropped {dropped} below {drop_below}) → {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Score training data by difficulty, novelty, and quality")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("--top", type=int, default=0, help="Show top N pairs")
    parser.add_argument("--drop-below", type=float, default=0.0,
                        help="Drop pairs below this importance threshold")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for filtered JSONL (requires --drop-below)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    score_file(args.input, args.top, args.drop_below, args.output, args.json)


if __name__ == "__main__":
    main()
