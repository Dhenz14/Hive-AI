#!/usr/bin/env python3
"""
scripts/auto_curate.py — Self-improving loop: review responses, find failures, generate training candidates.

Implements improvement_notes.md section 6: scan conversation logs and training data for
weak responses, score quality, detect failure patterns, and export candidates for
retraining or manual review.

Usage:
    python scripts/auto_curate.py                          # scan DB chat feedback, last 7 days
    python scripts/auto_curate.py --days 30                # last 30 days
    python scripts/auto_curate.py --json                   # machine-readable output
    python scripts/auto_curate.py --export candidates.jsonl # export failure candidates
    python scripts/auto_curate.py --file loras/training_data/v7.jsonl  # scan JSONL instead of DB
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Quality scoring signals
# ---------------------------------------------------------------------------

# Error / uncertainty indicators in responses
ERROR_INDICATORS = [
    "i don't know", "i can't", "i cannot", "i'm not sure",
    "i am not sure", "i'm unable", "i am unable",
    "as an ai", "as a language model",
    "i apologize", "i'm sorry but",
    "unfortunately, i", "i don't have access",
    "error occurred", "traceback (most recent",
    "undefined is not", "null pointer", "segmentation fault",
]

HALLUCINATION_MARKERS = [
    "as of my last update", "as of my knowledge cutoff",
    "i was last trained", "my training data",
    "i believe", "i think it might be",
]

# Category detection keywords
CATEGORY_KEYWORDS = {
    "Hive": ["hive", "hive_keychain", "hivesigner", "dhive", "beem", "hive-engine",
             "ssc-steem", "steem", "hive blockchain", "hiveio", "splinterlands",
             "custom_json", "broadcast", "permlink", "posting_key"],
    "Rust": ["rust", "cargo", "tokio", "async fn", "impl ", "trait ", "borrow checker",
             "lifetime", "ownership", "Arc<", "Mutex<", "Result<", "Option<"],
    "Go": ["golang", "go ", "goroutine", "channel", "sync.Mutex", "errgroup",
           "context.Context", "http.Handler", "go func", "defer ", "select {"],
    "C++": ["c++", "cpp", "template<", "std::", "unique_ptr", "shared_ptr",
            "constexpr", "RAII", "move semantics", "virtual ", "namespace "],
    "Python": ["python", "flask", "django", "fastapi", "asyncio",
               "pandas", "numpy", "pytest", "decorator", "dataclass"],
    "JavaScript": ["javascript", "typescript", "react", "node.js", "express",
                   "async/await", "promise", "webpack", "nextjs", "vue"],
}


def score_quality(instruction: str, response: str) -> dict:
    """Multi-signal quality scorer. Returns dict with overall score and breakdown."""
    response_lower = response.lower()
    word_count = len(response.split())
    signals = {}

    # 1. Response length (0-0.15)
    if word_count >= 200:
        signals["length"] = 0.15
    elif word_count >= 100:
        signals["length"] = 0.12
    elif word_count >= 50:
        signals["length"] = 0.08
    elif word_count >= 20:
        signals["length"] = 0.03
    else:
        signals["length"] = 0.0

    # 2. Code presence and tagging (0-0.25)
    code_blocks = re.findall(r"```[\w]*\n.*?```", response, re.DOTALL)
    code_score = 0.0
    if code_blocks:
        code_score += 0.10
        tagged = sum(1 for b in code_blocks if re.match(r"```\w+", b))
        if tagged >= 1:
            code_score += 0.10
        if len(code_blocks) >= 2:
            code_score += 0.05
    signals["code"] = code_score

    # 3. Concept coverage — keywords from query appear in response (0-0.20)
    inst_words = set(w.lower() for w in instruction.split() if len(w) > 4)
    if inst_words:
        covered = sum(1 for w in inst_words if w in response_lower)
        coverage = covered / len(inst_words)
        signals["coverage"] = round(coverage * 0.20, 3)
    else:
        signals["coverage"] = 0.10  # short queries get partial credit

    # 4. Structure quality — headings, lists, organized output (0-0.15)
    has_headings = bool(re.search(r"^#{1,4}\s", response, re.MULTILINE))
    has_lists = bool(re.search(r"^[\-\*]\s", response, re.MULTILINE))
    has_numbered = bool(re.search(r"^\d+\.\s", response, re.MULTILINE))
    structure_count = sum([has_headings, has_lists, has_numbered])
    signals["structure"] = min(structure_count / 2, 1.0) * 0.15

    # 5. Explanation quality — text outside code blocks (0-0.15)
    text_only = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
    text_words = len(text_only.split())
    if text_words > 50:
        signals["explanation"] = 0.15
    elif text_words > 20:
        signals["explanation"] = 0.10
    elif text_words > 5:
        signals["explanation"] = 0.05
    else:
        signals["explanation"] = 0.0

    # 6. Penalties
    penalty = 0.0

    # Error indicators
    error_hits = sum(1 for e in ERROR_INDICATORS if e in response_lower)
    if error_hits >= 2:
        penalty += 0.20
    elif error_hits >= 1:
        penalty += 0.10

    # Hallucination markers
    hallucination_hits = sum(1 for h in HALLUCINATION_MARKERS if h in response_lower)
    if hallucination_hits >= 1:
        penalty += 0.10

    # Too short
    if word_count < 20:
        penalty += 0.15
    elif word_count < 50:
        penalty += 0.05

    # Repetitive content
    sentences = re.split(r"[.!?]\n", response)
    if len(sentences) > 3:
        unique = len(set(s.strip().lower()[:50] for s in sentences if s.strip()))
        repetition_ratio = 1.0 - (unique / len(sentences))
        if repetition_ratio > 0.3:
            penalty += 0.10

    signals["penalty"] = round(-penalty, 3)

    # Final score
    raw = sum(signals.values())
    overall = max(0.0, min(1.0, raw))

    return {
        "score": round(overall, 3),
        "signals": signals,
        "word_count": word_count,
        "code_blocks": len(code_blocks) if code_blocks else 0,
    }


def detect_category(instruction: str, response: str) -> str:
    """Detect the topic category of a pair."""
    combined = f"{instruction} {response}".lower()
    hits = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        count = sum(1 for k in keywords if k.lower() in combined)
        if count > 0:
            hits[cat] = count
    if hits:
        return max(hits, key=hits.get)
    return "General"


# ---------------------------------------------------------------------------
# Database scanner
# ---------------------------------------------------------------------------

def scan_database(days: int) -> list[dict]:
    """Scan ChatFeedback table for recent user-assistant pairs."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from hiveai.models import SessionLocal, ChatFeedback
    except Exception as e:
        print(f"  [warn] Cannot import database models: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    pairs = []

    try:
        db = SessionLocal()
        rows = (
            db.query(ChatFeedback)
            .filter(ChatFeedback.created_at >= cutoff)
            .order_by(ChatFeedback.created_at.desc())
            .all()
        )
        for row in rows:
            pairs.append({
                "id": row.id,
                "instruction": row.user_message,
                "response": row.ai_response,
                "rating": row.rating,
                "correction": row.correction,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "source": "chat_feedback",
            })
        db.close()
    except Exception as e:
        print(f"  [warn] Database query failed: {e}", file=sys.stderr)

    return pairs


# ---------------------------------------------------------------------------
# JSONL scanner (fallback)
# ---------------------------------------------------------------------------

def scan_jsonl(file_path: str) -> list[dict]:
    """Scan a JSONL training data file for pairs."""
    pairs = []
    path = Path(file_path)
    if not path.exists():
        print(f"  [error] File not found: {file_path}", file=sys.stderr)
        return []

    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pairs.append({
                    "id": i,
                    "instruction": obj.get("instruction", ""),
                    "response": obj.get("output", ""),
                    "rating": None,
                    "correction": None,
                    "created_at": None,
                    "source": f"jsonl:{path.name}",
                })
            except json.JSONDecodeError:
                continue

    return pairs


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_pairs(pairs: list[dict]) -> dict:
    """Score all pairs and detect failure patterns."""
    scored_pairs = []
    failures = []
    category_scores = defaultdict(list)
    failure_categories = Counter()

    for pair in pairs:
        result = score_quality(pair["instruction"], pair["response"])
        category = detect_category(pair["instruction"], pair["response"])

        entry = {
            "id": pair["id"],
            "instruction": pair["instruction"],
            "instruction_preview": pair["instruction"][:100],
            "response_preview": pair["response"][:150],
            "score": result["score"],
            "signals": result["signals"],
            "word_count": result["word_count"],
            "code_blocks": result["code_blocks"],
            "category": category,
            "rating": pair.get("rating"),
            "source": pair.get("source", "unknown"),
            "created_at": pair.get("created_at"),
        }
        scored_pairs.append(entry)
        category_scores[category].append(result["score"])

        # Identify failures
        if result["score"] < 0.4:
            entry["failure_reason"] = _classify_failure(result, pair["response"])
            failures.append(entry)
            failure_categories[category] += 1

    # Sort by score ascending (worst first)
    scored_pairs.sort(key=lambda x: x["score"])
    failures.sort(key=lambda x: x["score"])

    # Compute category averages
    cat_averages = {}
    for cat, scores in category_scores.items():
        cat_averages[cat] = {
            "avg_score": round(sum(scores) / len(scores), 3),
            "count": len(scores),
            "failures": sum(1 for s in scores if s < 0.4),
        }

    # Failure pattern summary
    failure_patterns = _detect_failure_patterns(failures)

    return {
        "total": len(scored_pairs),
        "avg_score": round(sum(p["score"] for p in scored_pairs) / max(len(scored_pairs), 1), 3),
        "failures": failures,
        "failure_count": len(failures),
        "failure_rate": round(len(failures) / max(len(scored_pairs), 1), 3),
        "category_stats": cat_averages,
        "failure_categories": dict(failure_categories),
        "failure_patterns": failure_patterns,
        "scored_pairs": scored_pairs,
    }


def _classify_failure(result: dict, response: str) -> str:
    """Classify why a response failed."""
    reasons = []
    if result["word_count"] < 20:
        reasons.append("too_short")
    if result["word_count"] < 50:
        reasons.append("brief")
    if result["code_blocks"] == 0:
        reasons.append("no_code")
    if result["signals"].get("coverage", 0) < 0.05:
        reasons.append("off_topic")
    if result["signals"].get("penalty", 0) < -0.15:
        reasons.append("error_indicators")

    response_lower = response.lower()
    if any(h in response_lower for h in HALLUCINATION_MARKERS):
        reasons.append("hallucination_risk")
    if any(e in response_lower for e in ERROR_INDICATORS[:7]):
        reasons.append("refusal")

    return "|".join(reasons) if reasons else "low_overall"


def _detect_failure_patterns(failures: list[dict]) -> list[dict]:
    """Detect recurring failure patterns across failures."""
    patterns = []

    # Pattern 1: Common failure reasons
    reason_counts = Counter()
    for f in failures:
        for reason in f.get("failure_reason", "").split("|"):
            if reason:
                reason_counts[reason] += 1

    for reason, count in reason_counts.most_common(10):
        if count >= 2:
            patterns.append({
                "pattern": reason,
                "count": count,
                "pct": round(count / max(len(failures), 1) * 100, 1),
            })

    # Pattern 2: Categories that consistently fail
    cat_counts = Counter(f["category"] for f in failures)
    for cat, count in cat_counts.most_common(5):
        if count >= 2:
            patterns.append({
                "pattern": f"category:{cat}",
                "count": count,
                "pct": round(count / max(len(failures), 1) * 100, 1),
            })

    return patterns


# ---------------------------------------------------------------------------
# Training candidate generation
# ---------------------------------------------------------------------------

def generate_candidates(failures: list[dict]) -> list[dict]:
    """Generate training pair candidates from identified failures."""
    candidates = []
    for f in failures:
        candidates.append({
            "instruction": f["instruction"],
            "input": "",
            "output": "",  # empty — needs re-generation or manual review
            "metadata": {
                "source": "auto_curate",
                "original_score": f["score"],
                "failure_reason": f.get("failure_reason", "low_quality"),
                "category": f["category"],
                "status": "needs_improvement",
                "original_source": f.get("source", "unknown"),
                "curated_at": datetime.now(timezone.utc).isoformat(),
            },
        })
    return candidates


def export_candidates(candidates: list[dict], output_path: str):
    """Export training candidates to JSONL."""
    path = Path(output_path)
    with open(path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return len(candidates)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(analysis: dict, source_label: str):
    """Print a human-readable console report."""
    print(f"\n{'=' * 75}")
    print(f"  AUTO-CURATION REPORT — {source_label}")
    print(f"{'=' * 75}")
    print(f"  Total pairs scanned:  {analysis['total']}")
    print(f"  Average quality:      {analysis['avg_score']:.3f}")
    print(f"  Failures (< 0.4):     {analysis['failure_count']}  "
          f"({analysis['failure_rate'] * 100:.1f}%)")
    print()

    # Category breakdown
    if analysis["category_stats"]:
        print(f"  CATEGORY BREAKDOWN:")
        print(f"  {'Category':<15} {'Avg Score':>10} {'Count':>6} {'Failures':>9}")
        print(f"  {'-' * 45}")
        for cat, stats in sorted(analysis["category_stats"].items(),
                                  key=lambda x: x[1]["avg_score"]):
            print(f"  {cat:<15} {stats['avg_score']:>10.3f} {stats['count']:>6} "
                  f"{stats['failures']:>9}")
        print()

    # Failure patterns
    if analysis["failure_patterns"]:
        print(f"  FAILURE PATTERNS:")
        print(f"  {'Pattern':<30} {'Count':>6} {'% of failures':>14}")
        print(f"  {'-' * 55}")
        for p in analysis["failure_patterns"]:
            print(f"  {p['pattern']:<30} {p['count']:>6} {p['pct']:>13.1f}%")
        print()

    # Top failures
    failures = analysis["failures"][:15]
    if failures:
        print(f"  TOP FAILURES (worst first):")
        print(f"  {'#':>4}  {'Score':>5}  {'Cat':<10}  {'Reason':<25}  Instruction")
        print(f"  {'-' * 75}")
        for f in failures:
            reason = f.get("failure_reason", "")[:25]
            preview = f["instruction_preview"][:40]
            print(f"  {f['id']:4}  {f['score']:5.3f}  {f['category']:<10}  "
                  f"{reason:<25}  {preview}")
        print()

    # Score distribution
    scored = analysis["scored_pairs"]
    if scored:
        bins = {
            "0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0,
            "0.6-0.8": 0, "0.8-1.0": 0,
        }
        for p in scored:
            s = p["score"]
            if s < 0.2:
                bins["0.0-0.2"] += 1
            elif s < 0.4:
                bins["0.2-0.4"] += 1
            elif s < 0.6:
                bins["0.4-0.6"] += 1
            elif s < 0.8:
                bins["0.6-0.8"] += 1
            else:
                bins["0.8-1.0"] += 1

        print(f"  SCORE DISTRIBUTION:")
        max_count = max(bins.values()) if bins.values() else 1
        for label, count in bins.items():
            bar_len = int(count / max(max_count, 1) * 30)
            bar = "#" * bar_len
            print(f"  {label}  {count:>5}  {bar}")
        print()

    if not failures:
        print("  No failures detected — all responses above quality threshold.")
    print(f"{'=' * 75}\n")


def print_json_report(analysis: dict, source_label: str):
    """Print machine-readable JSON report."""
    output = {
        "source": source_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": analysis["total"],
            "avg_score": analysis["avg_score"],
            "failure_count": analysis["failure_count"],
            "failure_rate": analysis["failure_rate"],
        },
        "category_stats": analysis["category_stats"],
        "failure_patterns": analysis["failure_patterns"],
        "failures": [
            {
                "id": f["id"],
                "instruction_preview": f["instruction_preview"],
                "score": f["score"],
                "category": f["category"],
                "failure_reason": f.get("failure_reason", ""),
                "word_count": f["word_count"],
                "code_blocks": f["code_blocks"],
            }
            for f in analysis["failures"]
        ],
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Auto-curate: scan responses, score quality, detect failures, "
                    "generate training candidates.")
    parser.add_argument("--days", type=int, default=7,
                        help="Lookback window in days for DB scan (default: 7)")
    parser.add_argument("--file", type=str, default=None,
                        help="Scan a JSONL training data file instead of the database")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--export", type=str, default=None,
                        help="Export failure candidates to JSONL file")
    parser.add_argument("--threshold", type=float, default=0.4,
                        help="Quality threshold for failures (default: 0.4)")
    args = parser.parse_args()

    # Collect pairs from either DB or JSONL
    if args.file:
        source_label = f"JSONL: {Path(args.file).name}"
        pairs = scan_jsonl(args.file)
    else:
        source_label = f"Database (last {args.days} days)"
        pairs = scan_database(args.days)
        if not pairs:
            print("  [info] No chat data in database. Use --file to scan JSONL training data.",
                  file=sys.stderr)
            # Try default training data as fallback
            default_jsonl = Path(__file__).resolve().parent.parent / "loras" / "training_data"
            jsonl_files = sorted(default_jsonl.glob("v*.jsonl"), reverse=True)
            if jsonl_files:
                fallback = jsonl_files[0]
                print(f"  [info] Falling back to: {fallback.name}", file=sys.stderr)
                source_label = f"JSONL fallback: {fallback.name}"
                pairs = scan_jsonl(str(fallback))

    if not pairs:
        print("  [error] No data to analyze. Provide --file or ensure DB has chat feedback.",
              file=sys.stderr)
        sys.exit(1)

    # Run analysis
    analysis = analyze_pairs(pairs)

    # Output report
    if args.json:
        print_json_report(analysis, source_label)
    else:
        print_report(analysis, source_label)

    # Export candidates if requested
    if args.export:
        candidates = generate_candidates(analysis["failures"])
        if candidates:
            count = export_candidates(candidates, args.export)
            if not args.json:
                print(f"  Exported {count} training candidates -> {args.export}")
        else:
            if not args.json:
                print("  No failure candidates to export.")


if __name__ == "__main__":
    main()
