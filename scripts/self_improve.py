#!/usr/bin/env python3
"""
scripts/self_improve.py — Self-improving loop orchestrator.

Ties together auto_curate, consolidate_skills, evolve_skills, and
score_training_data into one automated improvement cycle.

Does NOT trigger training, push changes, or modify the model.
Only prepares data and skills for human review.

Usage:
    python scripts/self_improve.py                     # full cycle, last 7 days
    python scripts/self_improve.py --days 30           # wider lookback
    python scripts/self_improve.py --dry-run           # preview without executing
    python scripts/self_improve.py --skip-evolve       # skip skill evolution
    python scripts/self_improve.py --json              # machine-readable output
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "loras/training_data/self_improve"


def run_script(cmd: list[str], label: str, dry_run: bool = False) -> dict:
    """Run a subscript, capture output. Returns {ok, stdout, stderr, elapsed}."""
    if dry_run:
        return {"ok": True, "stdout": f"[dry-run] would run: {' '.join(cmd)}", "stderr": "", "elapsed": 0.0}

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, cwd=str(PROJECT_ROOT),
        )
        elapsed = time.monotonic() - t0
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed": round(elapsed, 1),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"{label} timed out (600s)", "elapsed": 600.0}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"{label} script not found", "elapsed": 0.0}


def step_score(days: int, dry_run: bool) -> dict:
    """Step 1: Run auto_curate to scan recent feedback."""
    export_path = DEFAULT_OUTPUT_DIR / "raw_candidates.jsonl"
    cmd = [
        sys.executable, str(SCRIPTS_DIR / "auto_curate.py"),
        "--days", str(days), "--export", str(export_path), "--json",
    ]
    result = run_script(cmd, "auto_curate", dry_run)

    stats = {"scanned": 0, "upvoted": 0, "downvoted": 0, "candidates": 0}
    if result["ok"] and result["stdout"].strip() and not dry_run:
        try:
            data = json.loads(result["stdout"])
            stats["scanned"] = data.get("total", 0)
            # Parse rating breakdown from category_stats or direct fields
            for pair in data.get("top_failures", []):
                stats["candidates"] += 1
            if export_path.exists():
                stats["candidates"] = sum(1 for _ in open(export_path))
        except (json.JSONDecodeError, KeyError):
            pass

    return {**result, "stats": stats}


def step_mine(days: int, dry_run: bool) -> dict:
    """Step 2: Extract high-quality pairs from upvoted feedback + corrections."""
    sys.path.insert(0, str(PROJECT_ROOT))
    stats = {"extracted": 0}

    if dry_run:
        return {"ok": True, "stdout": "[dry-run] would mine feedback pairs", "stderr": "", "elapsed": 0.0, "stats": stats}

    t0 = time.monotonic()
    try:
        from hiveai.models import SessionLocal, ChatFeedback
        from datetime import timedelta
        from scripts.auto_curate import score_quality

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        db = SessionLocal()
        rows = (
            db.query(ChatFeedback)
            .filter(ChatFeedback.created_at >= cutoff)
            .all()
        )

        upvoted = [r for r in rows if r.rating == "up"]
        downvoted = [r for r in rows if r.rating == "down"]
        pairs = []

        # Upvoted responses with good quality become training pairs
        for row in upvoted:
            q = score_quality(row.user_message, row.ai_response)
            if q["score"] >= 0.5:
                pairs.append({
                    "instruction": row.user_message,
                    "input": "",
                    "output": row.ai_response,
                    "source": "feedback_upvoted",
                })

        # Downvoted with corrections become training pairs (correction is the output)
        for row in downvoted:
            if row.correction and len(row.correction.strip()) > 20:
                pairs.append({
                    "instruction": row.user_message,
                    "input": "",
                    "output": row.correction,
                    "source": "feedback_correction",
                })

        db.close()

        # Write extracted pairs
        if pairs:
            out_path = DEFAULT_OUTPUT_DIR / "mined_pairs.jsonl"
            with open(out_path, "w", encoding="utf-8") as f:
                for p in pairs:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")

        stats["extracted"] = len(pairs)
        stats["from_upvoted"] = sum(1 for p in pairs if p["source"] == "feedback_upvoted")
        stats["from_corrections"] = sum(1 for p in pairs if p["source"] == "feedback_correction")
        stats["total_upvoted"] = len(upvoted)
        stats["total_downvoted"] = len(downvoted)
        elapsed = round(time.monotonic() - t0, 1)
        return {"ok": True, "stdout": "", "stderr": "", "elapsed": elapsed, "stats": stats}

    except Exception as e:
        elapsed = round(time.monotonic() - t0, 1)
        return {"ok": False, "stdout": "", "stderr": str(e), "elapsed": elapsed, "stats": stats}


def step_consolidate(dry_run: bool) -> dict:
    """Step 3: Run consolidate_skills to update SKILL.md from patterns."""
    script = SCRIPTS_DIR / "consolidate_skills.py"
    if not script.exists():
        return {"ok": True, "stdout": "[skip] consolidate_skills.py not found", "stderr": "", "elapsed": 0.0, "stats": {"updated": 0}}

    cmd = [sys.executable, str(script)]
    if dry_run:
        cmd.append("--dry-run")
    result = run_script(cmd, "consolidate_skills", dry_run=False)

    # Parse updated count from output
    updated = 0
    for line in result["stdout"].splitlines():
        if "updated" in line.lower() or "wrote" in line.lower():
            # Try to extract a number
            import re
            m = re.search(r"(\d+)", line)
            if m:
                updated = int(m.group(1))
                break

    return {**result, "stats": {"updated": updated}}


def step_evolve(dry_run: bool) -> dict:
    """Step 4: Run evolve_skills to test skill variants."""
    script = SCRIPTS_DIR / "evolve_skills.py"
    if not script.exists():
        return {"ok": False, "stdout": "", "stderr": "evolve_skills.py not found", "elapsed": 0.0, "stats": {"evolved": 0, "details": []}}

    cmd = [sys.executable, str(script), "--json"]
    if dry_run:
        cmd.append("--dry-run")
    result = run_script(cmd, "evolve_skills", dry_run=False)

    stats = {"evolved": 0, "details": []}
    if result["ok"] and result["stdout"].strip():
        try:
            data = json.loads(result["stdout"])
            if isinstance(data, list):
                stats["evolved"] = sum(1 for d in data if d.get("promoted"))
                stats["details"] = [
                    {"skill": d.get("skill", "?"), "lift": d.get("lift", 0)}
                    for d in data if d.get("promoted")
                ]
            elif isinstance(data, dict):
                stats["evolved"] = data.get("promoted_count", 0)
                stats["details"] = data.get("promoted", [])
        except json.JSONDecodeError:
            pass

    return {**result, "stats": stats}


def step_prepare(dry_run: bool) -> dict:
    """Step 5: Score and filter training data."""
    mined = DEFAULT_OUTPUT_DIR / "mined_pairs.jsonl"
    candidates = DEFAULT_OUTPUT_DIR / "candidates.jsonl"

    if not mined.exists():
        return {"ok": True, "stdout": "[skip] no mined pairs to score", "stderr": "", "elapsed": 0.0, "stats": {"input": 0, "passed": 0}}

    input_count = sum(1 for _ in open(mined))

    cmd = [
        sys.executable, str(SCRIPTS_DIR / "score_training_data.py"),
        str(mined), "--drop-below", "0.3", "--output", str(candidates),
    ]
    result = run_script(cmd, "score_training_data", dry_run)

    passed = 0
    if not dry_run and candidates.exists():
        passed = sum(1 for _ in open(candidates))

    return {**result, "stats": {"input": input_count, "passed": passed}}


def print_report(results: dict, args):
    """Print human-readable summary table."""
    mine = results["mine"]["stats"]
    consolidate = results["consolidate"]["stats"]
    evolve = results.get("evolve", {}).get("stats", {"evolved": 0, "details": []})
    prepare = results["prepare"]["stats"]

    scanned = mine.get("total_upvoted", 0) + mine.get("total_downvoted", 0)
    upvoted = mine.get("total_upvoted", 0)
    downvoted = mine.get("total_downvoted", 0)
    up_pct = round(100 * upvoted / scanned, 0) if scanned else 0
    down_pct = round(100 * downvoted / scanned, 0) if scanned else 0

    print(f"\n{'='*50}")
    print(f" Self-Improvement Cycle Report")
    print(f"{'='*50}")
    print(f"Feedback scanned:    {scanned} entries (last {args.days} days)")
    print(f"  Upvoted:           {upvoted} ({up_pct:.0f}%)")
    print(f"  Downvoted:         {downvoted} ({down_pct:.0f}%)")
    print(f"New training pairs:  {mine.get('extracted', 0)} extracted")

    # Skills
    skills_updated = consolidate.get("updated", 0)
    skills_names = []
    evolved_count = evolve.get("evolved", 0)
    evolved_details = evolve.get("details", [])

    print(f"Skills updated:      {skills_updated}", end="")
    if skills_names:
        print(f" ({', '.join(skills_names)})", end="")
    print()

    if evolved_count > 0:
        detail_str = ", ".join(
            f"{d.get('skill', '?')}: +{d.get('lift', 0):.1f}% lift"
            for d in evolved_details[:3]
        )
        print(f"Skills evolved:      {evolved_count} ({detail_str})")
    else:
        print(f"Skills evolved:      0")

    print(f"Data filtered:       {prepare['passed']}/{prepare['input']} passed importance scoring")

    candidates = DEFAULT_OUTPUT_DIR / "candidates.jsonl"
    if candidates.exists() and prepare["passed"] > 0:
        print(f"Ready for training:  {prepare['passed']} pairs in self_improve/candidates.jsonl")
    else:
        print(f"Ready for training:  0 pairs")

    # Timing
    total_time = sum(r.get("elapsed", 0) for r in results.values() if isinstance(r, dict))
    print(f"\nTotal time:          {total_time:.1f}s")

    # Errors
    errors = [
        (name, r["stderr"][:120])
        for name, r in results.items()
        if isinstance(r, dict) and not r.get("ok") and r.get("stderr")
    ]
    if errors:
        print(f"\nWarnings/Errors:")
        for name, err in errors:
            print(f"  [{name}] {err}")
    print()


def print_json(results: dict, args):
    """Print machine-readable JSON output."""
    mine = results["mine"]["stats"]
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "dry_run": args.dry_run,
        "feedback": {
            "scanned": mine.get("total_upvoted", 0) + mine.get("total_downvoted", 0),
            "upvoted": mine.get("total_upvoted", 0),
            "downvoted": mine.get("total_downvoted", 0),
        },
        "pairs_extracted": mine.get("extracted", 0),
        "skills_updated": results["consolidate"]["stats"].get("updated", 0),
        "skills_evolved": results.get("evolve", {}).get("stats", {}).get("evolved", 0),
        "data_filtered": {
            "input": results["prepare"]["stats"]["input"],
            "passed": results["prepare"]["stats"]["passed"],
        },
        "candidates_path": str(DEFAULT_OUTPUT_DIR / "candidates.jsonl"),
        "errors": [
            {"step": name, "error": r["stderr"][:200]}
            for name, r in results.items()
            if isinstance(r, dict) and not r.get("ok") and r.get("stderr")
        ],
    }
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Self-improving loop: score, mine, consolidate, evolve, prepare")
    parser.add_argument("--days", type=int, default=7,
                        help="Lookback window for feedback (default: 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without executing")
    parser.add_argument("--skip-evolve", action="store_true",
                        help="Skip skill evolution step (saves time)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help="Where to save extracted pairs")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output")
    args = parser.parse_args()

    global DEFAULT_OUTPUT_DIR
    DEFAULT_OUTPUT_DIR = Path(args.output_dir)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.json:
        print(f"[self_improve] Starting cycle (last {args.days} days, dry_run={args.dry_run})")

    results = {}

    # Step 1: Score — scan feedback for failures
    if not args.json:
        print("[1/6] Scanning feedback (auto_curate)...")
    results["score"] = step_score(args.days, args.dry_run)

    # Step 2: Mine — extract pairs from feedback
    if not args.json:
        print("[2/6] Mining training pairs from feedback...")
    results["mine"] = step_mine(args.days, args.dry_run)

    # Step 3: Consolidate — update SKILL.md
    if not args.json:
        print("[3/6] Consolidating skills...")
    results["consolidate"] = step_consolidate(args.dry_run)

    # Step 4: Evolve — test skill variants
    if args.skip_evolve:
        results["evolve"] = {"ok": True, "stdout": "[skipped]", "stderr": "", "elapsed": 0.0, "stats": {"evolved": 0, "details": []}}
        if not args.json:
            print("[4/6] Skill evolution skipped (--skip-evolve)")
    else:
        if not args.json:
            print("[4/6] Evolving skills...")
        results["evolve"] = step_evolve(args.dry_run)

    # Step 5: Prepare — score and filter training data
    if not args.json:
        print("[5/6] Scoring and filtering training data...")
    results["prepare"] = step_prepare(args.dry_run)

    # Step 6: Report
    if args.json:
        print_json(results, args)
    else:
        print("[6/6] Generating report...")
        print_report(results, args)


if __name__ == "__main__":
    main()
