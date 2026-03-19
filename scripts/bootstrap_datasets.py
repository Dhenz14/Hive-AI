#!/usr/bin/env python3
"""Bootstrap public datasets for synthetic traffic generation.

Downloads coding Q&A datasets from HuggingFace, samples and classifies
queries, and writes a unified JSONL file for synthetic_traffic.py.

Usage:
    python scripts/bootstrap_datasets.py [--output data/synthetic_queries.jsonl] [--max-per-source 50]

Datasets used (all permissively licensed):
    - CoSQA (MIT): 20k query/code/label triples — reranker calibration
    - SO Questions (Apache 2.0): 3.9M SO titles — realistic chat traffic
    - CoNaLa (CC-BY-SA): 594k raw+rewritten intent pairs — normalizer testing

All downloads are cached by HuggingFace hub (~/.cache/huggingface/).
"""

import argparse
import json
import os
import random
import re
import sys

# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

def classify_query(query: str, source: str) -> str:
    """Assign a query_class tag based on content heuristics."""
    q = query.lower().strip()
    # Error/exception queries (highest priority — discriminative surface cues)
    if any(w in q for w in ["error", "exception", "traceback", "segfault", "panic",
                             "typeerror", "valueerror", "nameerror", "keyerror",
                             "syntaxerror", "importerror", "attributeerror",
                             "failed", "crash", "bug", "broken", "not working"]):
        return "error_text"
    # Syntax-heavy (contains code-like tokens)
    if any(tok in q for tok in ["()", "[]", "{}", "->", "::", "=>", "&&", "||",
                                  "def ", "class ", "import ", "fn ", "func ",
                                  "struct ", "impl ", "__", ".get(", ".set(",
                                  "lambda", "async ", "await ", "yield"]):
        return "syntax_heavy"
    # Conceptual/design
    if any(w in q for w in ["design pattern", "architecture", "best practice",
                              "trade-off", "when should i", "difference between",
                              "pros and cons", "comparison", "why does", "explain",
                              "what is the difference", "vs ", "versus"]):
        return "conceptual"
    # Direct how-to (check before short_ambiguous — short how-tos are still how-tos)
    if q.startswith(("how to", "how do i", "how can i", "what is the way to",
                     "how would", "what's the best way", "is there a way")):
        return "direct_how"
    # Paraphrase (CoNaLa rewritten intents)
    if source == "conala":
        return "paraphrase"
    # Action-oriented queries (imperative verbs)
    if q.startswith(("sort ", "filter ", "convert ", "parse ", "find ", "get ",
                     "create ", "delete ", "remove ", "add ", "check ", "list ",
                     "read ", "write ", "merge ", "split ", "count ", "replace ")):
        return "direct_how"
    # Short/ambiguous — last resort (< 5 words, very short)
    if len(q.split()) < 5:
        return "short_ambiguous"
    # Default: most remaining queries are task-oriented
    return "direct_how"


# ---------------------------------------------------------------------------
# Dataset loaders
# ---------------------------------------------------------------------------

def load_cosqa(max_n: int) -> list[dict]:
    """Load CoSQA query/code/label triples."""
    try:
        from datasets import load_dataset
        ds = load_dataset("gonglinyuan/CoSQA", split="train")
    except Exception as e:
        print(f"  [SKIP] CoSQA: {e}")
        return []

    samples = []
    indices = list(range(len(ds)))
    random.shuffle(indices)

    for i in indices[:max_n * 3]:  # oversample then filter
        row = ds[i]
        query = row.get("doc") or row.get("query") or ""
        code = row.get("code") or ""
        label = row.get("label", -1)
        if not query.strip() or not code.strip():
            continue
        samples.append({
            "query": query.strip(),
            "source": "cosqa",
            "query_class": classify_query(query, "cosqa"),
            "has_label": label in (0, 1),
            "relevance_label": int(label) if label in (0, 1) else None,
            "gold_code": code.strip()[:500],
            "idx": i,
        })
        if len(samples) >= max_n:
            break

    print(f"  CoSQA: {len(samples)} queries loaded")
    return samples


def load_so_questions(max_n: int) -> list[dict]:
    """Load Stack Overflow question titles (streaming — 3.9M rows, Apache 2.0)."""
    try:
        from datasets import load_dataset
        ds = load_dataset("pacovaldez/stackoverflow-questions", split="train", streaming=True)
    except Exception as e:
        print(f"  [SKIP] SO Questions: {e}")
        return []

    # Collect candidates, then sample
    candidates = []
    programming_keywords = {"python", "javascript", "rust", "go ", "golang", "c++", "typescript",
                            "function", "class", "error", "exception", "api", "async",
                            "array", "list", "dict", "string", "file", "json", "sql",
                            "loop", "sort", "parse", "import", "module", "package"}
    seen = 0
    for row in ds:
        seen += 1
        if seen > max_n * 50:  # cap streaming reads
            break
        title = row.get("title") or ""
        if not title.strip() or len(title) < 10:
            continue
        # Filter to programming-relevant questions
        t_lower = title.lower()
        if not any(kw in t_lower for kw in programming_keywords):
            continue
        candidates.append(title.strip())
        if len(candidates) >= max_n * 5:
            break

    random.shuffle(candidates)
    samples = []
    for title in candidates[:max_n]:
        samples.append({
            "query": title,
            "source": "so_questions",
            "query_class": classify_query(title, "so_questions"),
            "has_label": False,
            "relevance_label": None,
            "gold_code": None,
            "idx": len(samples),
        })

    print(f"  SO Questions: {len(samples)} queries loaded (from {seen} streamed)")
    return samples


def load_conala(max_n: int) -> list[dict]:
    """Load CoNaLa raw+rewritten intent pairs."""
    try:
        from datasets import load_dataset
        ds = load_dataset("codeparrot/conala-mined-curated", split="train")
    except Exception as e:
        print(f"  [SKIP] CoNaLa: {e}")
        return []

    # Pre-filter high-confidence rows, then sample
    candidates = []
    for i in range(len(ds)):
        row = ds[i]
        intent = row.get("intent") or ""
        rewritten = row.get("rewritten_intent") or ""
        snippet = row.get("snippet") or ""
        prob = float(row.get("prob", 0))
        if not intent.strip() or not snippet.strip():
            continue
        if prob < 0.7:
            continue
        candidates.append((i, intent.strip(), rewritten.strip() if rewritten else None,
                           snippet.strip()[:500]))
        if len(candidates) >= max_n * 10:
            break

    random.shuffle(candidates)
    samples = []
    for i, intent, rewritten, snippet in candidates[:max_n]:
        samples.append({
            "query": intent,
            "source": "conala",
            "query_class": classify_query(intent, "conala"),
            "has_label": False,
            "relevance_label": None,
            "gold_code": snippet,
            "idx": i,
            "rewritten_intent": rewritten,
        })

    print(f"  CoNaLa: {len(samples)} queries loaded (from {len(candidates)} candidates)")
    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bootstrap public datasets for synthetic traffic")
    parser.add_argument("--output", default="data/synthetic_queries.jsonl",
                        help="Output JSONL path (default: data/synthetic_queries.jsonl)")
    parser.add_argument("--max-per-source", type=int, default=50,
                        help="Max queries per dataset source (default: 50)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    random.seed(args.seed)
    n = args.max_per_source

    print(f"Bootstrapping datasets (max {n} per source, seed={args.seed})...")
    print()

    all_queries = []

    print("Loading CoSQA...")
    all_queries.extend(load_cosqa(n))

    print("Loading SO Questions...")
    all_queries.extend(load_so_questions(n))

    print("Loading CoNaLa...")
    all_queries.extend(load_conala(n))

    if not all_queries:
        print("\nERROR: No queries loaded. Install datasets: pip install datasets")
        sys.exit(1)

    # Shuffle final mix
    random.shuffle(all_queries)

    # Write output
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for q in all_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    # Summary
    print(f"\n{'='*60}")
    print(f"Total: {len(all_queries)} queries written to {args.output}")
    print()
    print("By source:")
    from collections import Counter
    src_counts = Counter(q["source"] for q in all_queries)
    for src, cnt in src_counts.most_common():
        print(f"  {src}: {cnt}")
    print()
    print("By query class:")
    cls_counts = Counter(q["query_class"] for q in all_queries)
    for cls, cnt in cls_counts.most_common():
        print(f"  {cls}: {cnt}")
    print()
    labeled = sum(1 for q in all_queries if q["has_label"])
    print(f"Labeled (for reranker ground truth): {labeled}")
    print(f"Unlabeled (for traffic + normalizer): {len(all_queries) - labeled}")


if __name__ == "__main__":
    main()
