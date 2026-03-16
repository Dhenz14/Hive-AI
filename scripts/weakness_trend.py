#!/usr/bin/env python3
"""
Weakness Trend Tracker -- append-only JSONL log of per-probe eval scores.

Tracks probe-level scores across versions to classify probes as:
  declining, resistant, improving, stable, volatile

Usage:
    python scripts/weakness_trend.py --show                    # show all trends
    python scripts/weakness_trend.py --domain cpp              # filter by domain
    python scripts/weakness_trend.py --resistant               # show only resistant probes
    python scripts/weakness_trend.py --compact                 # trim to last 1000 entries
    python scripts/weakness_trend.py --format json             # JSON output
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TREND_LOG_PATH = PROJECT_ROOT / "weakness_trend.jsonl"

# ---------------------------------------------------------------------------
# Weakness classifier (deterministic, versioned)
# ---------------------------------------------------------------------------
WEAKNESS_CLASSIFIER_VERSION = 1
KEYWORD_LOW_THRESHOLD = 0.70
STRUCTURE_LOW_THRESHOLD = 0.50


def classify_weakness_type(keyword_score: float, structure_score: float) -> str:
    """Deterministic weakness classification. Bump WEAKNESS_CLASSIFIER_VERSION if thresholds change."""
    if keyword_score < KEYWORD_LOW_THRESHOLD and structure_score < STRUCTURE_LOW_THRESHOLD:
        return "compound"
    elif keyword_score < KEYWORD_LOW_THRESHOLD:
        return "keyword_only"
    elif structure_score < STRUCTURE_LOW_THRESHOLD:
        return "structure_only"
    else:
        return "none"


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------
def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_probe_library_hash() -> str:
    probe_lib = PROJECT_ROOT / "scripts" / "probe_library.py"
    if probe_lib.exists():
        content = probe_lib.read_bytes()
        return hashlib.sha256(content).hexdigest()[:8]
    return "unknown"


SCORER_VERSION = "regression_eval_v2"


# ---------------------------------------------------------------------------
# Trend entry append
# ---------------------------------------------------------------------------
def append_trend_entry(version: str, domain: str, probe_id: str,
                       score: float, keyword_score: float = None,
                       structure_score: float = None,
                       prev_score: float = None, eval_mode: str = "full",
                       fix_attempted: bool = False, fix_version: str = None,
                       fix_result: str = None, path: str = None):
    """Append one trend entry per probe per eval run."""
    log_path = Path(path) if path else TREND_LOG_PATH

    delta = round(score - prev_score, 4) if prev_score is not None else None
    weakness_type = classify_weakness_type(
        keyword_score or 0.0, structure_score or 0.0
    )

    entry = {
        "version": version,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "domain": domain,
        "probe_id": probe_id,
        "score": round(score, 4),
        "keyword_score": round(keyword_score, 4) if keyword_score is not None else None,
        "structure_score": round(structure_score, 4) if structure_score is not None else None,
        "weakness_type": weakness_type,
        "weakness_classifier_version": WEAKNESS_CLASSIFIER_VERSION,
        "prev_score": round(prev_score, 4) if prev_score is not None else None,
        "delta": delta,
        "eval_mode": eval_mode,
        "fix_attempted": fix_attempted,
        "fix_version": fix_version,
        "fix_result": fix_result,
        "provenance": {
            "scorer_version": SCORER_VERSION,
            "probe_library_hash": _get_probe_library_hash(),
            "git_sha": _get_git_sha(),
        },
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Trend log loading
# ---------------------------------------------------------------------------
def load_trend_log(path: str = None, eval_mode: str = None,
                   max_entries: int = 1000) -> list[dict]:
    """Load trend log, optionally filtered by eval_mode. Last max_entries entries."""
    log_path = Path(path) if path else TREND_LOG_PATH
    if not log_path.exists():
        return []

    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if eval_mode and entry.get("eval_mode") != eval_mode:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    # Return last max_entries
    return entries[-max_entries:]


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------
@dataclass
class TrendClassification:
    probe_id: str
    domain: str
    trend: str          # declining, resistant, improving, stable, volatile
    consecutive: int    # N consecutive drops/gains/fix-fails
    avg_score: float
    scores: list
    fix_attempts: int
    fix_successes: int


def classify_trends(entries: list[dict]) -> dict[str, TrendClassification]:
    """Classify each probe as declining/resistant/improving/stable/volatile."""
    # Group entries by probe_id (ordered by time)
    by_probe = {}
    for e in entries:
        pid = e.get("probe_id", "")
        if pid not in by_probe:
            by_probe[pid] = []
        by_probe[pid].append(e)

    results = {}
    for pid, probe_entries in by_probe.items():
        scores = [e["score"] for e in probe_entries]
        domain = probe_entries[-1].get("domain", "")
        fix_attempts = sum(1 for e in probe_entries if e.get("fix_attempted"))
        fix_successes = sum(
            1 for e in probe_entries
            if e.get("fix_result") in ("improved", "fixed")
        )

        last_5 = scores[-5:]
        trend = "volatile"
        consecutive = 0

        if len(last_5) >= 3:
            # Check declining: 3+ consecutive drops
            drops = 0
            for i in range(1, len(last_5)):
                if last_5[i] < last_5[i - 1]:
                    drops += 1
                else:
                    drops = 0
            if drops >= 2:
                trend = "declining"
                consecutive = drops

            # Check improving: 3+ consecutive gains
            gains = 0
            for i in range(1, len(last_5)):
                if last_5[i] > last_5[i - 1]:
                    gains += 1
                else:
                    gains = 0
            if gains >= 2:
                trend = "improving"
                consecutive = gains

            # Check stable: variance < 0.02
            if len(last_5) >= 3:
                mean = sum(last_5) / len(last_5)
                variance = sum((s - mean) ** 2 for s in last_5) / len(last_5)
                if variance < 0.0004:  # 0.02^2
                    trend = "stable"
                    consecutive = len(last_5)

            # Check resistant: 3+ fix attempts with <0.01 cumulative improvement
            if fix_attempts >= 3:
                first_score = scores[0]
                last_score = scores[-1]
                if last_score - first_score < 0.01:
                    trend = "resistant"
                    consecutive = fix_attempts

        avg = round(sum(last_5) / len(last_5), 4) if last_5 else 0.0
        results[pid] = TrendClassification(
            probe_id=pid,
            domain=domain,
            trend=trend,
            consecutive=consecutive,
            avg_score=avg,
            scores=last_5,
            fix_attempts=fix_attempts,
            fix_successes=fix_successes,
        )

    return results


def get_domain_trend(domain: str, entries: list[dict] = None) -> dict:
    """Domain-level summary with per-probe breakdown."""
    if entries is None:
        entries = load_trend_log()

    domain_entries = [e for e in entries if e.get("domain") == domain]
    if not domain_entries:
        return {"domain": domain, "probes": {}, "avg_score": 0.0}

    trends = classify_trends(domain_entries)
    probe_summaries = {}
    for pid, tc in trends.items():
        probe_summaries[pid] = {
            "trend": tc.trend,
            "avg_score": tc.avg_score,
            "consecutive": tc.consecutive,
            "fix_attempts": tc.fix_attempts,
        }

    all_avgs = [tc.avg_score for tc in trends.values()]
    return {
        "domain": domain,
        "avg_score": round(sum(all_avgs) / len(all_avgs), 4) if all_avgs else 0.0,
        "probes": probe_summaries,
    }


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------
def compact_log(path: str = None, keep: int = 1000):
    """Trim trend log to last N entries."""
    log_path = Path(path) if path else TREND_LOG_PATH
    entries = load_trend_log(path=str(log_path), max_entries=keep)
    with open(log_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Compacted to {len(entries)} entries")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Weakness Trend Tracker")
    parser.add_argument("--show", action="store_true", help="Show trend table")
    parser.add_argument("--domain", type=str, help="Filter by domain")
    parser.add_argument("--resistant", action="store_true", help="Show only resistant probes")
    parser.add_argument("--format", type=str, default="table", choices=["table", "json"])
    parser.add_argument("--compact", action="store_true", help="Trim to last 1000 entries")
    parser.add_argument("--eval-mode", type=str, default=None, help="Filter by eval mode")
    args = parser.parse_args()

    if args.compact:
        compact_log()
        return

    entries = load_trend_log(eval_mode=args.eval_mode)
    if not entries:
        print("No trend data yet. Run regression_eval.py to populate.")
        return

    trends = classify_trends(entries)

    # Filter
    if args.domain:
        trends = {k: v for k, v in trends.items() if v.domain == args.domain}
    if args.resistant:
        trends = {k: v for k, v in trends.items() if v.trend == "resistant"}

    if args.format == "json":
        print(json.dumps({k: asdict(v) for k, v in trends.items()}, indent=2))
        return

    # Table output
    print(f"\n{'Probe ID':20s} {'Domain':8s} {'Trend':12s} {'Consec':>6s} "
          f"{'Avg':>6s} {'Fixes':>5s} {'Last 5 Scores'}")
    print("-" * 85)
    for pid in sorted(trends, key=lambda k: (trends[k].domain, k)):
        tc = trends[pid]
        scores_str = " ".join(f"{s:.3f}" for s in tc.scores)
        trend_marker = {"declining": "!!", "resistant": "XX",
                        "improving": "++", "stable": "==", "volatile": "~~"}.get(tc.trend, "  ")
        print(f"  {pid:18s} {tc.domain:8s} {trend_marker} {tc.trend:10s} "
              f"{tc.consecutive:>4d}   {tc.avg_score:.3f} {tc.fix_attempts:>3d}   {scores_str}")

    print(f"\nTotal: {len(trends)} probes from {len(entries)} entries")


if __name__ == "__main__":
    main()
