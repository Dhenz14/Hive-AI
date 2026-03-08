#!/usr/bin/env python3
"""
Audit training data: generation vs understanding ratio + experiment tracking.

Classifies each training pair as "generation" (code/implementation) or
"understanding" (explanation/analysis) and reports the ratio. Optionally
exports a balanced subset or generates understanding pairs from existing
generation pairs.

Usage:
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --output balanced.jsonl
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --test-rank 32
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --generate-understanding understanding.jsonl
    python scripts/audit_training_data.py --data loras/training_data/v7.jsonl --generate-understanding understanding.jsonl --understanding-count 500

Linux-targeted (WSL2 training environment).
"""

import argparse
import hashlib
import json
import random
import re
import sys
import textwrap
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


###############################################################################
# Understanding pair generation
###############################################################################

# Regex to extract fenced code blocks: ```lang\n...code...\n```
_CODE_BLOCK_RE = re.compile(
    r"```(\w*)\n(.*?)```", re.DOTALL
)

# Language detection from code content (fallback when fence tag is missing)
_LANG_HINTS = [
    (re.compile(r"\b(fn |impl |let mut |pub fn |use std::)", re.IGNORECASE), "Rust"),
    (re.compile(r"\b(func |go |chan |goroutine|package main)", re.IGNORECASE), "Go"),
    (re.compile(r"(#include|std::|template<|namespace |cout)", re.IGNORECASE), "C++"),
    (re.compile(r"\b(def |import |class |self\.|print\()", re.IGNORECASE), "Python"),
    (re.compile(r"\b(function |const |let |var |=>|async |Promise)", re.IGNORECASE), "JavaScript"),
    (re.compile(r"\b(interface |type |export |import \{)", re.IGNORECASE), "TypeScript"),
]

_FENCE_LANG_MAP = {
    "python": "Python", "py": "Python",
    "rust": "Rust", "rs": "Rust",
    "go": "Go", "golang": "Go",
    "cpp": "C++", "c++": "C++", "c": "C",
    "javascript": "JavaScript", "js": "JavaScript",
    "typescript": "TypeScript", "ts": "TypeScript",
    "java": "Java",
    "ruby": "Ruby", "rb": "Ruby",
    "bash": "Bash", "sh": "Bash", "shell": "Bash",
}


def _infer_language(fence_tag: str, code: str) -> str:
    """Infer programming language from fence tag or code content."""
    if fence_tag:
        mapped = _FENCE_LANG_MAP.get(fence_tag.lower())
        if mapped:
            return mapped
    for pattern, lang in _LANG_HINTS:
        if pattern.search(code[:500]):
            return lang
    return "code"


def _extract_code_blocks(output: str) -> list[tuple[str, str]]:
    """Extract (language, code) tuples from fenced code blocks in output.

    Returns blocks with at least 3 lines of meaningful code.
    """
    blocks = []
    for match in _CODE_BLOCK_RE.finditer(output):
        fence_tag = match.group(1).strip()
        code = match.group(2).strip()
        # Filter out trivially short snippets
        meaningful_lines = [l for l in code.split("\n") if l.strip() and not l.strip().startswith("#")]
        if len(meaningful_lines) < 3:
            continue
        lang = _infer_language(fence_tag, code)
        blocks.append((lang, code))
    return blocks


def _extract_prose_context(output: str) -> str:
    """Extract explanatory prose from output (non-code text).

    Used to build understanding answers from existing generation outputs.
    """
    lines = output.split("\n")
    prose_lines = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block and stripped:
            # Skip lines that look like pure code outside fences
            if stripped.startswith(("def ", "fn ", "func ", "class ", "import ",
                                    "#include", "pub ", "const ", "let ", "var ")):
                continue
            prose_lines.append(line)
    return "\n".join(prose_lines).strip()


def _get_function_names(code: str) -> list[str]:
    """Extract function/method names from code for targeted questions."""
    names = []
    for match in re.finditer(
        r"(?:def |fn |func |function |pub fn |async fn )(\w+)", code
    ):
        name = match.group(1)
        if name not in ("main", "new", "init", "__init__", "test"):
            names.append(name)
    return names


def _get_struct_names(code: str) -> list[str]:
    """Extract struct/class/type names from code."""
    names = []
    for match in re.finditer(
        r"(?:class |struct |type |interface |enum )(\w+)", code
    ):
        names.append(match.group(1))
    return names


def _truncate_code(code: str, max_lines: int = 60) -> str:
    """Truncate code to max_lines, keeping it readable."""
    lines = code.split("\n")
    if len(lines) <= max_lines:
        return code
    return "\n".join(lines[:max_lines]) + "\n// ... (truncated)"


# Understanding pair templates. Each is a (template_name, instruction_fmt, answer_builder).
# instruction_fmt uses {lang}, {code}, {func_name}, {struct_name}, {topic}.
# answer_builder is a callable(lang, code, prose, instruction, func_names, struct_names) -> str.

def _build_explain_answer(lang, code, prose, instruction, func_names, struct_names):
    """Build an explanation answer for 'explain this code' questions."""
    parts = []
    parts.append(f"This {lang} code implements the following:\n")
    if prose:
        # Use existing prose from the generation pair as explanation basis
        parts.append(prose[:2000])
    else:
        parts.append(f"The code addresses the task: {instruction[:300]}\n")
    if func_names:
        parts.append(f"\nKey functions: {', '.join(func_names[:5])}")
    if struct_names:
        parts.append(f"Key types: {', '.join(struct_names[:5])}")
    parts.append(f"\n```{lang.lower()}\n{_truncate_code(code)}\n```")
    parts.append("\nThe implementation works by processing the logic step by step as shown above.")
    return "\n".join(parts)


def _build_trace_answer(lang, code, prose, instruction, func_names, struct_names):
    """Build a trace/walkthrough answer."""
    parts = [f"Let me trace through this {lang} code step by step:\n"]
    lines = [l for l in code.split("\n") if l.strip()][:30]
    for i, line in enumerate(lines[:15], 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "/*", "*")):
            continue
        parts.append(f"**Step {i}**: `{stripped[:100]}`")
        # Add contextual explanation
        if "import" in stripped or "#include" in stripped:
            parts.append(f"  - Imports a dependency needed for the implementation.")
        elif re.match(r"(def |fn |func |function )", stripped):
            parts.append(f"  - Defines a function that handles part of the logic.")
        elif "return" in stripped:
            parts.append(f"  - Returns the computed result.")
        elif "if " in stripped or "match " in stripped:
            parts.append(f"  - Conditional branch that handles different cases.")
        elif "for " in stripped or "while " in stripped or "loop" in stripped:
            parts.append(f"  - Iterates over the data to process each element.")
        else:
            parts.append(f"  - Executes this operation as part of the algorithm.")
    if prose:
        parts.append(f"\n**Summary**: {prose[:500]}")
    return "\n".join(parts)


def _build_review_answer(lang, code, prose, instruction, func_names, struct_names):
    """Build a code review answer."""
    parts = [f"## Code Review: {lang} Implementation\n"]
    code_lines = code.split("\n")
    num_lines = len(code_lines)
    has_error_handling = any(kw in code.lower() for kw in ("try", "catch", "error", "result<", "err"))
    has_comments = any(l.strip().startswith(("//", "#", "/*", "///")) for l in code_lines)
    has_tests = any(kw in code.lower() for kw in ("test", "assert", "#[test]", "def test_"))

    parts.append("### Strengths")
    if has_error_handling:
        parts.append("- Includes error handling, which is important for robustness.")
    if has_comments:
        parts.append("- Contains comments that aid readability.")
    if num_lines < 100:
        parts.append("- Reasonably concise implementation.")
    if func_names and len(func_names) > 1:
        parts.append(f"- Well-decomposed into {len(func_names)} functions: {', '.join(func_names[:4])}.")
    if struct_names:
        parts.append(f"- Uses structured types ({', '.join(struct_names[:3])}) for clarity.")

    parts.append("\n### Areas for Improvement")
    if not has_error_handling:
        parts.append("- Consider adding error handling for edge cases and invalid inputs.")
    if not has_comments:
        parts.append("- Adding documentation comments would improve maintainability.")
    if not has_tests:
        parts.append("- Unit tests would help verify correctness and prevent regressions.")
    if num_lines > 80:
        parts.append("- Consider breaking the implementation into smaller, focused functions.")
    parts.append("- Consider adding input validation at function boundaries.")

    parts.append(f"\n### Overall Assessment")
    parts.append(f"The code addresses: {instruction[:200]}")
    if prose:
        parts.append(f"\n{prose[:400]}")
    return "\n".join(parts)


def _build_whydoes_answer(lang, code, prose, instruction, func_names, struct_names):
    """Build an answer explaining design decisions."""
    parts = []
    topic = instruction[:150].rstrip(".")
    parts.append(f"The design choices in this {lang} code reflect several important considerations:\n")

    if struct_names:
        parts.append(f"**Data modeling**: The use of `{struct_names[0]}` provides a clear abstraction "
                      f"that encapsulates the relevant state and behavior together.")
    if func_names:
        parts.append(f"\n**Function decomposition**: Breaking the logic into functions like "
                      f"`{func_names[0]}` makes the code testable and reusable.")

    # Analyze patterns in the code
    if "async" in code or "await" in code:
        parts.append("\n**Async design**: The asynchronous approach prevents blocking, which is "
                      "essential for I/O-bound operations and concurrent request handling.")
    if "Result<" in code or "Result(" in code or "-> Result" in code:
        parts.append("\n**Error propagation**: Using Result types enables explicit error handling "
                      "that the compiler can verify, preventing silent failures.")
    if "trait " in code or "interface " in code:
        parts.append("\n**Abstraction**: The use of traits/interfaces allows different implementations "
                      "to be swapped without changing the calling code.")
    if "HashMap" in code or "map[" in code or "dict" in code.lower():
        parts.append("\n**Data structure choice**: Hash maps provide O(1) average-case lookups, "
                      "which is appropriate when fast key-based access is needed.")
    if "channel" in code.lower() or "chan " in code or "mpsc" in code:
        parts.append("\n**Concurrency**: Channels provide a safe communication mechanism between "
                      "concurrent tasks without shared mutable state.")

    if prose:
        parts.append(f"\n**Context**: {prose[:500]}")
    return "\n".join(parts)


def _build_compare_answer(lang, code, prose, instruction, func_names, struct_names):
    """Build a comparison/alternatives answer."""
    parts = [f"## Alternative Approaches to This {lang} Implementation\n"]
    topic = instruction[:200]

    parts.append(f"The current implementation ({topic}) takes one approach, but there are "
                 f"several alternatives worth considering:\n")

    parts.append("### Current Approach")
    if func_names:
        parts.append(f"Uses functions: {', '.join(func_names[:3])}")
    if struct_names:
        parts.append(f"With types: {', '.join(struct_names[:3])}")

    parts.append("\n### Alternative 1: Different Abstraction Level")
    parts.append("Instead of the current decomposition, you could use a higher-level "
                 "abstraction (e.g., a framework or library) that handles boilerplate, "
                 "at the cost of less control over the implementation details.")

    parts.append("\n### Alternative 2: Different Paradigm")
    if "class " in code or "struct " in code:
        parts.append("A functional approach using pure functions and immutable data "
                     "could simplify reasoning about state, though it may feel less "
                     "natural in this language.")
    else:
        parts.append("An object-oriented approach with encapsulation could better "
                     "organize state and behavior, though it adds complexity for "
                     "simple use cases.")

    parts.append("\n### Trade-offs")
    parts.append("| Aspect | Current | Alternative |")
    parts.append("|--------|---------|-------------|")
    parts.append("| Readability | Explicit logic flow | Higher abstraction |")
    parts.append("| Performance | Direct control | Framework overhead |")
    parts.append("| Maintainability | Self-contained | Dependency on external code |")
    parts.append("| Testability | Unit-testable functions | May need mocking |")

    if prose:
        parts.append(f"\n{prose[:300]}")
    return "\n".join(parts)


# Template definitions: (name, weight, instruction_builder, answer_builder)
_UNDERSTANDING_TEMPLATES = [
    (
        "explain",
        3,  # higher weight = more common
        lambda lang, code, topic, fn, sn: (
            f"Explain how this {lang} code works:\n\n```{lang.lower()}\n{_truncate_code(code)}\n```"
        ),
        _build_explain_answer,
    ),
    (
        "trace",
        2,
        lambda lang, code, topic, fn, sn: (
            f"Trace through the following {lang} code step by step and explain what happens at each stage:\n\n"
            f"```{lang.lower()}\n{_truncate_code(code, 40)}\n```"
        ),
        _build_trace_answer,
    ),
    (
        "review",
        2,
        lambda lang, code, topic, fn, sn: (
            f"Review this {lang} code for quality, correctness, and best practices:\n\n"
            f"```{lang.lower()}\n{_truncate_code(code)}\n```"
        ),
        _build_review_answer,
    ),
    (
        "what_does",
        2,
        lambda lang, code, topic, fn, sn: (
            f"What does this {lang} code do? Describe its purpose and behavior:\n\n"
            f"```{lang.lower()}\n{_truncate_code(code)}\n```"
        ),
        _build_explain_answer,
    ),
    (
        "why_design",
        2,
        lambda lang, code, topic, fn, sn: (
            f"Why does this {lang} implementation use this particular design? "
            f"What are the design decisions and their rationale?\n\n"
            f"```{lang.lower()}\n{_truncate_code(code)}\n```"
        ),
        _build_whydoes_answer,
    ),
    (
        "compare",
        1,
        lambda lang, code, topic, fn, sn: (
            f"What are alternative approaches to this {lang} implementation? "
            f"Compare trade-offs:\n\n```{lang.lower()}\n{_truncate_code(code, 40)}\n```"
        ),
        _build_compare_answer,
    ),
    (
        "func_explain",
        2,
        lambda lang, code, topic, fn, sn: (
            f"Explain the purpose and behavior of the `{fn[0]}` function in this {lang} code:\n\n"
            f"```{lang.lower()}\n{_truncate_code(code)}\n```"
        ) if fn else None,
        _build_explain_answer,
    ),
    (
        "struct_explain",
        1,
        lambda lang, code, topic, fn, sn: (
            f"What is the role of the `{sn[0]}` type in this {lang} code? "
            f"How does it relate to the overall design?\n\n"
            f"```{lang.lower()}\n{_truncate_code(code)}\n```"
        ) if sn else None,
        _build_whydoes_answer,
    ),
]


def generate_understanding_pairs(
    classified_pairs: list[dict],
    target_count: int = 500,
    seed: int = 42,
) -> list[dict]:
    """Generate understanding-focused training pairs from generation pairs.

    Takes existing generation pairs that contain code in their output and
    transforms them into understanding pairs that ask questions about the code.

    Args:
        classified_pairs: Pairs with _classification metadata from audit().
        target_count: Number of understanding pairs to generate.
        seed: Random seed for reproducibility.

    Returns:
        List of new understanding-focused training pairs (instruction/input/output/metadata).
    """
    rng = random.Random(seed)

    # Collect generation pairs that have extractable code
    candidates = []
    for pair in classified_pairs:
        if pair["_classification"] != "generation":
            continue
        output = pair.get("output", "")
        blocks = _extract_code_blocks(output)
        if not blocks:
            continue
        candidates.append((pair, blocks))

    if not candidates:
        print("WARNING: No generation pairs with code blocks found", file=sys.stderr)
        return []

    print(f"  Found {len(candidates)} generation pairs with extractable code blocks")

    # Build weighted template list
    weighted_templates = []
    for name, weight, inst_builder, ans_builder in _UNDERSTANDING_TEMPLATES:
        for _ in range(weight):
            weighted_templates.append((name, inst_builder, ans_builder))

    # Generate understanding pairs, distributing across candidates
    generated = []
    seen_hashes = set()  # Deduplicate by instruction hash
    attempts = 0
    max_attempts = target_count * 5  # Safety valve

    while len(generated) < target_count and attempts < max_attempts:
        attempts += 1

        # Pick a random candidate and code block
        pair, blocks = rng.choice(candidates)
        lang, code = rng.choice(blocks)
        instruction_text = pair.get("instruction", "") + " " + pair.get("input", "")
        prose = _extract_prose_context(pair.get("output", ""))
        func_names = _get_function_names(code)
        struct_names = _get_struct_names(code)

        # Pick a random template
        tmpl_name, inst_builder, ans_builder = rng.choice(weighted_templates)

        # Build instruction (some templates require func/struct names)
        new_instruction = inst_builder(lang, code, instruction_text, func_names, struct_names)
        if new_instruction is None:
            continue  # Template not applicable (e.g., no function names)

        # Deduplicate
        inst_hash = hashlib.md5(new_instruction[:300].encode()).hexdigest()
        if inst_hash in seen_hashes:
            continue
        seen_hashes.add(inst_hash)

        # Build answer
        answer = ans_builder(lang, code, prose, instruction_text, func_names, struct_names)

        # Compose the training pair
        source_tag = pair.get("metadata", {}).get("tag", pair.get("metadata", {}).get("source", "unknown"))
        new_pair = {
            "instruction": new_instruction,
            "input": "",
            "output": answer,
            "metadata": {
                "source": f"understanding_gen/{tmpl_name}",
                "tag": f"understanding/{tmpl_name}",
                "derived_from": source_tag,
                "has_thinking": False,
            },
        }
        generated.append(new_pair)

    print(f"  Generated {len(generated)} understanding pairs from {len(candidates)} source pairs")
    print(f"  Template distribution:")
    tmpl_counts = Counter(p["metadata"]["tag"].split("/")[1] for p in generated)
    for name, count in sorted(tmpl_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count}")

    return generated


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
    parser.add_argument("--generate-understanding", type=str, default=None,
                        metavar="OUTPUT_PATH",
                        help="Generate understanding pairs from generation pairs "
                             "and write to this JSONL path")
    parser.add_argument("--understanding-count", type=int, default=500,
                        help="Number of understanding pairs to generate (default: 500)")
    parser.add_argument("--understanding-seed", type=int, default=42,
                        help="Random seed for understanding pair generation (default: 42)")
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

    if args.generate_understanding:
        print(f"\nGenerating ~{args.understanding_count} understanding pairs...")
        und_pairs = generate_understanding_pairs(
            result["classified_pairs"],
            target_count=args.understanding_count,
            seed=args.understanding_seed,
        )
        if und_pairs:
            und_path = Path(args.generate_understanding)
            und_path.parent.mkdir(parents=True, exist_ok=True)
            with open(und_path, "w", encoding="utf-8") as f:
                for pair in und_pairs:
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            print(f"\nWrote {len(und_pairs)} understanding pairs to {und_path}")

            # Show what the new ratio would be
            new_total = result["total"] + len(und_pairs)
            new_und = result["understanding"] + len(und_pairs)
            new_gen = result["generation"]
            new_und_pct = round(100 * new_und / max(new_total, 1), 1)
            print(f"  New projected ratio: {new_gen}:{new_und} "
                  f"({round(100 * new_gen / max(new_total, 1), 1)}% gen / {new_und_pct}% und)")
        else:
            print("ERROR: Could not generate any understanding pairs", file=sys.stderr)

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
