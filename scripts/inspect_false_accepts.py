#!/usr/bin/env python3
"""
P1 Residual Failure Inspection

Inspects the false-accept and false-reject cases from P0 topic-gate evaluation.
For each case, retrieves:
  - Top-5 nearest sections (with headers, book titles, text snippets)
  - Distance metrics (nearest, mean-top-5, gap)
  - Cross-encoder reranker scores
  - Section metadata (source_type, keywords)

Usage:
    python scripts/inspect_false_accepts.py [--db PATH] [--results PATH]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

import numpy as np


def load_section_embeddings(db_path):
    """Load all sections with embeddings and content."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    books = {}
    for row in conn.execute("SELECT id, title FROM golden_books"):
        books[row["id"]] = row["title"]

    sections = []
    cursor = conn.execute(
        "SELECT id, book_id, header, content, embedding_json, keywords_json, token_count "
        "FROM book_sections WHERE embedding_json IS NOT NULL"
    )
    for row in cursor:
        try:
            emb = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
            if emb.shape != (1024,):
                continue
        except (json.JSONDecodeError, ValueError):
            continue

        source_type = None
        keywords = []
        kw_raw = row["keywords_json"]
        if kw_raw:
            try:
                kw_data = json.loads(kw_raw)
                if isinstance(kw_data, dict):
                    source_type = kw_data.get("source_type")
                    keywords = kw_data.get("keywords", [])
                elif isinstance(kw_data, list):
                    keywords = kw_data
            except json.JSONDecodeError:
                pass

        sections.append({
            "id": row["id"],
            "book_id": row["book_id"],
            "book_title": books.get(row["book_id"], f"unknown-{row['book_id']}"),
            "header": row["header"],
            "content": row["content"] or "",
            "token_count": row["token_count"],
            "source_type": source_type,
            "keywords": keywords,
            "embedding": emb,
        })

    conn.close()
    return sections, books


def embed_queries(queries):
    """Embed query strings using BGE-M3."""
    from sentence_transformers import SentenceTransformer
    print("Loading BGE-M3...")
    model = SentenceTransformer("BAAI/bge-m3", device="cpu")
    texts = [q["query"] for q in queries]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    for q, emb in zip(queries, embeddings):
        q["embedding"] = np.array(emb, dtype=np.float32)
    return queries, model


def compute_reranker_scores(query_text, section_texts, model=None):
    """Compute cross-encoder reranker scores for query-section pairs."""
    if model is None:
        from sentence_transformers import CrossEncoder
        print("Loading cross-encoder reranker...")
        model = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")

    pairs = [[query_text, text] for text in section_texts]
    scores = model.predict(pairs)
    return scores.tolist() if hasattr(scores, 'tolist') else list(scores)


def get_top_sections(query_emb, sections, section_embeddings, k=10):
    """Get top-k nearest sections for a query."""
    dots = section_embeddings @ query_emb
    dists = 1.0 - dots
    top_idx = np.argsort(dists)[:k]

    results = []
    for idx in top_idx:
        s = sections[idx]
        results.append({
            "rank": len(results) + 1,
            "section_id": s["id"],
            "book_title": s["book_title"],
            "header": s["header"],
            "content_snippet": s["content"][:300].replace("\n", " "),
            "content_length": len(s["content"]),
            "token_count": s["token_count"],
            "source_type": s["source_type"],
            "keywords": s["keywords"][:10] if s["keywords"] else [],
            "cosine_distance": round(float(dists[idx]), 6),
        })

    return results


def inspect_query(query, sections, section_embeddings, reranker_model):
    """Full inspection of one query against the corpus."""
    top_sections = get_top_sections(query["embedding"], sections, section_embeddings, k=10)

    # Compute reranker scores for top-10
    section_texts = []
    for ts in top_sections:
        # Find full content
        for s in sections:
            if s["id"] == ts["section_id"]:
                section_texts.append(s["content"][:1500])  # truncate for reranker
                break

    reranker_scores = compute_reranker_scores(query["query"], section_texts, reranker_model)
    for ts, score in zip(top_sections, reranker_scores):
        ts["reranker_score"] = round(float(score), 6)

    # Compute aggregate metrics
    dists = [ts["cosine_distance"] for ts in top_sections]
    nearest_dist = dists[0]
    mean_top5 = np.mean(dists[:5])
    mean_top10 = np.mean(dists[:10])
    gap_1_5 = dists[4] - dists[0] if len(dists) >= 5 else 0
    std_top5 = np.std(dists[:5])

    # Reranker aggregate
    rr_scores = [ts["reranker_score"] for ts in top_sections]
    rr_best = max(rr_scores)
    rr_mean_top5 = np.mean(sorted(rr_scores, reverse=True)[:5])

    return {
        "query_id": query["id"],
        "query_text": query["query"],
        "label": query["label"],
        "metrics": {
            "nearest_section_dist": round(float(nearest_dist), 6),
            "mean_top5_dist": round(float(mean_top5), 6),
            "mean_top10_dist": round(float(mean_top10), 6),
            "gap_rank1_rank5": round(float(gap_1_5), 6),
            "std_top5": round(float(std_top5), 6),
            "reranker_best": round(float(rr_best), 6),
            "reranker_mean_top5": round(float(rr_mean_top5), 6),
        },
        "top_sections": top_sections[:10],
    }


def print_inspection(result):
    """Pretty-print one inspection result."""
    m = result["metrics"]
    print(f"\n{'='*80}")
    print(f"Query: [{result['query_id']}] {result['query_text']}")
    print(f"Label: {result['label']}")
    print(f"{'='*80}")
    print(f"  nearest_section_dist: {m['nearest_section_dist']:.4f}")
    print(f"  mean_top5_dist:       {m['mean_top5_dist']:.4f}")
    print(f"  mean_top10_dist:      {m['mean_top10_dist']:.4f}")
    print(f"  gap (rank1→rank5):    {m['gap_rank1_rank5']:.4f}")
    print(f"  std top5:             {m['std_top5']:.4f}")
    print(f"  reranker best:        {m['reranker_best']:.4f}")
    print(f"  reranker mean top5:   {m['reranker_mean_top5']:.4f}")

    print(f"\n  Top-10 matched sections:")
    print(f"  {'Rk':>3} {'Dist':>7} {'Rerank':>8} {'Book':<40} {'Header'}")
    print(f"  {'-'*100}")
    for ts in result["top_sections"]:
        bk = ts["book_title"][:38]
        hd = ts["header"][:50]
        st = f" [{ts['source_type']}]" if ts["source_type"] else ""
        print(f"  {ts['rank']:>3} {ts['cosine_distance']:>7.4f} {ts['reranker_score']:>8.4f} {bk:<40} {hd}{st}")

    # Show content snippets for top-3
    print(f"\n  Content snippets (top-3):")
    for ts in result["top_sections"][:3]:
        print(f"\n  --- Rank {ts['rank']}: {ts['header']} (d={ts['cosine_distance']:.4f}, rerank={ts['reranker_score']:.4f}) ---")
        print(f"  Book: {ts['book_title']}")
        print(f"  Keywords: {', '.join(ts['keywords'][:5])}")
        snippet = ts["content_snippet"][:250]
        for line in snippet.split(". "):
            print(f"    {line.strip()}")


def main():
    parser = argparse.ArgumentParser(description="P1 Residual Failure Inspection")
    parser.add_argument("--db", default=None)
    parser.add_argument("--results", default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = args.db or str(project_root / "hiveai.db")
    results_path = args.results or str(project_root / "scripts" / "topic_gate_results" / "topic_gate_eval_results.json")

    # Load P0 results to identify failure cases
    print("Loading P0 results...")
    with open(results_path) as f:
        p0 = json.load(f)

    # Identify the cases we need to inspect:
    # 1. False accepts: off_domain queries with nearest_section_dist < 0.46
    # 2. False reject from mean-top-5: in_domain query with mean_top5_section_dist >= 0.46
    false_accepts = []
    false_reject_top5 = []

    for r in p0["per_query_results"]:
        sig = r["signals"]
        if r["label"] == "off_domain" and sig["nearest_section_dist"] < 0.46:
            false_accepts.append(r)
        if r["label"] == "in_domain" and sig["mean_top5_section_dist"] >= 0.46:
            false_reject_top5.append(r)

    print(f"\nFalse accepts (off-domain, nearest < 0.46): {len(false_accepts)}")
    for fa in false_accepts:
        print(f"  {fa['id']}: d={fa['signals']['nearest_section_dist']:.4f}  {fa['query'][:70]}")

    print(f"\nFalse rejects from mean-top-5 (in-domain, top5 >= 0.46): {len(false_reject_top5)}")
    for fr in false_reject_top5:
        print(f"  {fr['id']}: d={fr['signals']['mean_top5_section_dist']:.4f}  {fr['query'][:70]}")

    # Also find the borderline off-domain queries that are JUST above 0.46
    borderline_off = []
    for r in p0["per_query_results"]:
        sig = r["signals"]
        if r["label"] == "off_domain" and 0.46 <= sig["nearest_section_dist"] < 0.52:
            borderline_off.append(r)
    print(f"\nBorderline off-domain (0.46 <= nearest < 0.52): {len(borderline_off)}")
    for bo in borderline_off:
        print(f"  {bo['id']}: d={bo['signals']['nearest_section_dist']:.4f}  {bo['query'][:70]}")

    # Load section data
    print(f"\nLoading sections from {db_path}...")
    sections, books = load_section_embeddings(db_path)
    print(f"  {len(sections)} sections loaded")
    section_embeddings = np.stack([s["embedding"] for s in sections])

    # Embed the queries we need to inspect
    queries_to_inspect = []
    for fa in false_accepts:
        queries_to_inspect.append({"id": fa["id"], "query": fa["query"], "label": fa["label"]})
    for fr in false_reject_top5:
        queries_to_inspect.append({"id": fr["id"], "query": fr["query"], "label": fr["label"]})
    for bo in borderline_off:
        queries_to_inspect.append({"id": bo["id"], "query": bo["query"], "label": bo["label"]})

    print(f"\nEmbedding {len(queries_to_inspect)} queries for inspection...")
    queries_to_inspect, embed_model = embed_queries(queries_to_inspect)

    # Load reranker
    from sentence_transformers import CrossEncoder
    print("Loading cross-encoder reranker (BAAI/bge-reranker-v2-m3)...")
    reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")

    # Inspect each case
    all_inspections = []

    print("\n" + "=" * 80)
    print("FALSE ACCEPT INSPECTION (off-domain queries that would be accepted)")
    print("=" * 80)
    for q in queries_to_inspect:
        if q["label"] == "off_domain" and q["id"] in [fa["id"] for fa in false_accepts]:
            result = inspect_query(q, sections, section_embeddings, reranker)
            print_inspection(result)
            all_inspections.append(result)

    print("\n" + "=" * 80)
    print("FALSE REJECT INSPECTION (in-domain queries that mean-top-5 would reject)")
    print("=" * 80)
    for q in queries_to_inspect:
        if q["label"] == "in_domain":
            result = inspect_query(q, sections, section_embeddings, reranker)
            print_inspection(result)
            all_inspections.append(result)

    print("\n" + "=" * 80)
    print("BORDERLINE OFF-DOMAIN (just above threshold — context for understanding the gap)")
    print("=" * 80)
    for q in queries_to_inspect:
        if q["label"] == "off_domain" and q["id"] in [bo["id"] for bo in borderline_off]:
            result = inspect_query(q, sections, section_embeddings, reranker)
            print_inspection(result)
            all_inspections.append(result)

    # Save full inspection data
    out_dir = project_root / "scripts" / "topic_gate_results"
    out_file = out_dir / "residual_failure_inspection.json"
    with open(out_file, "w") as f:
        json.dump(all_inspections, f, indent=2, default=str)
    print(f"\nFull inspection saved to {out_file}")

    # === SUMMARY ===
    print("\n" + "=" * 80)
    print("RESIDUAL FAILURE ANALYSIS SUMMARY")
    print("=" * 80)

    print("\nReranker signal comparison:")
    print(f"  {'ID':<10} {'Label':<15} {'NearDist':>9} {'Top5Dist':>9} {'RerankBest':>11} {'RerankTop5':>11}")
    print(f"  {'-'*70}")
    for insp in all_inspections:
        m = insp["metrics"]
        print(f"  {insp['query_id']:<10} {insp['label']:<15} {m['nearest_section_dist']:>9.4f} "
              f"{m['mean_top5_dist']:>9.4f} {m['reranker_best']:>11.4f} {m['reranker_mean_top5']:>11.4f}")

    # Check if reranker separates where distance fails
    fa_reranker = [insp["metrics"]["reranker_best"] for insp in all_inspections if insp["label"] == "off_domain" and insp["query_id"] in [fa["id"] for fa in false_accepts]]
    fr_reranker = [insp["metrics"]["reranker_best"] for insp in all_inspections if insp["label"] == "in_domain"]

    if fa_reranker and fr_reranker:
        print(f"\n  False-accept reranker scores: {[round(x, 3) for x in fa_reranker]}")
        print(f"  False-reject reranker scores: {[round(x, 3) for x in fr_reranker]}")
        fa_max = max(fa_reranker)
        fr_min = min(fr_reranker) if fr_reranker else 0
        if fa_max < fr_min:
            print(f"  -> Reranker SEPARATES: FA max={fa_max:.3f} < FR min={fr_min:.3f}")
        else:
            print(f"  -> Reranker does NOT cleanly separate: FA max={fa_max:.3f} vs FR min={fr_min:.3f}")


if __name__ == "__main__":
    main()
