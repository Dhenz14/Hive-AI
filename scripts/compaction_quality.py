#!/usr/bin/env python3
"""
Compaction Quality Analyzer
============================

Measures how much information survives the knowledge compression pipeline.
Compares original book prose to dense-encoded compressed content across
five dimensions:

  1. Entity retention   — are named entities (projects, people, orgs) preserved?
  2. Numeric retention  — are dates, versions, quantities, measurements kept?
  3. URL retention      — are source links preserved?
  4. Key phrase overlap  — do important concept bigrams survive?
  5. Embedding similarity — (optional) semantic similarity via BAAI/bge-m3

Each dimension yields a 0.0-1.0 score. The overall quality score is a weighted
average. Books scoring below --threshold are flagged for re-compression.

Usage:
    python scripts/compaction_quality.py                      # Summary report
    python scripts/compaction_quality.py --verbose             # Per-book details
    python scripts/compaction_quality.py --book-id 5           # Single book deep-dive
    python scripts/compaction_quality.py --threshold 0.5       # Flag low-quality books
    python scripts/compaction_quality.py --json                # Machine-readable output
    python scripts/compaction_quality.py --with-embeddings     # Add semantic similarity

Exit codes:
    0 — all books above threshold (or no threshold set)
    1 — one or more books below threshold
    2 — no compressed books found
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words — excluded from key-phrase extraction
# ---------------------------------------------------------------------------
STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "of", "in", "to", "for",
    "with", "on", "at", "from", "by", "as", "or", "and", "but", "not",
    "it", "its", "this", "that", "these", "those", "i", "we", "you",
    "he", "she", "they", "also", "so", "if", "then", "than", "more",
    "very", "just", "about", "up", "out", "no", "only", "other", "into",
})


# ---------------------------------------------------------------------------
# Feature extractors
# ---------------------------------------------------------------------------
def extract_entities(text: str) -> set[str]:
    """Extract likely entity names from text.

    Catches:
      - Capitalized multi-word phrases: "Ethereum Virtual Machine"
      - Quoted terms: "proof of stake"
      - Technical identifiers: camelCase, snake_case, UPPER_CASE
      - Bracketed terms from dense format: [Topic Name]
    """
    entities: set[str] = set()
    # Capitalized phrases (2+ words, e.g. "Bitcoin Cash")
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
        entities.add(m.group(1).lower())
    # Single capitalized words 4+ chars (likely proper nouns, not "The")
    for m in re.finditer(r'\b([A-Z][a-z]{3,})\b', text):
        entities.add(m.group(1).lower())
    # Quoted terms
    for m in re.finditer(r'["\u201c]([^"\u201d]{2,50})["\u201d]', text):
        entities.add(m.group(1).lower().strip())
    # Technical identifiers: camelCase, snake_case, SCREAMING_CASE
    for m in re.finditer(r'\b([a-z]+[A-Z][a-zA-Z]+)\b', text):
        entities.add(m.group(1).lower())
    for m in re.finditer(r'\b([a-z][a-z]+_[a-z_]{2,})\b', text):
        entities.add(m.group(1))
    for m in re.finditer(r'\b([A-Z][A-Z_]{3,})\b', text):
        entities.add(m.group(1).lower())
    # Dense format bracketed topics: [Consensus Mechanisms]
    for m in re.finditer(r'\[([^\]]{2,50})\]', text):
        entities.add(m.group(1).lower())
    return entities


def extract_numbers(text: str) -> set[str]:
    """Extract numeric facts — dates, versions, quantities, measurements.

    Returns normalized number strings for comparison (e.g. "2024", "3.14", "100 GB").
    """
    numbers: set[str] = set()
    # Numbers with optional units
    units = r'(?:\s*(?:GB|MB|KB|TB|ms|ns|seconds?|minutes?|hours?|days?|years?|%|x|k|m|b|tps|rpm))?'
    for m in re.finditer(r'\b(\d{1,}(?:[.,]\d+)?' + units + r')\b', text, re.IGNORECASE):
        val = m.group(1).strip().lower()
        if len(val) >= 2:  # Skip single digits (noise)
            numbers.add(val)
    # Version strings: v1.2.3, 2.5.0
    for m in re.finditer(r'\bv?(\d+\.\d+(?:\.\d+)?)\b', text):
        numbers.add(m.group(1))
    # Year ranges: 2020-2024
    for m in re.finditer(r'\b((?:19|20)\d{2})\b', text):
        numbers.add(m.group(1))
    return numbers


def extract_urls(text: str) -> set[str]:
    """Extract URLs from text, normalized to lowercase."""
    urls: set[str] = set()
    for m in re.finditer(r'https?://[^\s<>"\')]+', text):
        url = m.group(0).rstrip('.,;:)')
        urls.add(url.lower())
    return urls


def extract_key_phrases(text: str) -> set[str]:
    """Extract meaningful bigrams (2-word phrases) as concept indicators.

    Filters out phrases composed entirely of stop words. Returns lowercase.
    """
    phrases: set[str] = set()
    words = re.findall(r'[a-z]+', text.lower())
    for i in range(len(words) - 1):
        w1, w2 = words[i], words[i + 1]
        # Both words must be 3+ chars and at least one non-stopword
        if len(w1) >= 3 and len(w2) >= 3:
            if w1 not in STOP_WORDS or w2 not in STOP_WORDS:
                phrases.add(f"{w1} {w2}")
    return phrases


def compute_embedding_similarity(original: str, compressed: str) -> float | None:
    """Compute cosine similarity between original and compressed using bge-m3.

    Returns float 0.0-1.0 or None if embedding model is unavailable.
    Imports are deferred to avoid loading the model when not needed.
    """
    try:
        from hiveai.llm.client import _get_embedding_model
        model = _get_embedding_model()
        if model is None:
            return None
        # Truncate to avoid OOM on very long texts
        orig_trunc = original[:4000]
        comp_trunc = compressed[:4000]
        embeddings = model.encode([orig_trunc, comp_trunc], normalize_embeddings=True)
        # Cosine similarity of normalized vectors = dot product
        similarity = float(embeddings[0] @ embeddings[1])
        return max(0.0, min(1.0, similarity))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core quality measurement
# ---------------------------------------------------------------------------

# Dimension weights for overall score
WEIGHTS = {
    "entity_retention": 0.30,
    "number_retention": 0.20,
    "url_retention": 0.15,
    "key_phrase_retention": 0.15,
    "embedding_similarity": 0.20,
}

# Weights when embedding is not available (redistribute its weight)
WEIGHTS_NO_EMBED = {
    "entity_retention": 0.40,
    "number_retention": 0.25,
    "url_retention": 0.15,
    "key_phrase_retention": 0.20,
}


def measure_quality(original: str, compressed: str,
                    with_embeddings: bool = False) -> dict:
    """Measure compaction quality across multiple dimensions.

    Args:
        original: The original book prose content.
        compressed: The dense-encoded compressed content.
        with_embeddings: If True, compute semantic similarity via bge-m3.

    Returns:
        Dict with per-dimension scores (0.0-1.0), compression stats,
        and an overall weighted quality score.
    """
    if not original or not compressed:
        return {
            "compression_ratio": 0.0,
            "entity_retention": 0.0,
            "number_retention": 0.0,
            "url_retention": 0.0,
            "key_phrase_retention": 0.0,
            "embedding_similarity": None,
            "overall_quality": 0.0,
            "original_words": 0,
            "compressed_words": 0,
            "stats": {},
        }

    orig_words = len(original.split())
    comp_words = len(compressed.split())
    ratio = orig_words / comp_words if comp_words > 0 else float('inf')
    comp_lower = compressed.lower()

    # --- Entity retention ---
    orig_entities = extract_entities(original)
    entity_hits = sum(1 for ent in orig_entities if ent in comp_lower)
    entity_retention = entity_hits / max(len(orig_entities), 1)

    # --- Number retention ---
    orig_numbers = extract_numbers(original)
    number_hits = sum(1 for n in orig_numbers if n in compressed.lower())
    number_retention = number_hits / max(len(orig_numbers), 1)

    # --- URL retention ---
    orig_urls = extract_urls(original)
    comp_urls = extract_urls(compressed)
    url_hits = len(orig_urls & comp_urls)
    url_retention = url_hits / max(len(orig_urls), 1) if orig_urls else 1.0

    # --- Key phrase retention ---
    orig_phrases = extract_key_phrases(original)
    phrase_hits = sum(1 for p in orig_phrases if p in comp_lower)
    phrase_retention = phrase_hits / max(len(orig_phrases), 1)

    # --- Embedding similarity (optional) ---
    embed_sim = None
    if with_embeddings:
        embed_sim = compute_embedding_similarity(original, compressed)

    # --- Overall score ---
    if embed_sim is not None:
        weights = WEIGHTS
        overall = (
            weights["entity_retention"] * entity_retention +
            weights["number_retention"] * number_retention +
            weights["url_retention"] * url_retention +
            weights["key_phrase_retention"] * phrase_retention +
            weights["embedding_similarity"] * embed_sim
        )
    else:
        weights = WEIGHTS_NO_EMBED
        overall = (
            weights["entity_retention"] * entity_retention +
            weights["number_retention"] * number_retention +
            weights["url_retention"] * url_retention +
            weights["key_phrase_retention"] * phrase_retention
        )

    return {
        "compression_ratio": round(ratio, 1),
        "entity_retention": round(entity_retention, 3),
        "number_retention": round(number_retention, 3),
        "url_retention": round(url_retention, 3),
        "key_phrase_retention": round(phrase_retention, 3),
        "embedding_similarity": round(embed_sim, 3) if embed_sim is not None else None,
        "overall_quality": round(overall, 3),
        "original_words": orig_words,
        "compressed_words": comp_words,
        "stats": {
            "entities_found": len(orig_entities),
            "entities_retained": entity_hits,
            "numbers_found": len(orig_numbers),
            "numbers_retained": number_hits,
            "urls_found": len(orig_urls),
            "urls_retained": url_hits,
            "phrases_found": len(orig_phrases),
            "phrases_retained": phrase_hits,
        },
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _quality_grade(q: float) -> str:
    """Return a letter grade for a quality score."""
    if q >= 0.85:
        return "A"
    elif q >= 0.70:
        return "B"
    elif q >= 0.55:
        return "C"
    elif q >= 0.40:
        return "D"
    return "F"


def _bar(value: float, width: int = 20) -> str:
    """Render a horizontal bar for a 0.0-1.0 value."""
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def print_book_detail(r: dict) -> None:
    """Print detailed quality report for a single book."""
    grade = _quality_grade(r["overall_quality"])
    logger.info(f"  Book #{r['book_id']}: {r['title']}")
    logger.info(f"  Grade: {grade}  |  Overall: {r['overall_quality']:.1%}")
    logger.info(f"  Compression: {r['original_words']:,} -> {r['compressed_words']:,} words ({r['compression_ratio']}x)")
    logger.info(f"")
    stats = r.get("stats", {})
    dims = [
        ("Entity retention", r["entity_retention"],
         f"{stats.get('entities_retained', '?')}/{stats.get('entities_found', '?')}"),
        ("Number retention", r["number_retention"],
         f"{stats.get('numbers_retained', '?')}/{stats.get('numbers_found', '?')}"),
        ("URL retention", r["url_retention"],
         f"{stats.get('urls_retained', '?')}/{stats.get('urls_found', '?')}"),
        ("Phrase retention", r["key_phrase_retention"],
         f"{stats.get('phrases_retained', '?')}/{stats.get('phrases_found', '?')}"),
    ]
    if r.get("embedding_similarity") is not None:
        dims.append(("Semantic similarity", r["embedding_similarity"], "cosine"))

    for label, val, detail in dims:
        logger.info(f"    {label:22s} {_bar(val)} {val:.1%}  ({detail})")
    logger.info("")


def print_summary(results: list[dict]) -> None:
    """Print aggregate quality report."""
    n = len(results)
    avg = lambda key: sum(r[key] for r in results) / n

    avg_quality = avg("overall_quality")
    avg_ratio = avg("compression_ratio")
    avg_entity = avg("entity_retention")
    avg_number = avg("number_retention")
    avg_url = avg("url_retention")
    avg_phrase = avg("key_phrase_retention")

    embed_results = [r for r in results if r.get("embedding_similarity") is not None]
    avg_embed = (sum(r["embedding_similarity"] for r in embed_results) / len(embed_results)
                 if embed_results else None)

    worst = results[0]   # sorted ascending
    best = results[-1]

    logger.info("=" * 64)
    logger.info(f"  COMPACTION QUALITY REPORT")
    logger.info(f"  {n} compressed books analyzed")
    logger.info("=" * 64)
    logger.info("")
    logger.info(f"  Overall quality:      {_bar(avg_quality)} {avg_quality:.1%}  (grade {_quality_grade(avg_quality)})")
    logger.info(f"  Avg compression:      {avg_ratio:.1f}x")
    logger.info("")
    logger.info(f"  Dimension averages:")
    logger.info(f"    Entity retention:   {_bar(avg_entity)} {avg_entity:.1%}")
    logger.info(f"    Number retention:   {_bar(avg_number)} {avg_number:.1%}")
    logger.info(f"    URL retention:      {_bar(avg_url)} {avg_url:.1%}")
    logger.info(f"    Phrase retention:   {_bar(avg_phrase)} {avg_phrase:.1%}")
    if avg_embed is not None:
        logger.info(f"    Semantic sim:       {_bar(avg_embed)} {avg_embed:.1%}")
    logger.info("")
    logger.info(f"  Best:  #{best['book_id']:3d} {best['title'][:45]:45s} {best['overall_quality']:.1%} ({_quality_grade(best['overall_quality'])})")
    logger.info(f"  Worst: #{worst['book_id']:3d} {worst['title'][:45]:45s} {worst['overall_quality']:.1%} ({_quality_grade(worst['overall_quality'])})")

    # Distribution histogram
    bins = {"A (85-100%)": 0, "B (70-84%)": 0, "C (55-69%)": 0, "D (40-54%)": 0, "F (0-39%)": 0}
    for r in results:
        q = r["overall_quality"]
        if q >= 0.85:
            bins["A (85-100%)"] += 1
        elif q >= 0.70:
            bins["B (70-84%)"] += 1
        elif q >= 0.55:
            bins["C (55-69%)"] += 1
        elif q >= 0.40:
            bins["D (40-54%)"] += 1
        else:
            bins["F (0-39%)"] += 1

    logger.info("")
    logger.info("  Grade distribution:")
    max_count = max(bins.values()) if any(bins.values()) else 1
    for label, count in bins.items():
        bar_len = int(count / max_count * 25) if max_count > 0 else 0
        logger.info(f"    {label:15s} {'█' * bar_len:25s} {count}")
    logger.info("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compaction Quality Analyzer — measure information retention "
                    "after knowledge compression.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        Summary report for all compressed books
  %(prog)s --verbose              Per-book breakdown with bar charts
  %(prog)s --book-id 5            Deep-dive on book #5
  %(prog)s --threshold 0.5        Flag books below 50%% quality
  %(prog)s --json --verbose       Machine-readable JSON output
  %(prog)s --with-embeddings      Add semantic similarity (slower, needs GPU)
"""
    )
    parser.add_argument("--book-id", type=int,
                        help="Analyze a single book by database ID")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-book quality details")
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Quality threshold — flag books below this (0.0-1.0)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON (for pipeline integration)")
    parser.add_argument("--with-embeddings", action="store_true",
                        help="Include embedding-based semantic similarity (slower)")
    args = parser.parse_args()

    # --- Load books from database ---
    try:
        from hiveai.models import GoldenBook, get_db
    except ImportError:
        logger.error("Cannot import hiveai.models — run from project root.")
        sys.exit(2)

    try:
        db = next(get_db())
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(2)

    query = db.query(GoldenBook).filter(
        GoldenBook.compressed_content.isnot(None),
        GoldenBook.compressed_content != "",
    )
    if args.book_id:
        query = query.filter(GoldenBook.id == args.book_id)

    books = query.all()
    if not books:
        msg = f"No compressed books found" + (f" (book_id={args.book_id})" if args.book_id else "")
        if args.json:
            print(json.dumps({"error": msg, "total_books": 0}))
        else:
            logger.info(msg)
        sys.exit(2)

    if not args.json:
        logger.info(f"Analyzing {len(books)} compressed books"
                     f"{' with embeddings' if args.with_embeddings else ''}...\n")

    # --- Measure quality ---
    results = []
    for book in books:
        quality = measure_quality(
            book.content or "",
            book.compressed_content or "",
            with_embeddings=args.with_embeddings,
        )
        quality["book_id"] = book.id
        quality["title"] = (book.title or "Untitled")[:60]
        results.append(quality)

    # Sort by quality ascending (worst first)
    results.sort(key=lambda r: r["overall_quality"])

    # --- Filter by threshold ---
    flagged = [r for r in results if r["overall_quality"] < args.threshold] if args.threshold > 0 else []

    # --- Output ---
    if args.json:
        avg_quality = sum(r["overall_quality"] for r in results) / len(results)
        output = {
            "total_books": len(results),
            "avg_quality": round(avg_quality, 3),
            "threshold": args.threshold if args.threshold > 0 else None,
            "flagged_count": len(flagged),
            "with_embeddings": args.with_embeddings,
            "books": results if args.verbose else None,
            "flagged_books": [{"book_id": r["book_id"], "title": r["title"],
                               "quality": r["overall_quality"]} for r in flagged] if flagged else None,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        if args.verbose or args.book_id:
            for r in results:
                print_book_detail(r)

        print_summary(results)

        if flagged:
            logger.info(f"  WARNING: {len(flagged)} book(s) below {args.threshold:.0%} threshold:")
            for r in flagged:
                logger.info(f"    #{r['book_id']:3d} {r['title'][:50]:50s} {r['overall_quality']:.1%}")
            logger.info("")

    # Exit code: 1 if books below threshold
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
