#!/usr/bin/env python3
"""
P0 Offline Topic-Gate Evaluator

Computes candidate domain-discrimination signals from existing section embeddings
and evaluates them against a labeled query set. Produces:

  1. Per-signal distance distributions by label (in_domain / near_domain / off_domain)
  2. Threshold sweep with false-accept / false-reject counts
  3. Confusion matrices at candidate operating points
  4. Recommendation for best gating signal

Signals compared:
  A. Global centroid distance (mean of ALL section embeddings)
  B. Nearest per-book centroid distance (mean per golden book)
  C. Trimmed global centroid (exclude outlier sections by IQR)
  D. Nearest-section distance (min distance to any section — upper bound on discrimination)

All distances are cosine distance (1 - cosine_similarity).
Embeddings are L2-normalized (BGE-M3 with normalize_embeddings=True),
so cosine_distance = 1 - dot_product.

Usage:
    python scripts/eval_topic_gate.py [--db PATH] [--queries PATH] [--out DIR]

Runs on CPU only. No LLM calls. No chat-path integration.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

import numpy as np


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def load_section_embeddings(db_path: str):
    """Load all section embeddings from SQLite, grouped by book.

    Returns:
        sections: list of dicts with id, book_id, book_title, header, embedding (np.array)
        books: dict of book_id -> book_title
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load books
    books = {}
    for row in conn.execute("SELECT id, title FROM golden_books WHERE status = 'published'"):
        books[row["id"]] = row["title"]

    # Load sections with embeddings
    sections = []
    skipped = 0
    cursor = conn.execute(
        "SELECT id, book_id, header, embedding_json, keywords_json "
        "FROM book_sections WHERE embedding_json IS NOT NULL"
    )
    for row in cursor:
        try:
            emb = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
            if emb.shape != (1024,):
                skipped += 1
                continue
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue

        # Parse source_type from keywords_json
        source_type = None
        kw = row["keywords_json"]
        if kw:
            try:
                kw_data = json.loads(kw)
                if isinstance(kw_data, dict):
                    source_type = kw_data.get("source_type")
            except json.JSONDecodeError:
                pass

        book_id = row["book_id"]
        sections.append({
            "id": row["id"],
            "book_id": book_id,
            "book_title": books.get(book_id, f"unknown-{book_id}"),
            "header": row["header"],
            "source_type": source_type,
            "embedding": emb,
        })

    conn.close()

    if skipped:
        print(f"  Skipped {skipped} sections with bad embeddings")

    return sections, books


def embed_queries(queries: list[dict]) -> list[dict]:
    """Embed query strings using BGE-M3 (same model as indexing).

    Returns queries with 'embedding' field added.
    """
    from sentence_transformers import SentenceTransformer

    print("Loading BGE-M3 embedding model (CPU)...")
    model = SentenceTransformer("BAAI/bge-m3", device="cpu")

    texts = [q["query"] for q in queries]
    print(f"Embedding {len(texts)} queries...")
    t0 = time.time()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    print(f"  Done in {time.time() - t0:.1f}s")

    for q, emb in zip(queries, embeddings):
        q["embedding"] = np.array(emb, dtype=np.float32)

    return queries


# ---------------------------------------------------------------------------
# Centroid computation
# ---------------------------------------------------------------------------

def compute_global_centroid(sections):
    """Mean of all section embeddings, re-normalized."""
    all_emb = np.stack([s["embedding"] for s in sections])
    centroid = all_emb.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid /= norm
    return centroid


def compute_trimmed_global_centroid(sections, iqr_factor=1.5):
    """Trimmed mean: exclude sections whose distance to raw centroid
    is beyond Q3 + iqr_factor * IQR. Re-normalize."""
    raw_centroid = compute_global_centroid(sections)

    # Compute distances to raw centroid
    all_emb = np.stack([s["embedding"] for s in sections])
    dots = all_emb @ raw_centroid  # cosine similarity (normalized)
    distances = 1.0 - dots

    q1, q3 = np.percentile(distances, [25, 75])
    iqr = q3 - q1
    upper = q3 + iqr_factor * iqr

    mask = distances <= upper
    trimmed_emb = all_emb[mask]
    n_excluded = (~mask).sum()

    if len(trimmed_emb) < 10:
        print(f"  WARNING: trimming would leave only {len(trimmed_emb)} sections, using raw centroid")
        return raw_centroid, 0

    centroid = trimmed_emb.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid /= norm
    return centroid, int(n_excluded)


def compute_per_book_centroids(sections, books, min_sections=3):
    """Per-book centroid = mean of that book's section embeddings, re-normalized.

    Books with < min_sections are excluded (unstable centroids).
    """
    by_book = defaultdict(list)
    for s in sections:
        by_book[s["book_id"]].append(s["embedding"])

    centroids = {}
    excluded_books = []
    for book_id, embs in by_book.items():
        if len(embs) < min_sections:
            excluded_books.append((book_id, books.get(book_id, "?"), len(embs)))
            continue
        arr = np.stack(embs)
        c = arr.mean(axis=0)
        norm = np.linalg.norm(c)
        if norm > 0:
            c /= norm
        centroids[book_id] = {
            "centroid": c,
            "title": books.get(book_id, f"unknown-{book_id}"),
            "n_sections": len(embs),
        }

    return centroids, excluded_books


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def cosine_distance(a, b):
    """Cosine distance between two L2-normalized vectors = 1 - dot product."""
    return 1.0 - float(np.dot(a, b))


def compute_signals(query_emb, global_centroid, trimmed_centroid,
                    book_centroids, section_embeddings):
    """Compute all candidate topic-gate signals for one query.

    Returns dict with:
        global_centroid_dist: cosine distance to global centroid
        trimmed_centroid_dist: cosine distance to trimmed global centroid
        nearest_book_centroid_dist: min cosine distance to any book centroid
        nearest_book_title: which book's centroid was closest
        nearest_section_dist: min cosine distance to any section (oracle-like)
        mean_top5_section_dist: mean distance to 5 nearest sections
    """
    # Global centroid
    global_dist = cosine_distance(query_emb, global_centroid)

    # Trimmed global centroid
    trimmed_dist = cosine_distance(query_emb, trimmed_centroid)

    # Nearest per-book centroid
    best_book_dist = float("inf")
    best_book_title = None
    for book_id, info in book_centroids.items():
        d = cosine_distance(query_emb, info["centroid"])
        if d < best_book_dist:
            best_book_dist = d
            best_book_title = info["title"]

    # Nearest section (upper bound — expensive but informative)
    # Use vectorized dot product for speed
    dots = section_embeddings @ query_emb  # (N,) cosine similarities
    section_dists = 1.0 - dots
    nearest_idx = np.argmin(section_dists)
    nearest_section_dist = float(section_dists[nearest_idx])

    # Mean of top-5 nearest sections
    top5_idx = np.argpartition(section_dists, min(5, len(section_dists) - 1))[:5]
    mean_top5 = float(section_dists[top5_idx].mean())

    return {
        "global_centroid_dist": round(global_dist, 6),
        "trimmed_centroid_dist": round(trimmed_dist, 6),
        "nearest_book_centroid_dist": round(best_book_dist, 6),
        "nearest_book_title": best_book_title,
        "nearest_section_dist": round(nearest_section_dist, 6),
        "mean_top5_section_dist": round(mean_top5, 6),
    }


# ---------------------------------------------------------------------------
# Threshold sweep & evaluation
# ---------------------------------------------------------------------------

def threshold_sweep(results, signal_key, thresholds,
                    positive_labels=("in_domain",),
                    reject_labels=("off_domain",)):
    """Sweep a threshold range for a given signal.

    Convention: distance < threshold → ACCEPT (in-domain), else → REJECT.

    Returns list of dicts per threshold:
        threshold, true_accept, false_reject, true_reject, false_accept,
        precision, recall, f1, accuracy
    """
    rows = []
    for t in thresholds:
        ta = fr = tr = fa = 0
        for r in results:
            dist = r["signals"][signal_key]
            label = r["label"]
            predicted_accept = dist < t

            if label in positive_labels:
                if predicted_accept:
                    ta += 1
                else:
                    fr += 1
            elif label in reject_labels:
                if predicted_accept:
                    fa += 1
                else:
                    tr += 1
            else:
                # near_domain — count but don't penalize either way
                pass

        total = ta + fr + tr + fa
        precision = ta / (ta + fa) if (ta + fa) > 0 else 0.0
        recall = ta / (ta + fr) if (ta + fr) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (ta + tr) / total if total > 0 else 0.0

        rows.append({
            "threshold": round(t, 4),
            "true_accept": ta,
            "false_reject": fr,
            "true_reject": tr,
            "false_accept": fa,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
        })

    return rows


def find_best_operating_point(sweep_rows):
    """Find the threshold that maximizes F1, with tiebreak on fewer false rejects."""
    best = max(sweep_rows, key=lambda r: (r["f1"], -r["false_reject"]))
    return best


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def print_distribution_table(results, signal_key, signal_name):
    """Print per-label statistics for a signal."""
    by_label = defaultdict(list)
    for r in results:
        by_label[r["label"]].append(r["signals"][signal_key])

    print(f"\n{'='*70}")
    print(f"Signal: {signal_name} ({signal_key})")
    print(f"{'='*70}")
    print(f"{'Label':<15} {'N':>4} {'Min':>8} {'Q25':>8} {'Median':>8} {'Q75':>8} {'Max':>8} {'Mean':>8} {'Std':>8}")
    print("-" * 85)

    for label in ["in_domain", "near_domain", "off_domain"]:
        vals = by_label.get(label, [])
        if not vals:
            continue
        arr = np.array(vals)
        q25, med, q75 = np.percentile(arr, [25, 50, 75])
        print(f"{label:<15} {len(arr):>4} {arr.min():>8.4f} {q25:>8.4f} {med:>8.4f} "
              f"{q75:>8.4f} {arr.max():>8.4f} {arr.mean():>8.4f} {arr.std():>8.4f}")

    # Separation metric: gap between in_domain max and off_domain min
    in_vals = by_label.get("in_domain", [])
    off_vals = by_label.get("off_domain", [])
    if in_vals and off_vals:
        in_max = max(in_vals)
        off_min = min(off_vals)
        gap = off_min - in_max
        overlap_pct = sum(1 for v in in_vals if v >= off_min) / len(in_vals) * 100 if off_min <= in_max else 0
        print(f"\n  Separation gap (off_min - in_max): {gap:+.4f}")
        print(f"  In-domain queries above off-domain min: {overlap_pct:.1f}%")
        if gap > 0:
            print(f"  -> CLEAN SEPARATION possible in [{in_max:.4f}, {off_min:.4f}]")
        else:
            print(f"  -> OVERLAP: {abs(gap):.4f} distance units, {overlap_pct:.1f}% of in-domain queries in overlap zone")


def print_sweep_table(sweep_rows, signal_name):
    """Print threshold sweep results."""
    print(f"\n--- Threshold Sweep: {signal_name} ---")
    print(f"{'Thresh':>8} {'TA':>4} {'FR':>4} {'TR':>4} {'FA':>4} {'Prec':>7} {'Recall':>7} {'F1':>7} {'Acc':>7}")
    print("-" * 68)
    for r in sweep_rows:
        print(f"{r['threshold']:>8.4f} {r['true_accept']:>4} {r['false_reject']:>4} "
              f"{r['true_reject']:>4} {r['false_accept']:>4} "
              f"{r['precision']:>7.3f} {r['recall']:>7.3f} {r['f1']:>7.3f} {r['accuracy']:>7.3f}")


def print_confusion_matrix(sweep_row, signal_name, threshold):
    """Print a confusion matrix for a specific operating point."""
    ta, fr, tr, fa = sweep_row["true_accept"], sweep_row["false_reject"], \
                     sweep_row["true_reject"], sweep_row["false_accept"]
    print(f"\n  Confusion Matrix @ {signal_name} < {threshold:.4f}")
    print(f"  {'':>20} {'Predicted ACCEPT':>18} {'Predicted REJECT':>18}")
    print(f"  {'Actual IN-DOMAIN':<20} {ta:>18} {fr:>18}")
    print(f"  {'Actual OFF-DOMAIN':<20} {fa:>18} {tr:>18}")
    print(f"  Precision={sweep_row['precision']:.3f}  Recall={sweep_row['recall']:.3f}  "
          f"F1={sweep_row['f1']:.3f}  Accuracy={sweep_row['accuracy']:.3f}")


def print_near_domain_analysis(results, signal_key, threshold):
    """Show where near-domain queries fall relative to a threshold."""
    near = [(r["id"], r["query"][:60], r["signals"][signal_key]) for r in results if r["label"] == "near_domain"]
    near.sort(key=lambda x: x[2])

    accepted = [n for n in near if n[2] < threshold]
    rejected = [n for n in near if n[2] >= threshold]

    print(f"\n  Near-domain @ threshold {threshold:.4f}: {len(accepted)} accepted, {len(rejected)} rejected")
    if accepted:
        print("  Accepted:")
        for nid, q, d in accepted:
            print(f"    {nid:<10} d={d:.4f}  {q}")
    if rejected:
        print("  Rejected:")
        for nid, q, d in rejected:
            print(f"    {nid:<10} d={d:.4f}  {q}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="P0 Offline Topic-Gate Evaluator")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--queries", default=None, help="Labeled query set JSON path")
    parser.add_argument("--out", default=None, help="Output directory for results")
    args = parser.parse_args()

    # Resolve paths
    project_root = Path(__file__).resolve().parent.parent
    db_path = args.db or str(project_root / "hiveai.db")
    queries_path = args.queries or str(project_root / "scripts" / "topic_gate_labeled_queries.json")
    out_dir = Path(args.out) if args.out else project_root / "scripts" / "topic_gate_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        print("  Set --db or ensure hiveai.db exists in project root")
        sys.exit(1)

    # --- Step 1: Load section embeddings ---
    print(f"\n[1/5] Loading section embeddings from {db_path}...")
    sections, books = load_section_embeddings(db_path)
    print(f"  Loaded {len(sections)} sections from {len(books)} books")

    # Filter out critique patterns (embedding=NULL in DB, but double-check)
    sections = [s for s in sections if s["source_type"] != "critique_pattern"]
    print(f"  After filtering critique patterns: {len(sections)} sections")

    # Summary by book
    by_book = defaultdict(int)
    for s in sections:
        by_book[s["book_title"]] += 1
    print("\n  Sections per book:")
    for title, count in sorted(by_book.items(), key=lambda x: -x[1]):
        print(f"    {count:>4}  {title[:70]}")

    # Pre-stack all embeddings for vectorized nearest-section computation
    section_embeddings = np.stack([s["embedding"] for s in sections])  # (N, 1024)

    # --- Step 2: Compute centroids ---
    print(f"\n[2/5] Computing centroids...")

    global_centroid = compute_global_centroid(sections)
    print(f"  Global centroid computed from {len(sections)} sections")

    trimmed_centroid, n_excluded = compute_trimmed_global_centroid(sections)
    print(f"  Trimmed global centroid: excluded {n_excluded} outlier sections")

    book_centroids, excluded_books = compute_per_book_centroids(sections, books, min_sections=3)
    print(f"  Per-book centroids: {len(book_centroids)} books (excluded {len(excluded_books)} with <3 sections)")
    if excluded_books:
        for bid, title, n in excluded_books:
            print(f"    Excluded: {title[:50]} ({n} sections)")

    # --- Step 3: Load and embed queries ---
    print(f"\n[3/5] Loading labeled queries from {queries_path}...")
    with open(queries_path) as f:
        query_data = json.load(f)
    queries = query_data["queries"]
    print(f"  Loaded {len(queries)} queries")

    label_counts = defaultdict(int)
    for q in queries:
        label_counts[q["label"]] += 1
    for label, count in sorted(label_counts.items()):
        print(f"    {label}: {count}")

    queries = embed_queries(queries)

    # --- Step 4: Compute all signals ---
    print(f"\n[4/5] Computing signals for {len(queries)} queries...")
    results = []
    for q in queries:
        signals = compute_signals(
            q["embedding"], global_centroid, trimmed_centroid,
            book_centroids, section_embeddings
        )
        results.append({
            "id": q["id"],
            "query": q["query"],
            "label": q["label"],
            "source": q.get("source", "unknown"),
            "signals": signals,
        })

    # --- Step 5: Analysis ---
    print(f"\n[5/5] Analysis...")

    signal_configs = [
        ("global_centroid_dist", "Global Centroid Distance"),
        ("trimmed_centroid_dist", "Trimmed Global Centroid Distance"),
        ("nearest_book_centroid_dist", "Nearest Per-Book Centroid Distance"),
        ("nearest_section_dist", "Nearest Section Distance (oracle)"),
        ("mean_top5_section_dist", "Mean Top-5 Section Distance"),
    ]

    # Threshold range: 0.10 to 0.90 in steps of 0.02
    thresholds = [round(0.10 + i * 0.02, 4) for i in range(41)]

    all_sweeps = {}
    best_points = {}

    for signal_key, signal_name in signal_configs:
        # Distribution table
        print_distribution_table(results, signal_key, signal_name)

        # Threshold sweep
        sweep = threshold_sweep(results, signal_key, thresholds)
        all_sweeps[signal_key] = sweep
        print_sweep_table(sweep, signal_name)

        # Best operating point
        best = find_best_operating_point(sweep)
        best_points[signal_key] = best
        print(f"\n  BEST operating point: threshold={best['threshold']:.4f}  "
              f"F1={best['f1']:.3f}  FA={best['false_accept']}  FR={best['false_reject']}")
        print_confusion_matrix(best, signal_name, best["threshold"])

        # Near-domain breakdown at best threshold
        print_near_domain_analysis(results, signal_key, best["threshold"])

    # --- Summary comparison ---
    print(f"\n{'='*70}")
    print("SIGNAL COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"{'Signal':<35} {'Best Thresh':>12} {'F1':>6} {'FA':>4} {'FR':>4} {'Acc':>7}")
    print("-" * 72)
    for signal_key, signal_name in signal_configs:
        bp = best_points[signal_key]
        print(f"{signal_name:<35} {bp['threshold']:>12.4f} {bp['f1']:>6.3f} "
              f"{bp['false_accept']:>4} {bp['false_reject']:>4} {bp['accuracy']:>7.3f}")

    # --- Save results ---
    output = {
        "meta": {
            "db_path": db_path,
            "queries_path": queries_path,
            "n_sections": len(sections),
            "n_books": len(books),
            "n_book_centroids": len(book_centroids),
            "n_trimmed_excluded": n_excluded,
            "n_queries": len(queries),
            "label_counts": dict(label_counts),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "per_query_results": [
            {k: v for k, v in r.items() if k != "embedding"}
            for r in results
        ],
        "signal_sweeps": all_sweeps,
        "best_operating_points": best_points,
        "signal_configs": [{"key": k, "name": n} for k, n in signal_configs],
    }

    out_file = out_dir / "topic_gate_eval_results.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_file}")

    # Also save a concise summary
    summary_file = out_dir / "topic_gate_eval_summary.txt"
    with open(summary_file, "w") as f:
        f.write("P0 Topic-Gate Offline Evaluation Summary\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Sections: {len(sections)}, Books: {len(books)}, Queries: {len(queries)}\n")
        f.write(f"Labels: {dict(label_counts)}\n\n")

        f.write("Signal Comparison:\n")
        f.write(f"{'Signal':<35} {'Thresh':>8} {'F1':>6} {'FA':>4} {'FR':>4}\n")
        f.write("-" * 60 + "\n")
        for signal_key, signal_name in signal_configs:
            bp = best_points[signal_key]
            f.write(f"{signal_name:<35} {bp['threshold']:>8.4f} {bp['f1']:>6.3f} "
                    f"{bp['false_accept']:>4} {bp['false_reject']:>4}\n")

        # Recommendation
        best_signal = max(best_points.items(), key=lambda x: (x[1]["f1"], -x[1]["false_reject"]))
        f.write(f"\nRecommended signal: {best_signal[0]}\n")
        f.write(f"  Threshold: {best_signal[1]['threshold']:.4f}\n")
        f.write(f"  F1: {best_signal[1]['f1']:.3f}\n")
        f.write(f"  False accepts: {best_signal[1]['false_accept']}\n")
        f.write(f"  False rejects: {best_signal[1]['false_reject']}\n")

    print(f"Summary saved to {summary_file}")

    print("\n" + "=" * 70)
    print("P0 EVALUATION COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Review distributions — is there a clean separation gap for any signal?")
    print("  2. Review false rejects — which in-domain queries would be wrongly blocked?")
    print("  3. Review near-domain behavior — are acceptable queries being rejected?")
    print("  4. If evidence is clean: design shadow-mode integration for chat.py")
    print("  5. If evidence is mixed: consider combining signals or adding keyword gate")


if __name__ == "__main__":
    main()
