#!/usr/bin/env python3
"""
fetch_reasoning_data.py — Download and integrate public reasoning datasets.

Downloads high-quality reasoning traces from HuggingFace, filters for coding
relevance, converts to our training format, and integrates with the data pipeline.

Datasets:
  1. jackrong/Opus-4.6-Reasoning-3000x-filtered  — 3000 Claude Opus reasoning pairs
  2. jackrong/claude-4.5-high-reasoning-250x      — 250 high-quality Claude traces
  3. jackrong/Qwen3.5-reasoning-700x              — 700 Qwen reasoning pairs

Usage:
    python scripts/fetch_reasoning_data.py --list                # Show available datasets
    python scripts/fetch_reasoning_data.py --download all        # Download all
    python scripts/fetch_reasoning_data.py --download opus       # Download specific
    python scripts/fetch_reasoning_data.py --filter              # Filter for coding relevance
    python scripts/fetch_reasoning_data.py --export              # Export to batch format
    python scripts/fetch_reasoning_data.py --stats               # Show dataset statistics
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "loras" / "training_data" / "reasoning_raw"
FILTERED_DIR = PROJECT_ROOT / "loras" / "training_data" / "reasoning_filtered"
BATCH_DIR = PROJECT_ROOT / "scripts" / "distill_batches"

# Dataset registry — correct HF repo IDs from improvement_notes.md §25
DATASETS = {
    "opus": {
        "name": "nohurry/Opus-4.6-Reasoning-3000x-filtered",
        "description": "3000 Claude Opus 4.6 reasoning traces (heavily curated)",
        "expected_pairs": 3000,
        "priority": 1,
    },
    "claude45": {
        "name": "TeichAI/claude-4.5-opus-high-reasoning-250x",
        "description": "250 high-intensity Claude 4.5 Opus reasoning instances",
        "expected_pairs": 250,
        "priority": 2,
    },
    "qwen35": {
        "name": "Jackrong/Qwen3.5-reasoning-700x",
        "description": "700 Qwen 3.5 step-by-step reasoning pairs",
        "expected_pairs": 700,
        "priority": 3,
    },
}

# Coding relevance keywords (at least 2 must match for a pair to be "coding")
CODING_KEYWORDS = [
    r"\b(python|javascript|typescript|rust|go|golang|cpp|c\+\+|java|ruby|swift)\b",
    r"\b(function|class|method|variable|array|string|integer|boolean|struct)\b",
    r"\b(algorithm|data structure|complexity|O\(|sort|search|tree|graph|hash)\b",
    r"\b(API|REST|HTTP|database|SQL|query|server|client|endpoint)\b",
    r"\b(import|require|module|package|library|framework|dependency)\b",
    r"\b(error|exception|debug|test|assert|mock|coverage)\b",
    r"\b(async|await|promise|future|thread|concurrent|parallel)\b",
    r"\b(docker|kubernetes|CI/CD|deploy|git|container|cloud)\b",
    r"\b(code|program|script|compile|runtime|syntax|parse)\b",
    r"\b(implement|refactor|optimize|design pattern|architecture)\b",
    r"```[\w]*\n",  # Code blocks in response
]

# Quality filters
MIN_RESPONSE_LEN = 200       # Skip very short responses
MAX_RESPONSE_LEN = 15000     # Skip walls of text
MIN_INSTRUCTION_LEN = 20     # Skip vague prompts
MIN_THINK_LEN = 50           # Minimum thinking content


def download_dataset(key: str) -> Path:
    """Download a dataset from HuggingFace."""
    if key not in DATASETS:
        logger.error(f"Unknown dataset: {key}. Available: {list(DATASETS.keys())}")
        return None

    info = DATASETS[key]
    logger.info(f"Downloading: {info['name']}")

    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("Install datasets: pip install datasets")
        sys.exit(1)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{key}.jsonl"

    try:
        ds = load_dataset(info["name"], split="train")
        logger.info(f"  Loaded {len(ds)} rows from {info['name']}")

        # Save as JSONL
        count = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for row in ds:
                f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
                count += 1

        logger.info(f"  Saved {count} rows to {out_path}")
        return out_path

    except Exception as e:
        logger.error(f"  Failed to download {info['name']}: {e}")
        logger.info("  Trying alternative: manual download via huggingface_hub")
        try:
            from huggingface_hub import hf_hub_download
            # Try downloading parquet file
            parquet_path = hf_hub_download(
                repo_id=info["name"],
                filename="data/train-00000-of-00001.parquet",
                repo_type="dataset",
            )
            import pyarrow.parquet as pq
            table = pq.read_table(parquet_path)
            count = 0
            with open(out_path, "w", encoding="utf-8") as f:
                for batch in table.to_batches():
                    for row in batch.to_pydict().items():
                        f.write(json.dumps(dict(zip(table.column_names, [col[i] for col in [table.column(n) for n in table.column_names]])), ensure_ascii=False) + "\n")
                        count += 1
            logger.info(f"  Saved {count} rows via parquet fallback")
            return out_path
        except Exception as e2:
            logger.error(f"  Parquet fallback also failed: {e2}")
            return None


def detect_format(row: dict) -> dict | None:
    """Detect and normalize dataset format to {instruction, response}.

    Different HF datasets use different field names:
    - instruction/output
    - prompt/response
    - messages (list of {role, content})
    - conversations (list of {from, value})
    - question/answer
    """
    # Format 1: instruction/output
    if "instruction" in row and "output" in row:
        return {"instruction": row["instruction"], "response": row["output"]}

    # Format 2: prompt/response
    if "prompt" in row and "response" in row:
        return {"instruction": row["prompt"], "response": row["response"]}

    # Format 3: messages list
    if "messages" in row and isinstance(row["messages"], list):
        msgs = row["messages"]
        user_msg = next((m["content"] for m in msgs if m.get("role") == "user"), None)
        asst_msg = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
        if user_msg and asst_msg:
            return {"instruction": user_msg, "response": asst_msg}

    # Format 4: conversations list (ShareGPT format)
    if "conversations" in row and isinstance(row["conversations"], list):
        convs = row["conversations"]
        user_msg = next((c["value"] for c in convs if c.get("from") == "human"), None)
        asst_msg = next((c["value"] for c in convs if c.get("from") == "gpt"), None)
        if user_msg and asst_msg:
            return {"instruction": user_msg, "response": asst_msg}

    # Format 5: question/answer
    if "question" in row and "answer" in row:
        return {"instruction": row["question"], "response": row["answer"]}

    # Format 6: input/output
    if "input" in row and "output" in row:
        return {"instruction": row["input"], "response": row["output"]}

    return None


def has_thinking(text: str) -> bool:
    """Check if response contains reasoning traces."""
    return bool(re.search(r"<think>|<reasoning>|<thought>|Let me think|Step \d+:", text))


def is_coding_relevant(instruction: str, response: str) -> tuple[bool, int]:
    """Check if a pair is coding-relevant. Returns (relevant, keyword_hits)."""
    combined = (instruction + " " + response).lower()
    hits = sum(1 for pattern in CODING_KEYWORDS if re.search(pattern, combined, re.IGNORECASE))
    return hits >= 2, hits


def quality_filter(instruction: str, response: str) -> tuple[bool, str]:
    """Apply quality filters. Returns (passes, reason)."""
    if len(response) < MIN_RESPONSE_LEN:
        return False, "response_too_short"
    if len(response) > MAX_RESPONSE_LEN:
        return False, "response_too_long"
    if len(instruction) < MIN_INSTRUCTION_LEN:
        return False, "instruction_too_short"

    # Check for thinking content quality
    think_match = re.search(r"<think>(.*?)</think>", response, re.DOTALL)
    if think_match and len(think_match.group(1).strip()) < MIN_THINK_LEN:
        return False, "thinking_too_shallow"

    # Check for repetitive content
    sentences = re.split(r"[.!?]\s+", response)
    if len(sentences) > 5:
        unique_ratio = len(set(s.strip().lower() for s in sentences)) / len(sentences)
        if unique_ratio < 0.6:
            return False, "too_repetitive"

    return True, "pass"


def filter_dataset(key: str) -> Path:
    """Filter a raw dataset for coding relevance and quality."""
    raw_path = RAW_DIR / f"{key}.jsonl"
    if not raw_path.exists():
        logger.error(f"Raw dataset not found: {raw_path}. Download first with --download {key}")
        return None

    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FILTERED_DIR / f"{key}_coding.jsonl"

    stats = {
        "total": 0, "parsed": 0, "coding": 0, "quality_pass": 0,
        "has_thinking": 0, "dedup": 0,
        "reject_reasons": {},
    }
    seen_hashes = set()

    with open(raw_path, encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:

        for line in fin:
            stats["total"] += 1
            row = json.loads(line)
            normalized = detect_format(row)
            if not normalized:
                continue
            stats["parsed"] += 1

            instruction = normalized["instruction"]
            response = normalized["response"]

            # Coding relevance
            relevant, hits = is_coding_relevant(instruction, response)
            if not relevant:
                stats["reject_reasons"]["not_coding"] = stats["reject_reasons"].get("not_coding", 0) + 1
                continue
            stats["coding"] += 1

            # Quality filter
            passes, reason = quality_filter(instruction, response)
            if not passes:
                stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1
                continue
            stats["quality_pass"] += 1

            # Dedup by instruction hash
            inst_hash = hashlib.md5(instruction[:200].encode()).hexdigest()
            if inst_hash in seen_hashes:
                stats["reject_reasons"]["duplicate"] = stats["reject_reasons"].get("duplicate", 0) + 1
                continue
            seen_hashes.add(inst_hash)
            stats["dedup"] += 1

            # Track thinking
            if has_thinking(response):
                stats["has_thinking"] += 1

            # Ensure response has <think> tags (add if not present but has reasoning)
            if not re.search(r"<think>", response) and re.search(r"Let me (think|analyze|break)", response):
                # Wrap existing reasoning in <think> tags
                think_match = re.match(r"((?:Let me|First,|I need to).*?)(\n\n|\n```)", response, re.DOTALL)
                if think_match:
                    reasoning = think_match.group(1)
                    rest = response[len(reasoning):]
                    response = f"<think>\n{reasoning}\n</think>\n{rest}"
                    stats["has_thinking"] += 1

            # Write filtered pair
            out_row = {
                "instruction": instruction,
                "input": "",
                "output": response,
                "metadata": {
                    "source": f"reasoning_{key}",
                    "coding_hits": hits,
                    "has_thinking": has_thinking(response),
                },
            }
            fout.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    logger.info(f"\n  Filter results for {key}:")
    logger.info(f"    Total:          {stats['total']}")
    logger.info(f"    Parsed:         {stats['parsed']}")
    logger.info(f"    Coding:         {stats['coding']}")
    logger.info(f"    Quality pass:   {stats['quality_pass']}")
    logger.info(f"    After dedup:    {stats['dedup']}")
    logger.info(f"    Has thinking:   {stats['has_thinking']}")
    if stats["reject_reasons"]:
        logger.info(f"    Rejections:")
        for reason, count in sorted(stats["reject_reasons"].items(), key=lambda x: -x[1]):
            logger.info(f"      {reason}: {count}")

    return out_path


def export_to_batches(max_per_batch: int = 25) -> list[Path]:
    """Export filtered reasoning data as batch files for prepare_v5_data.py.

    Creates batch_pNNNN_reasoning_*.py files that integrate with the
    existing data pipeline.
    """
    if not FILTERED_DIR.exists():
        logger.error("No filtered data found. Run --filter first.")
        return []

    # Collect all filtered pairs
    all_pairs = []
    for jsonl_path in sorted(FILTERED_DIR.glob("*_coding.jsonl")):
        source = jsonl_path.stem.replace("_coding", "")
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                all_pairs.append((source, row))

    if not all_pairs:
        logger.warning("No filtered pairs found.")
        return []

    logger.info(f"Total filtered pairs: {len(all_pairs)}")

    # Find next batch number
    existing = list(BATCH_DIR.glob("batch_p*_reasoning*.py"))
    batch_nums = []
    for f in existing:
        try:
            num = int(f.stem.split("_")[1][1:])
            batch_nums.append(num)
        except (IndexError, ValueError):
            pass
    next_num = max(batch_nums, default=1400) + 1

    # Split into batches
    written_paths = []
    for batch_idx in range(0, len(all_pairs), max_per_batch):
        batch = all_pairs[batch_idx:batch_idx + max_per_batch]
        batch_num = next_num + (batch_idx // max_per_batch)

        lines = [
            f'"""',
            f'batch_p{batch_num}_reasoning.py -- Public reasoning dataset pairs.',
            f'Auto-imported from HuggingFace reasoning datasets.',
            f'Source: {", ".join(set(src for src, _ in batch))}',
            f'"""',
            f'',
            f'PAIRS = [',
        ]

        for i, (source, row) in enumerate(batch):
            tag = f"reason_{source}_{batch_num}_{i+1:02d}"
            instruction = row["instruction"].replace("'''", "' ' '")
            response = row["output"].replace("'''", "' ' '")
            lines.append(f'    ("{tag}",')
            lines.append(f"     r'''{instruction}''',")
            lines.append(f"     r'''{response}'''),")
            lines.append(f"")

        lines.append("]")

        out_path = BATCH_DIR / f"batch_p{batch_num}_reasoning.py"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        written_paths.append(out_path)
        logger.info(f"  Written: {out_path.name} ({len(batch)} pairs)")

    logger.info(f"\nExported {len(all_pairs)} pairs across {len(written_paths)} batch files")
    logger.info(f"Rebuild v5.jsonl with: python scripts/prepare_v5_data.py --export")
    return written_paths


def show_stats():
    """Show statistics for all downloaded and filtered datasets."""
    print("=" * 60)
    print("  REASONING DATASET STATUS")
    print("=" * 60)

    for key, info in DATASETS.items():
        raw_path = RAW_DIR / f"{key}.jsonl"
        filtered_path = FILTERED_DIR / f"{key}_coding.jsonl"

        raw_count = 0
        if raw_path.exists():
            with open(raw_path, encoding="utf-8") as f:
                raw_count = sum(1 for _ in f)

        filtered_count = 0
        thinking_count = 0
        if filtered_path.exists():
            with open(filtered_path, encoding="utf-8") as f:
                for line in f:
                    filtered_count += 1
                    row = json.loads(line)
                    if row.get("metadata", {}).get("has_thinking"):
                        thinking_count += 1

        status = "downloaded" if raw_path.exists() else "not downloaded"
        print(f"\n  [{key}] {info['name']}")
        print(f"    Status:     {status}")
        print(f"    Raw:        {raw_count} / {info['expected_pairs']} expected")
        if filtered_count:
            think_pct = thinking_count / max(filtered_count, 1) * 100
            print(f"    Filtered:   {filtered_count} coding pairs ({think_pct:.0f}% with thinking)")

    # Check batch files
    batch_files = list(BATCH_DIR.glob("batch_p*_reasoning*.py"))
    if batch_files:
        total_batch_pairs = 0
        for bf in batch_files:
            try:
                with open(bf, encoding="utf-8") as f:
                    content = f.read()
                    total_batch_pairs += content.count('("reason_')
            except Exception:
                pass
        print(f"\n  Batch files:  {len(batch_files)} ({total_batch_pairs} pairs)")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Download and integrate reasoning datasets")
    parser.add_argument("--list", action="store_true", help="List available datasets")
    parser.add_argument("--download", type=str, help="Download dataset(s): key or 'all'")
    parser.add_argument("--filter", action="store_true", help="Filter downloaded data for coding relevance")
    parser.add_argument("--export", action="store_true", help="Export filtered data as batch files")
    parser.add_argument("--stats", action="store_true", help="Show dataset statistics")
    parser.add_argument("--max-per-batch", type=int, default=25, help="Max pairs per batch file")
    parser.add_argument("--pipeline", action="store_true", help="Full pipeline: download → filter → export")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable reasoning datasets:")
        for key, info in DATASETS.items():
            print(f"  {key:<10} {info['name']}")
            print(f"  {'':10} {info['description']} (~{info['expected_pairs']} pairs)")
        return

    if args.download:
        keys = list(DATASETS.keys()) if args.download == "all" else [args.download]
        for key in keys:
            download_dataset(key)

    if args.filter:
        for key in DATASETS:
            raw_path = RAW_DIR / f"{key}.jsonl"
            if raw_path.exists():
                filter_dataset(key)

    if args.export:
        export_to_batches(max_per_batch=args.max_per_batch)

    if args.stats:
        show_stats()

    if args.pipeline:
        logger.info("Running full pipeline: download → filter → export")
        for key in DATASETS:
            download_dataset(key)
        for key in DATASETS:
            raw_path = RAW_DIR / f"{key}.jsonl"
            if raw_path.exists():
                filter_dataset(key)
        export_to_batches(max_per_batch=args.max_per_batch)
        show_stats()
        return

    if not any([args.list, args.download, args.filter, args.export, args.stats]):
        parser.print_help()


if __name__ == "__main__":
    main()
