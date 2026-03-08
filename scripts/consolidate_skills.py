#!/usr/bin/env python3
"""
consolidate_skills.py — Extract recurring patterns from chat feedback
and auto-update SKILL.md files with new examples and gotchas.

Usage:
    python scripts/consolidate_skills.py --days 7 --dry-run
    python scripts/consolidate_skills.py --skill rust_async --min-feedback 3
    python scripts/consolidate_skills.py --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Project root: two levels up from this script (scripts/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.models import SessionLocal, ChatFeedback

SKILLS_DIR = PROJECT_ROOT / "skills"
MAX_NEW_TOKENS = 500

# Reuse SKILL_ROUTES from skill_loader for consistent classification
from skills.skill_loader import SKILL_ROUTES


# ── Feedback collection ─────────────────────────────────────────────

def fetch_feedback(days: int):
    """Fetch ChatFeedback entries from the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatFeedback)
            .filter(ChatFeedback.created_at >= cutoff)
            .filter(ChatFeedback.rating.in_(["up", "down"]))
            .all()
        )
        # Detach from session before closing
        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "user_message": r.user_message,
                "ai_response": r.ai_response,
                "rating": r.rating,
                "correction": r.correction,
                "created_at": r.created_at,
            })
        return result
    finally:
        db.close()


# ── Skill classification ────────────────────────────────────────────

def classify_feedback(entry: dict) -> list[str]:
    """Return list of skill names that match this feedback entry."""
    text = f"{entry['user_message']} {entry['ai_response']}".lower()
    matched = []
    for skill_name, patterns, priority in SKILL_ROUTES:
        for pattern in patterns:
            if re.search(pattern, text):
                matched.append((priority, skill_name))
                break
    matched.sort(key=lambda x: -x[0])
    seen = set()
    result = []
    for _, name in matched:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def group_by_skill(entries: list[dict]) -> dict[str, dict]:
    """Group feedback entries by skill, split into up/down."""
    groups = defaultdict(lambda: {"up": [], "down": []})
    for entry in entries:
        skills = classify_feedback(entry)
        for skill in skills:
            groups[skill][entry["rating"]].append(entry)
    return dict(groups)


# ── Pattern extraction ──────────────────────────────────────────────

def extract_code_blocks(text: str) -> list[str]:
    """Extract fenced code blocks from text."""
    blocks = re.findall(r"```[\w]*\n(.*?)```", text, re.DOTALL)
    # Filter to non-trivial blocks (at least 2 lines)
    return [b.strip() for b in blocks if b.strip().count("\n") >= 1]


def extract_success_patterns(entries: list[dict], max_examples: int = 3) -> list[str]:
    """Extract key code examples from successful (up-rated) responses."""
    all_blocks = []
    for entry in entries:
        blocks = extract_code_blocks(entry["ai_response"])
        for block in blocks:
            # Keep blocks between 3-30 lines (not too trivial, not too long)
            lines = block.count("\n") + 1
            if 3 <= lines <= 30:
                all_blocks.append(block)

    # Deduplicate by first line (common pattern: same boilerplate)
    seen_starts = set()
    unique = []
    for block in all_blocks:
        first_line = block.split("\n")[0].strip()
        if first_line not in seen_starts:
            seen_starts.add(first_line)
            unique.append(block)

    return unique[:max_examples]


def extract_failure_patterns(entries: list[dict], max_patterns: int = 5) -> list[str]:
    """Extract failure patterns from down-rated responses."""
    patterns = []
    for entry in entries:
        msg = entry["user_message"]
        correction = entry.get("correction") or ""
        # If there's a correction, the delta is the pattern
        if correction:
            patterns.append(f"Q: {msg[:100]}... -> Correction provided: {correction[:200]}")
        else:
            # Use first 150 chars of the response as context for what went wrong
            resp_preview = entry["ai_response"][:150].replace("\n", " ")
            patterns.append(f"Q: {msg[:100]}... -> Bad response started with: {resp_preview}")

    # Deduplicate by question prefix
    seen = set()
    unique = []
    for p in patterns:
        key = p[:60]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique[:max_patterns]


# ── SKILL.md update logic ──────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 4/3."""
    return len(text.split()) * 4 // 3


def build_update(skill_name: str, success: list[str], failures: list[str]) -> str | None:
    """Build the new content to append to SKILL.md. Returns None if nothing to add."""
    sections = []

    if success:
        lines = ["", "### Consolidated Examples (auto-generated)", ""]
        for i, block in enumerate(success, 1):
            lines.append(f"**Example {i}** (from positive feedback):")
            lines.append("```")
            lines.append(block)
            lines.append("```")
            lines.append("")
        sections.append("\n".join(lines))

    if failures:
        lines = ["", "### Common Mistakes (auto-generated)", ""]
        for pattern in failures:
            lines.append(f"- {pattern}")
        lines.append("")
        sections.append("\n".join(lines))

    if not sections:
        return None

    new_content = "\n".join(sections)
    tokens = estimate_tokens(new_content)
    if tokens > MAX_NEW_TOKENS:
        # Truncate to fit budget — drop examples from the end
        while estimate_tokens(new_content) > MAX_NEW_TOKENS and success:
            success.pop()
            return build_update(skill_name, success, failures)
        if estimate_tokens(new_content) > MAX_NEW_TOKENS:
            return None

    return new_content


def update_skill_md(skill_name: str, new_content: str, dry_run: bool) -> bool:
    """Append new_content to the skill's SKILL.md. Returns True if written."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        print(f"  SKIP: {skill_path} does not exist")
        return False

    existing = skill_path.read_text(encoding="utf-8")

    # Avoid duplicate consolidations — check for marker
    if "### Consolidated Examples (auto-generated)" in existing:
        # Remove old auto-generated sections before appending new ones
        existing = re.sub(
            r"\n### Consolidated Examples \(auto-generated\).*?(?=\n## |\Z)",
            "", existing, flags=re.DOTALL
        )
    if "### Common Mistakes (auto-generated)" in existing:
        existing = re.sub(
            r"\n### Common Mistakes \(auto-generated\).*?(?=\n## |\Z)",
            "", existing, flags=re.DOTALL
        )

    updated = existing.rstrip() + "\n" + new_content

    if dry_run:
        print(f"  DRY-RUN: Would update {skill_path}")
        print(f"  Added ~{estimate_tokens(new_content)} tokens")
        return False

    skill_path.write_text(updated, encoding="utf-8")
    print(f"  UPDATED: {skill_path} (+{estimate_tokens(new_content)} tokens)")
    return True


def update_skill_meta(skill_name: str, stats: dict, dry_run: bool):
    """Append consolidation record to skill_meta.json."""
    meta_path = SKILLS_DIR / skill_name / "skill_meta.json"
    if not meta_path.exists():
        meta = {"name": skill_name}
    else:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Bump version
    version = meta.get("version", "1.0")
    try:
        major, minor = version.split(".")
        meta["version"] = f"{major}.{int(minor) + 1}"
    except (ValueError, AttributeError):
        meta["version"] = "1.1"

    # Append consolidation history
    history = meta.get("consolidation_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "up_count": stats["up_count"],
        "down_count": stats["down_count"],
        "examples_added": stats["examples_added"],
        "failures_added": stats["failures_added"],
    })
    meta["consolidation_history"] = history

    if dry_run:
        print(f"  DRY-RUN: Would bump {skill_name} to v{meta['version']}")
        return

    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"  META: {skill_name} -> v{meta['version']}")


# ── Main ────────────────────────────────────────────────────────────

def run(args):
    print(f"Fetching feedback from last {args.days} days...")
    entries = fetch_feedback(args.days)
    print(f"Found {len(entries)} rated feedback entries")

    if not entries:
        print("No feedback to process.")
        return

    grouped = group_by_skill(entries)

    if args.skill:
        if args.skill not in grouped:
            print(f"No feedback found for skill '{args.skill}'")
            return
        grouped = {args.skill: grouped[args.skill]}

    results = {}

    for skill_name, data in sorted(grouped.items()):
        total = len(data["up"]) + len(data["down"])
        if total < args.min_feedback:
            continue

        print(f"\n{'='*60}")
        print(f"Skill: {skill_name} ({len(data['up'])} up, {len(data['down'])} down)")

        success = extract_success_patterns(data["up"])
        failures = extract_failure_patterns(data["down"])

        results[skill_name] = {
            "up_count": len(data["up"]),
            "down_count": len(data["down"]),
            "examples_extracted": len(success),
            "failures_extracted": len(failures),
            "examples_added": 0,
            "failures_added": 0,
        }

        if not success and not failures:
            print("  No actionable patterns found")
            continue

        new_content = build_update(skill_name, success, failures)
        if not new_content:
            print("  Update exceeds token budget, skipping")
            continue

        results[skill_name]["examples_added"] = len(success)
        results[skill_name]["failures_added"] = len(failures)

        if success:
            print(f"  Success patterns: {len(success)} code examples")
        if failures:
            print(f"  Failure patterns: {len(failures)} gotchas")

        written = update_skill_md(skill_name, new_content, args.dry_run)
        if written:
            update_skill_meta(skill_name, results[skill_name], args.dry_run)
        elif args.dry_run:
            update_skill_meta(skill_name, results[skill_name], args.dry_run)

    if args.json:
        print(f"\n{'='*60}")
        print(json.dumps(results, indent=2))

    # Summary
    total_updated = sum(1 for r in results.values() if r["examples_added"] or r["failures_added"])
    print(f"\n{'='*60}")
    print(f"Summary: {total_updated} skills updated out of {len(results)} with sufficient feedback")
    if args.dry_run:
        print("(dry-run mode — no files were modified)")


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate chat feedback into SKILL.md updates"
    )
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument("--min-feedback", type=int, default=5, help="Minimum feedback entries per skill (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--skill", type=str, help="Target a specific skill by name")
    parser.add_argument("--json", action="store_true", help="Output analysis as JSON")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
