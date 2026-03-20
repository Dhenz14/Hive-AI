"""
scripts/consolidate_and_promote.py

Master consolidation + RAG promotion pipeline.

1. Reads ALL training pair sources (deep_reasoning, thinking_pairs, new_pairs,
   reasoning_raw/opus, reasoning_raw/claude45, reasoning_raw/qwen35)
2. Normalizes to standard instruction/input/output format
3. Extracts code blocks, filters for ≥5 code lines
4. Deduplicates by content hash (prompt + code)
5. Promotes qualifying pairs to BookSections in Solved Examples book
6. Consolidates deep_reasoning batches into single file

Usage:
    python scripts/consolidate_and_promote.py [--db hiveai.db] [--dry-run]
"""

import sys
import os
import json
import hashlib
import re
import time
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Source readers — normalize every format to {instruction, code, language, output}
# ---------------------------------------------------------------------------

def read_standard_jsonl(path):
    """Read standard instruction/input/output JSONL."""
    if not os.path.exists(path):
        return []
    pairs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pairs.append({
                    "instruction": obj.get("instruction", ""),
                    "output": obj.get("output", ""),
                    "source_file": os.path.basename(path),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return pairs


def read_opus_raw(path):
    """Read reasoning_raw/opus.jsonl (problem/thinking/solution format)."""
    if not os.path.exists(path):
        return []
    pairs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                problem = obj.get("problem", "")
                thinking = obj.get("thinking", "")
                solution = obj.get("solution", "")
                # Reconstruct as instruction/output with <think> block
                output = f"<think>\n{thinking}\n</think>\n\n{solution}" if thinking else solution
                pairs.append({
                    "instruction": problem,
                    "output": output,
                    "source_file": "opus.jsonl",
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return pairs


def read_claude45_raw(path):
    """Read reasoning_raw/claude45.jsonl (messages format)."""
    if not os.path.exists(path):
        return []
    pairs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                msgs = obj.get("messages", [])
                instruction = ""
                output = ""
                for m in msgs:
                    if m.get("role") == "user":
                        instruction = m.get("content", "")
                    elif m.get("role") == "assistant":
                        output = m.get("content", "")
                if instruction and output:
                    pairs.append({
                        "instruction": instruction,
                        "output": output,
                        "source_file": "claude45.jsonl",
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return pairs


def read_qwen35_raw(path):
    """Read reasoning_raw/qwen35.jsonl (conversation format)."""
    if not os.path.exists(path):
        return []
    pairs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                instruction = obj.get("input", "")
                output = obj.get("output", "")
                if instruction and output:
                    pairs.append({
                        "instruction": instruction,
                        "output": output,
                        "source_file": "qwen35.jsonl",
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return pairs


# ---------------------------------------------------------------------------
# Code extraction and quality filtering
# ---------------------------------------------------------------------------

def extract_code_blocks(text):
    """Extract fenced code blocks from text. Returns list of (language, code)."""
    pattern = r'```(\w*)\n(.*?)```'
    return re.findall(pattern, text, re.DOTALL)


def detect_language(code_blocks, instruction=""):
    """Detect primary language from code blocks and instruction text."""
    # From code fence language tags
    for lang, _ in code_blocks:
        if lang:
            lang_lower = lang.lower()
            lang_map = {
                "python": "python", "py": "python",
                "javascript": "javascript", "js": "javascript",
                "typescript": "typescript", "ts": "typescript",
                "cpp": "cpp", "c++": "cpp", "c": "cpp",
                "rust": "rust", "rs": "rust",
                "go": "go", "golang": "go",
                "java": "java",
                "sql": "sql",
                "bash": "bash", "sh": "bash",
            }
            if lang_lower in lang_map:
                return lang_map[lang_lower]

    # From instruction text
    inst_lower = instruction.lower()
    if "python" in inst_lower or "def " in inst_lower:
        return "python"
    if "javascript" in inst_lower or "node" in inst_lower or "react" in inst_lower:
        return "javascript"
    if "typescript" in inst_lower:
        return "typescript"
    if "c++" in inst_lower or "cpp" in inst_lower:
        return "cpp"
    if "rust" in inst_lower:
        return "rust"
    if " go " in inst_lower or "golang" in inst_lower or "goroutine" in inst_lower:
        return "go"

    # Heuristic from code content
    all_code = "\n".join(code for _, code in code_blocks)
    if "def " in all_code and "import " in all_code:
        return "python"
    if "func " in all_code and "package " in all_code:
        return "go"
    if "fn " in all_code and ("let " in all_code or "impl " in all_code):
        return "rust"
    if "#include" in all_code:
        return "cpp"
    if "function " in all_code or "const " in all_code or "=>" in all_code:
        return "javascript"

    return "python"  # fallback


def count_code_lines(code_blocks):
    """Count non-empty code lines across all blocks."""
    total = 0
    for _, code in code_blocks:
        for line in code.strip().split("\n"):
            if line.strip():
                total += 1
    return total


def compute_hash(instruction, code_text):
    """Content hash for deduplication."""
    normalized = instruction.strip().lower() + "\n" + code_text.strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def extract_keywords(instruction, language):
    """Extract BM25 keywords."""
    terms = set()
    for word in instruction.lower().split():
        cleaned = re.sub(r'[^a-z0-9_]', '', word)
        if len(cleaned) > 2:
            terms.add(cleaned)
    terms.add(language.lower())
    return list(terms)[:20]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Consolidate + promote all training pairs")
    parser.add_argument("--db", default="hiveai.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gpu", action="store_true", help="Use GPU for embeddings (stop llama-server first)")
    parser.add_argument("--batch-embed", type=int, default=32, help="Embedding batch size (GPU only)")
    args = parser.parse_args()

    print("=" * 70)
    print("CONSOLIDATE + PROMOTE — Extract maximum RAG value from all pairs")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Phase 1: Read all sources
    # -----------------------------------------------------------------------
    print("\n[Phase 1] Reading all pair sources...")

    import glob
    all_pairs = []

    # Deep reasoning batches
    batch_files = sorted(glob.glob("loras/training_data/deep_reasoning_batch*.jsonl"))
    for bf in batch_files:
        pairs = read_standard_jsonl(bf)
        all_pairs.extend(pairs)
    print(f"  deep_reasoning_batches: {sum(len(read_standard_jsonl(f)) for f in batch_files)} pairs from {len(batch_files)} files")

    # Thinking pairs (master)
    tp = read_standard_jsonl("datasets/thinking_pairs.jsonl")
    all_pairs.extend(tp)
    print(f"  thinking_pairs.jsonl: {len(tp)} pairs")

    # New pairs (domain-balanced)
    np_ = read_standard_jsonl("loras/training_data/new_pairs_merged_512.jsonl")
    all_pairs.extend(np_)
    print(f"  new_pairs_merged_512.jsonl: {len(np_)} pairs")

    # Versioned training datasets (golden chain v1-v8)
    version_files = sorted(glob.glob("loras/training_data/v[0-9]*.jsonl"))
    for vf in version_files:
        vp = read_standard_jsonl(vf)
        all_pairs.extend(vp)
    version_total = sum(len(read_standard_jsonl(f)) for f in version_files)
    print(f"  versioned (v1-v8): {version_total} pairs from {len(version_files)} files")

    # Auto-improve files (sample best — too many to bulk promote)
    # Skipped: 663 auto_improve files (~660K pairs) — not hand-curated

    # Reasoning raw sources
    opus = read_opus_raw("loras/training_data/reasoning_raw/opus.jsonl")
    all_pairs.extend(opus)
    print(f"  reasoning_raw/opus.jsonl: {len(opus)} pairs")

    claude45 = read_claude45_raw("loras/training_data/reasoning_raw/claude45.jsonl")
    all_pairs.extend(claude45)
    print(f"  reasoning_raw/claude45.jsonl: {len(claude45)} pairs")

    qwen35 = read_qwen35_raw("loras/training_data/reasoning_raw/qwen35.jsonl")
    all_pairs.extend(qwen35)
    print(f"  reasoning_raw/qwen35.jsonl: {len(qwen35)} pairs")

    print(f"\n  TOTAL raw pairs: {len(all_pairs)}")

    # -----------------------------------------------------------------------
    # Phase 2: Filter for RAG-promotable pairs (must have real code)
    # -----------------------------------------------------------------------
    print("\n[Phase 2] Filtering for code-bearing pairs...")

    promotable = []
    rejected_no_code = 0
    rejected_short_code = 0
    rejected_no_instruction = 0

    for pair in all_pairs:
        instruction = pair["instruction"].strip()
        output = pair["output"].strip()

        if not instruction or len(instruction) < 10:
            rejected_no_instruction += 1
            continue

        code_blocks = extract_code_blocks(output)

        # Also try to find inline code (no fences but has function definitions)
        if not code_blocks:
            # Check if output has unfenced but clearly structured code
            if "def " in output or "func " in output or "fn " in output or "class " in output:
                # Treat entire output (minus think block) as code
                clean_output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL).strip()
                if clean_output and len(clean_output.split("\n")) >= 5:
                    code_blocks = [("", clean_output)]

        if not code_blocks:
            rejected_no_code += 1
            continue

        code_lines = count_code_lines(code_blocks)
        if code_lines < 5:
            rejected_short_code += 1
            continue

        language = detect_language(code_blocks, instruction)
        code_text = "\n\n".join(code for _, code in code_blocks)

        promotable.append({
            "instruction": instruction,
            "output": output,
            "code_blocks": code_blocks,
            "code_text": code_text,
            "code_lines": code_lines,
            "language": language,
            "source_file": pair["source_file"],
            "content_hash": compute_hash(instruction, code_text),
        })

    print(f"  Promotable (≥5 code lines): {len(promotable)}")
    print(f"  Rejected — no instruction: {rejected_no_instruction}")
    print(f"  Rejected — no code blocks: {rejected_no_code}")
    print(f"  Rejected — <5 code lines: {rejected_short_code}")

    # -----------------------------------------------------------------------
    # Phase 3: Deduplicate
    # -----------------------------------------------------------------------
    print("\n[Phase 3] Deduplicating...")

    seen_hashes = set()
    unique = []
    dupes = 0

    for p in promotable:
        if p["content_hash"] in seen_hashes:
            dupes += 1
            continue
        seen_hashes.add(p["content_hash"])
        unique.append(p)

    print(f"  Unique pairs: {len(unique)} (removed {dupes} duplicates)")

    # Language distribution
    lang_dist = defaultdict(int)
    source_dist = defaultdict(int)
    for p in unique:
        lang_dist[p["language"]] += 1
        source_dist[p["source_file"]] += 1

    print(f"\n  Language distribution:")
    for lang, count in sorted(lang_dist.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {count}")

    print(f"\n  Source distribution (top 10):")
    for src, count in sorted(source_dist.items(), key=lambda x: -x[1])[:10]:
        print(f"    {src}: {count}")

    # -----------------------------------------------------------------------
    # Phase 4: Consolidate deep_reasoning batches
    # -----------------------------------------------------------------------
    print("\n[Phase 4] Consolidating deep_reasoning batches...")
    consolidated_path = "loras/training_data/deep_reasoning_all.jsonl"
    batch_count = 0
    with open(consolidated_path, "w", encoding="utf-8") as out:
        for bf in batch_files:
            with open(bf, encoding="utf-8", errors="replace") as inp:
                for line in inp:
                    line = line.strip()
                    if line:
                        out.write(line + "\n")
                        batch_count += 1
    print(f"  Consolidated {batch_count} pairs from {len(batch_files)} files → {consolidated_path}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would promote {len(unique)} pairs to BookSections.")
        print("Run without --dry-run to insert into DB.")
        return

    # -----------------------------------------------------------------------
    # Phase 5: Promote to BookSections
    # -----------------------------------------------------------------------
    print(f"\n[Phase 5] Promoting {len(unique)} pairs to BookSections...")

    # Load embedding model
    if args.gpu:
        print("  Loading BGE-M3 on GPU (batch mode)...")
        from sentence_transformers import SentenceTransformer
        embed_model = SentenceTransformer("BAAI/bge-m3")
        embed_model = embed_model.to("cuda")
        _test = embed_model.encode(["test"])[0]
        print(f"  GPU embedding ready (dim={len(_test)})")

        def embed_batch(texts):
            return embed_model.encode(texts, batch_size=args.batch_embed, show_progress_bar=False).tolist()

        def embed_single(text):
            return embed_model.encode([text])[0].tolist()
    else:
        print("  Loading embedding model (CPU — slow)...")
        from hiveai.llm.client import embed_text
        _test = embed_text("test")
        print(f"  Embedding model loaded (dim={len(_test)})")

        def embed_batch(texts):
            return [embed_text(t) for t in texts]

        def embed_single(text):
            return embed_text(text)

    import sqlite3
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # Get book
    book = conn.execute(
        "SELECT id FROM golden_books WHERE title = ?",
        ("Solved Examples :: Verified Code",)
    ).fetchone()
    if not book:
        raise RuntimeError("Solved Examples book not found")
    book_id = book["id"]

    # Load existing hashes to skip already-promoted
    existing_hashes = set()
    for r in conn.execute(
        "SELECT keywords_json FROM book_sections WHERE book_id = ?", (book_id,)
    ).fetchall():
        try:
            kw = json.loads(r["keywords_json"])
            if kw.get("content_hash"):
                existing_hashes.add(kw["content_hash"])
        except (json.JSONDecodeError, TypeError):
            pass

    pre_existing = conn.execute(
        "SELECT COUNT(*) as c FROM book_sections WHERE book_id = ?", (book_id,)
    ).fetchone()["c"]
    print(f"  Existing sections in Solved Examples: {pre_existing}")
    print(f"  Existing content hashes: {len(existing_hashes)}")

    # Pre-filter and build all records before embedding
    to_embed = []
    skipped_dup = 0
    skipped_err = 0

    for p in unique:
        if p["content_hash"] in existing_hashes:
            skipped_dup += 1
            continue

        instruction = p["instruction"]
        language = p["language"]
        code_lines = p["code_lines"]

        code_body = p["code_text"].strip()
        header = f"Solved: {instruction[:200]}"
        content = f"""Problem:
{instruction}

Verified solution ({language}):
```{language}
{code_body}
```

Quality: 0.88 | Lines: {code_lines} | Source: {p['source_file']}"""

        # Cap content at ~4000 chars to avoid embedding bloat
        if len(content) > 4000:
            max_code = 3500 - len(instruction) - 100
            if max_code > 200:
                code_body_trunc = code_body[:max_code] + "\n// ... (truncated)"
                content = f"""Problem:
{instruction}

Verified solution ({language}):
```{language}
{code_body_trunc}
```

Quality: 0.88 | Lines: {code_lines} | Source: {p['source_file']}"""
            else:
                skipped_err += 1
                continue

        keywords = extract_keywords(instruction, language)
        embed_text_str = f"{instruction} {header}"

        to_embed.append({
            "header": header,
            "content": content,
            "keywords": keywords,
            "embed_text": embed_text_str,
            "language": language,
            "content_hash": p["content_hash"],
            "source_file": p["source_file"],
            "code_lines": code_lines,
        })

    print(f"  To embed: {len(to_embed)} (skipped {skipped_dup} dups, {skipped_err} errors)")

    # Batch embed
    if args.gpu and to_embed:
        print(f"  Batch embedding {len(to_embed)} texts on GPU...")
        all_texts = [r["embed_text"] for r in to_embed]
        all_embeddings = embed_batch(all_texts)
        for rec, emb in zip(to_embed, all_embeddings):
            rec["embedding"] = emb
        print(f"  Embedding complete.")
    else:
        # CPU: embed one at a time (slow but functional)
        for i, rec in enumerate(to_embed):
            try:
                rec["embedding"] = embed_single(rec["embed_text"])
            except Exception as e:
                rec["embedding"] = None
                skipped_err += 1
                if skipped_err <= 3:
                    print(f"  Embedding error: {e}")
            if (i + 1) % 50 == 0:
                print(f"    ... embedded {i+1}/{len(to_embed)}")

    # Insert into DB
    inserted = 0
    batch_size = 50

    for i, rec in enumerate(to_embed):
        if rec.get("embedding") is None:
            continue

        metadata = {
            "keywords": rec["keywords"],
            "source_type": "solved_example",
            "training_pair_id": -(inserted + 1000),
            "content_hash": rec["content_hash"],
            "verification_status": "distilled",
            "language": rec["language"],
            "quality_score": 0.88,
            "source_file": rec["source_file"],
            "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        conn.execute(
            """INSERT INTO book_sections
               (book_id, header, content, token_count, embedding_json, keywords_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (book_id, rec["header"], rec["content"], len(rec["content"].split()),
             json.dumps(rec["embedding"]), json.dumps(metadata)),
        )
        existing_hashes.add(rec["content_hash"])
        inserted += 1

        if inserted % batch_size == 0:
            conn.commit()
            print(f"    ... {inserted} inserted ({i+1}/{len(to_embed)} processed)")

    conn.commit()

    # Update book stats
    total = conn.execute(
        "SELECT COUNT(*) as c FROM book_sections WHERE book_id = ?", (book_id,)
    ).fetchone()["c"]
    total_words = conn.execute(
        "SELECT SUM(token_count) as s FROM book_sections WHERE book_id = ?", (book_id,)
    ).fetchone()["s"] or 0
    conn.execute(
        "UPDATE golden_books SET source_count = ?, word_count = ? WHERE id = ?",
        (total, total_words, book_id)
    )
    conn.commit()
    conn.close()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(f"CONSOLIDATION + PROMOTION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Sources processed: deep_reasoning, thinking, new_pairs, v1-v8, opus, claude45, qwen35")
    print(f"  Total raw pairs: {len(all_pairs)}")
    print(f"  Passed code filter: {len(promotable)}")
    print(f"  After dedup: {len(unique)}")
    print(f"  Already in DB (skipped): {skipped_dup}")
    print(f"  Embedding errors (skipped): {skipped_err}")
    print(f"  NEW sections inserted: {inserted}")
    print(f"  Total Solved Examples sections: {total}")
    print(f"  Deep reasoning consolidated: {batch_count} pairs → {consolidated_path}")


if __name__ == "__main__":
    main()
