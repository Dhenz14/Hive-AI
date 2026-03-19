#!/usr/bin/env python3
"""
Generate deep reasoning training pairs at scale.

Uses OpenRouter (Claude Sonnet 4) to generate instruction+output pairs with
explicit <think> reasoning blocks, seeded by hand-crafted exemplars.

Usage:
    # Generate 10 pairs for a specific category
    python scripts/generate_deep_reasoning.py --category python_async --count 10

    # Generate all Tier 1 categories
    python scripts/generate_deep_reasoning.py --tier 1

    # Resume interrupted generation
    python scripts/generate_deep_reasoning.py --tier 1 --resume

    # Dry run (show prompts without calling LLM)
    python scripts/generate_deep_reasoning.py --category algo_dp --count 3 --dry-run

    # Validate existing generated file
    python scripts/generate_deep_reasoning.py --validate loras/training_data/deep_reasoning_generated/python_async.jsonl
"""
import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOPIC_MATRIX_PATH = PROJECT_ROOT / "configs" / "topic_matrix.json"
SEED_DIR = PROJECT_ROOT / "loras" / "training_data"
OUTPUT_DIR = PROJECT_ROOT / "loras" / "training_data" / "deep_reasoning_generated"
STATE_FILE = OUTPUT_DIR / "generation_state.json"

# Quality gate thresholds
MIN_OUTPUT_LEN = 500
MIN_THINK_LEN = 100
MIN_REASONING_MARKERS = 3
MAX_RETRIES = 3

REASONING_MARKERS = [
    "because", "therefore", "however", "the key insight", "consider",
    "trade-off", "tradeoff", "alternatively", "edge case", "complexity",
    "notice", "approach", "the problem", "let me think", "this means",
    "so we need", "the challenge", "important", "subtle", "the trick",
    "option", "pro:", "con:", "if we", "but wait", "actually",
    "let me", "i need", "the issue", "this works", "this fails",
    "worst case", "best case", "o(n", "o(1", "o(log", "time:",
    "space:", "hmm", "wait", "key", "insight", "design",
    "decision", "choice", "strategy", "technique", "pattern",
]

SHALLOW_PATTERNS = [
    "as an ai", "i hope this helps", "feel free to ask",
    "here's a simple", "let me know if", "i'd be happy to",
]

# Meta-prompt template for generating pairs
GENERATION_PROMPT = """You are generating high-quality training data for a coding AI assistant.
Create a coding instruction and its complete answer with deep reasoning.

TOPIC: {category_description}
DIFFICULTY: {difficulty}
SPECIFIC FOCUS: {focus_area}

Here are examples of the exact format and quality level expected:

{seed_examples}

Now create a NEW, UNIQUE coding problem and answer in the same format.

Requirements:
1. The instruction must be a specific, implementable coding task (not vague/theoretical)
2. The output MUST start with <think>...</think> containing genuine step-by-step reasoning:
   - Analyze the problem's core challenge
   - Consider 2+ approaches with trade-offs
   - Walk through edge cases
   - Explain WHY the chosen approach is best
3. After </think>, provide complete, working code with:
   - Full implementation (not pseudocode, not snippets)
   - Example usage with expected output
   - Time/space complexity analysis
4. The reasoning in <think> must show genuine problem-solving, not just restating the question
5. Output must be at least 800 characters total
6. Use the topic's primary language unless the instruction specifies otherwise

CRITICAL: Do NOT copy the seed examples. Create something genuinely new and different.

Respond with ONLY valid JSON in this exact format (no markdown, no code fences around the JSON):
{{"instruction": "your instruction here", "output": "<think>\\nyour reasoning here\\n</think>\\n\\n```lang\\nyour code here\\n```\\n\\nyour explanation here"}}"""


def load_topic_matrix() -> dict:
    """Load the topic matrix configuration."""
    with open(TOPIC_MATRIX_PATH) as f:
        return json.load(f)


def load_seed_examples(batch_names: list[str], max_per_batch: int = 2) -> str:
    """Load seed examples from hand-crafted batches for few-shot prompting."""
    examples = []
    for batch_name in batch_names:
        # Find matching batch file
        for path in SEED_DIR.glob(f"deep_reasoning_{batch_name}.jsonl"):
            with open(path, encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            # Pick random examples from this batch
            selected = random.sample(lines, min(max_per_batch, len(lines)))
            for pair in selected:
                examples.append(
                    f"---\nInstruction: {pair['instruction']}\n\n"
                    f"Output: {pair['output'][:2000]}...\n---"
                )
    if not examples:
        # Fallback: use a generic example description
        return "(No seed examples available — generate high-quality reasoning from scratch)"
    return "\n\n".join(examples[:3])  # Max 3 examples to fit context


def load_generation_state() -> dict:
    """Load progress state for resume support."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_generation_state(state: dict):
    """Save progress state."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def call_openrouter(prompt: str, model: str = "anthropic/claude-sonnet-4") -> str | None:
    """Call OpenRouter API to generate a response."""
    import requests

    api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")
    base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        logger.error("OPENROUTER_API_KEY not set. Set AI_INTEGRATIONS_OPENROUTER_API_KEY env var.")
        return None

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.7,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"OpenRouter call failed: {e}")
        return None


def call_local_llm(prompt: str) -> str | None:
    """Call local llama-server as fallback."""
    import requests

    base_url = os.environ.get("LLAMA_SERVER_BASE_URL", "http://localhost:11435")
    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": "hiveai",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.7,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.debug(f"Local LLM call failed: {e}")
        return None


def generate_llm_response(prompt: str, backend: str = "auto") -> str | None:
    """Generate response using the best available LLM."""
    if backend == "openrouter":
        return call_openrouter(prompt)
    elif backend == "local":
        return call_local_llm(prompt)
    else:  # auto
        result = call_openrouter(prompt)
        if result:
            return result
        logger.info("OpenRouter unavailable, falling back to local LLM")
        return call_local_llm(prompt)


# === Quality Gates ===

def gate_has_think_block(output: str) -> bool:
    """G1: Must have <think>...</think> block."""
    return bool(re.search(r'<think>.*?</think>', output, re.DOTALL))


def gate_has_code_block(output: str) -> bool:
    """G2: Must have at least one fenced code block."""
    return bool(re.search(r'```\w*\n', output))


def gate_min_output_length(output: str) -> bool:
    """G3: Output must be >= 500 chars."""
    return len(output) >= MIN_OUTPUT_LEN


def gate_min_think_length(output: str) -> bool:
    """G4: Think block must be >= 100 chars."""
    match = re.search(r'<think>(.*?)</think>', output, re.DOTALL)
    if not match:
        return False
    return len(match.group(1).strip()) >= MIN_THINK_LEN


def gate_reasoning_markers(output: str) -> bool:
    """G5: Must have >= 3 reasoning markers in think block."""
    match = re.search(r'<think>(.*?)</think>', output, re.DOTALL)
    if not match:
        return False
    think_text = match.group(1).lower()
    count = sum(1 for marker in REASONING_MARKERS if marker in think_text)
    return count >= MIN_REASONING_MARKERS


def gate_no_shallow_patterns(output: str) -> bool:
    """G6: No shallow/generic AI patterns."""
    lower = output.lower()
    return not any(pattern in lower for pattern in SHALLOW_PATTERNS)


def gate_instruction_quality(instruction: str) -> bool:
    """Check instruction is specific enough."""
    if len(instruction) < 20:
        return False
    # Should contain a verb (implement, write, build, design, create, etc.)
    action_words = ["implement", "write", "build", "design", "create", "solve",
                     "debug", "optimize", "refactor", "explain", "fix"]
    lower = instruction.lower()
    return any(word in lower for word in action_words)


def validate_pair(instruction: str, output: str) -> tuple[bool, list[str]]:
    """Run all quality gates. Returns (passed, list of failures)."""
    failures = []

    if not gate_instruction_quality(instruction):
        failures.append("instruction_quality: too short or no action verb")

    if not gate_has_think_block(output):
        failures.append("G1: missing <think>...</think> block")

    if not gate_has_code_block(output):
        failures.append("G2: missing fenced code block")

    if not gate_min_output_length(output):
        failures.append(f"G3: output too short ({len(output)} < {MIN_OUTPUT_LEN})")

    if not gate_min_think_length(output):
        failures.append("G4: think block too short")

    if not gate_reasoning_markers(output):
        failures.append("G5: insufficient reasoning markers")

    if not gate_no_shallow_patterns(output):
        failures.append("G6: contains shallow AI patterns")

    return len(failures) == 0, failures


def parse_llm_response(raw: str) -> tuple[str, str] | None:
    """Parse the LLM response into (instruction, output). Returns None on parse failure."""
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        if "instruction" in data and "output" in data:
            return data["instruction"], data["output"]
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code fences
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)```', raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1).strip())
            if "instruction" in data and "output" in data:
                return data["instruction"], data["output"]
        except json.JSONDecodeError:
            pass

    # Try finding JSON-like structure
    json_match = re.search(r'\{[^{}]*"instruction"[^{}]*"output"[^{}]*\}', raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return data["instruction"], data["output"]
        except (json.JSONDecodeError, KeyError):
            pass

    logger.debug(f"Failed to parse LLM response: {raw[:200]}...")
    return None


def generate_pair(category: dict, backend: str = "auto") -> dict | None:
    """Generate a single training pair for a category."""
    # Pick random template, focus area, and difficulty
    template = random.choice(category["templates"])
    focus = random.choice(category["focus_areas"])
    difficulty = random.choices(
        ["easy", "medium", "hard"],
        weights=[
            category["difficulty_dist"]["easy"],
            category["difficulty_dist"]["medium"],
            category["difficulty_dist"]["hard"],
        ]
    )[0]

    # Load seed examples
    seed_batches = category.get("seed_batches", [])
    seed_text = load_seed_examples(seed_batches)

    # Build prompt
    prompt = GENERATION_PROMPT.format(
        category_description=category["description"],
        difficulty=difficulty,
        focus_area=focus,
        seed_examples=seed_text,
    )

    # Call LLM with retries
    for attempt in range(MAX_RETRIES):
        raw = generate_llm_response(prompt, backend)
        if not raw:
            logger.warning(f"LLM returned empty (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(2 ** attempt)
            continue

        parsed = parse_llm_response(raw)
        if not parsed:
            logger.warning(f"Failed to parse response (attempt {attempt + 1}/{MAX_RETRIES})")
            continue

        instruction, output = parsed

        # Validate
        passed, failures = validate_pair(instruction, output)
        if passed:
            return {
                "instruction": instruction,
                "input": "",
                "output": output,
            }
        else:
            logger.info(f"Quality gate failures (attempt {attempt + 1}): {failures}")

    return None  # All retries failed


def generate_for_category(category: dict, count: int, backend: str = "auto",
                          dry_run: bool = False) -> list[dict]:
    """Generate pairs for a single category."""
    cat_id = category["id"]
    output_path = OUTPUT_DIR / f"{cat_id}.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing pairs for this category (resume support)
    existing = []
    if output_path.exists():
        with open(output_path) as f:
            existing = [json.loads(line) for line in f if line.strip()]

    remaining = count - len(existing)
    if remaining <= 0:
        logger.info(f"[{cat_id}] Already have {len(existing)}/{count} pairs — skipping")
        return existing

    logger.info(f"[{cat_id}] Generating {remaining} pairs (have {len(existing)}/{count})")

    if dry_run:
        # Show what would be generated
        seed_text = load_seed_examples(category.get("seed_batches", []))
        focus = random.choice(category["focus_areas"])
        prompt = GENERATION_PROMPT.format(
            category_description=category["description"],
            difficulty="medium",
            focus_area=focus,
            seed_examples=seed_text[:500] + "...",
        )
        print(f"\n{'='*60}")
        print(f"Category: {cat_id}")
        print(f"Would generate: {remaining} pairs")
        print(f"Sample prompt:\n{prompt[:1000]}...")
        print(f"{'='*60}")
        return existing

    generated = 0
    failed = 0
    for i in range(remaining):
        pair = generate_pair(category, backend)
        if pair:
            # Append to file
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            existing.append(pair)
            generated += 1
            if generated % 10 == 0:
                logger.info(f"[{cat_id}] Progress: {generated}/{remaining} generated, {failed} failed")
        else:
            failed += 1

        # Rate limiting: 1 request per 2 seconds to avoid API limits
        time.sleep(2)

    logger.info(f"[{cat_id}] Done: {generated} generated, {failed} failed, {len(existing)} total")

    # Update state
    state = load_generation_state()
    state[cat_id] = {"generated": len(existing), "target": count, "failed": failed}
    save_generation_state(state)

    return existing


def validate_file(path: str):
    """Validate an existing JSONL file against quality gates."""
    path = Path(path)
    if not path.exists():
        print(f"File not found: {path}")
        return

    total = 0
    passed = 0
    failed = 0
    failure_counts = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            pair = json.loads(line)
            ok, failures = validate_pair(pair.get("instruction", ""), pair.get("output", ""))
            if ok:
                passed += 1
            else:
                failed += 1
                for f_msg in failures:
                    gate = f_msg.split(":")[0]
                    failure_counts[gate] = failure_counts.get(gate, 0) + 1

    print(f"\nValidation report for {path.name}:")
    print(f"  Total: {total}")
    print(f"  Passed: {passed} ({passed/max(total,1)*100:.1f}%)")
    print(f"  Failed: {failed} ({failed/max(total,1)*100:.1f}%)")
    if failure_counts:
        print(f"  Failure breakdown:")
        for gate, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
            print(f"    {gate}: {count}")


def merge_all_generated(output_path: str = None):
    """Merge all per-category JSONL files into one."""
    if output_path is None:
        output_path = SEED_DIR / "deep_reasoning_5k.jsonl"

    all_pairs = []
    for jsonl_file in sorted(OUTPUT_DIR.glob("*.jsonl")):
        if jsonl_file.name == "generation_state.json":
            continue
        with open(jsonl_file) as f:
            pairs = [json.loads(line) for line in f if line.strip()]
        all_pairs.extend(pairs)
        logger.info(f"  {jsonl_file.name}: {len(pairs)} pairs")

    # Dedup by instruction hash
    seen = set()
    unique = []
    for pair in all_pairs:
        key = hashlib.md5(pair["instruction"].lower().strip().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(pair)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in unique:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    logger.info(f"Merged {len(unique)} unique pairs (from {len(all_pairs)} total) → {output_path}")
    return unique


def main():
    parser = argparse.ArgumentParser(description="Generate deep reasoning training pairs")
    parser.add_argument("--category", type=str, help="Generate for a specific category ID")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Generate all categories in a tier")
    parser.add_argument("--count", type=int, help="Override pair count per category")
    parser.add_argument("--backend", default="auto", choices=["auto", "openrouter", "local"],
                        help="LLM backend to use")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts without generating")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state")
    parser.add_argument("--validate", type=str, help="Validate an existing JSONL file")
    parser.add_argument("--merge", action="store_true", help="Merge all generated files into one")
    parser.add_argument("--stats", action="store_true", help="Show generation progress stats")
    args = parser.parse_args()

    matrix = load_topic_matrix()
    categories = matrix["categories"]

    if args.validate:
        validate_file(args.validate)
        return

    if args.merge:
        merge_all_generated()
        return

    if args.stats:
        state = load_generation_state()
        total_gen = sum(v.get("generated", 0) for v in state.values())
        total_target = sum(c["count"] for c in categories)
        print(f"Generation progress: {total_gen}/{total_target} ({total_gen/max(total_target,1)*100:.1f}%)")
        for cat in categories:
            cid = cat["id"]
            s = state.get(cid, {})
            gen = s.get("generated", 0)
            target = cat["count"]
            status = "DONE" if gen >= target else f"{gen}/{target}"
            print(f"  [{cat['tier']}] {cid:25s} {status:>10s}  ({cat['domain']})")
        return

    # Select categories to generate
    if args.category:
        selected = [c for c in categories if c["id"] == args.category]
        if not selected:
            print(f"Category '{args.category}' not found. Available:")
            for c in categories:
                print(f"  {c['id']} ({c['domain']}, tier {c['tier']})")
            return
    elif args.tier:
        selected = [c for c in categories if c["tier"] == args.tier]
    else:
        print("Specify --category, --tier, --validate, --merge, or --stats")
        parser.print_help()
        return

    # Generate
    total_generated = 0
    for cat in selected:
        count = args.count or cat["count"]
        pairs = generate_for_category(cat, count, backend=args.backend, dry_run=args.dry_run)
        total_generated += len(pairs)

    if not args.dry_run:
        logger.info(f"Total: {total_generated} pairs across {len(selected)} categories")


if __name__ == "__main__":
    main()
