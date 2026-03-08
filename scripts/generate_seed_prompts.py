#!/usr/bin/env python3
"""
Generate diverse seed prompts for GRPO training.

Extracts prompts from eval_challenges.json and training data,
deduplicates by embedding similarity, outputs seed_prompts.jsonl.

Usage:
    python scripts/generate_seed_prompts.py --output seed_prompts.jsonl
    python scripts/generate_seed_prompts.py --count 500 --source both
    python scripts/generate_seed_prompts.py --source eval --count 200
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_eval_challenges():
    """Load prompts from eval_challenges.json and eval_challenges_hard.json."""
    prompts = []
    for name in ("eval_challenges.json", "eval_challenges_hard.json"):
        path = os.path.join(PROJECT_ROOT, "scripts", name)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            challenges = json.load(f)
        for ch in challenges:
            prompts.append({
                "instruction": ch["instruction"],
                "category": ch.get("category", "general"),
                "difficulty": ch.get("difficulty", 2),
                "expected_concepts": ch.get("expected_concepts", []),
                "test_code": ch.get("test_code", ""),
                "source": "eval",
            })
        logger.info(f"  Loaded {len(challenges)} from {name}")
    return prompts


def load_training_data():
    """Extract instructions from training JSONL files."""
    prompts = []
    data_dir = os.path.join(PROJECT_ROOT, "loras", "training_data")
    # Prefer newest training data first
    for name in ("v8.jsonl", "v7.jsonl", "v6.jsonl", "v5.jsonl"):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            continue
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                inst = row.get("instruction", "")
                inp = row.get("input", "")
                text = f"{inst}\n\n{inp}" if inp else inst
                if len(text) < 30:
                    continue
                # Infer category from instruction keywords
                cat = _infer_category(text)
                prompts.append({
                    "instruction": text,
                    "category": cat,
                    "difficulty": 2,
                    "expected_concepts": [],
                    "test_code": "",
                    "source": f"training:{name}",
                })
                count += 1
        logger.info(f"  Loaded {count} from {name}")
    return prompts


def _infer_category(text):
    """Infer programming category from instruction text."""
    tl = text.lower()
    if any(k in tl for k in ("rust", "cargo", "fn ", "impl ", "struct ", "trait ")):
        return "rust"
    if any(k in tl for k in (" go ", "golang", "goroutine", "func ", "chan ")):
        return "go"
    if any(k in tl for k in ("c++", "cpp", "#include", "std::", "template<")):
        return "cpp"
    if any(k in tl for k in ("javascript", "typescript", "react", "node", "promise")):
        return "javascript"
    if any(k in tl for k in ("hive", "blockchain", "beem", "custom_json")):
        return "hive"
    if any(k in tl for k in ("python", "def ", "import ", "class ")):
        return "python"
    return "general"


def deduplicate_by_similarity(prompts, threshold=0.85):
    """Deduplicate prompts using embedding cosine similarity (or prefix fallback)."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        logger.info("  Using embedding-based deduplication")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        texts = [p["instruction"][:512] for p in prompts]
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        keep = []
        kept_embs = []
        for i, emb in enumerate(embeddings):
            if kept_embs:
                sims = np.dot(np.array(kept_embs), emb)
                if np.max(sims) > threshold:
                    continue
            keep.append(i)
            kept_embs.append(emb)

        deduped = [prompts[i] for i in keep]
        logger.info(f"  Dedup: {len(prompts)} -> {len(deduped)} (threshold={threshold})")
        return deduped

    except ImportError:
        logger.info("  sentence-transformers not available, using prefix dedup")
        seen = set()
        deduped = []
        for p in prompts:
            key = p["instruction"][:150].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        logger.info(f"  Prefix dedup: {len(prompts)} -> {len(deduped)}")
        return deduped


def balance_categories(prompts, target_count):
    """Balance prompts across categories to ensure diversity."""
    by_cat = defaultdict(list)
    for p in prompts:
        by_cat[p["category"]].append(p)

    n_cats = len(by_cat)
    per_cat = max(target_count // n_cats, 10)

    balanced = []
    for cat, items in sorted(by_cat.items()):
        selected = items[:per_cat]
        balanced.extend(selected)
        logger.info(f"  {cat}: {len(selected)}/{len(items)} selected")

    # Fill remaining slots from largest categories
    remaining = target_count - len(balanced)
    if remaining > 0:
        extras = []
        for cat, items in sorted(by_cat.items(), key=lambda x: -len(x[1])):
            for item in items[per_cat:]:
                extras.append(item)
        balanced.extend(extras[:remaining])

    return balanced[:target_count]


def main():
    parser = argparse.ArgumentParser(description="Generate diverse seed prompts for GRPO training")
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "loras", "training_data", "seed_prompts.jsonl"),
                        help="Output JSONL path")
    parser.add_argument("--count", type=int, default=500, help="Target prompt count (default: 500)")
    parser.add_argument("--source", choices=["eval", "training", "both"], default="both",
                        help="Prompt source (default: both)")
    args = parser.parse_args()

    logger.info("Generating seed prompts for GRPO")
    all_prompts = []

    if args.source in ("eval", "both"):
        all_prompts.extend(load_eval_challenges())

    if args.source in ("training", "both"):
        all_prompts.extend(load_training_data())

    logger.info(f"Total raw prompts: {len(all_prompts)}")

    # Deduplicate
    all_prompts = deduplicate_by_similarity(all_prompts)

    # Balance across categories
    if len(all_prompts) > args.count:
        all_prompts = balance_categories(all_prompts, args.count)

    # Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for p in all_prompts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Summary
    cats = defaultdict(int)
    for p in all_prompts:
        cats[p["category"]] += 1
    logger.info(f"\nWrote {len(all_prompts)} seed prompts to {args.output}")
    logger.info(f"Categories: {dict(sorted(cats.items()))}")
    with_tests = sum(1 for p in all_prompts if p.get("test_code"))
    with_concepts = sum(1 for p in all_prompts if p.get("expected_concepts"))
    logger.info(f"With test_code: {with_tests}, with expected_concepts: {with_concepts}")


if __name__ == "__main__":
    main()
