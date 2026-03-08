#!/usr/bin/env python3
"""
Publish HiveAI skills to skills.sh-compatible format.

Packages skill directories into distributable bundles with manifest.json,
README.md, and validation against skills.sh requirements.

Usage:
    python scripts/publish_skills.py --skill rust_async --output dist/skills/
    python scripts/publish_skills.py --all --validate-only
    python scripts/publish_skills.py --all --output dist/skills/ --dry-run
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("publish_skills")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_OUTPUT = PROJECT_ROOT / "dist" / "skills"
AUTHOR = "HiveAI"
REPO_URL = "https://github.com/TheyCallMeHacked/Hive-AI"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_skill(skill_dir: Path) -> list[str]:
    """Validate a skill directory against skills.sh requirements.
    Returns list of error messages (empty = valid).
    """
    errors = []
    skill_md = skill_dir / "SKILL.md"
    meta_json = skill_dir / "skill_meta.json"

    if not skill_dir.is_dir():
        return [f"Not a directory: {skill_dir}"]

    # Must have SKILL.md
    if not skill_md.exists():
        errors.append(f"Missing SKILL.md in {skill_dir.name}")
    else:
        content = skill_md.read_text(encoding="utf-8")
        if len(content.strip()) < 50:
            errors.append(f"SKILL.md too short ({len(content)} chars) in {skill_dir.name}")
        # Should have a heading
        if not content.strip().startswith("#"):
            errors.append(f"SKILL.md should start with a markdown heading in {skill_dir.name}")

    # Must have skill_meta.json
    if not meta_json.exists():
        errors.append(f"Missing skill_meta.json in {skill_dir.name}")
    else:
        try:
            meta = json.loads(meta_json.read_text(encoding="utf-8"))
            # Required fields
            for field in ["name", "description"]:
                if field not in meta:
                    errors.append(f"skill_meta.json missing '{field}' in {skill_dir.name}")
            # Test cases recommended
            if "test_cases" not in meta:
                errors.append(f"skill_meta.json missing 'test_cases' in {skill_dir.name} (recommended)")
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in skill_meta.json: {e} in {skill_dir.name}")

    return errors


def discover_skills() -> list[Path]:
    """Find all valid skill directories under skills/."""
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for child in sorted(SKILLS_DIR.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            skills.append(child)
    return skills


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

def generate_manifest(skill_dir: Path) -> dict:
    """Generate a skills.sh-compatible manifest.json for a skill."""
    meta_path = skill_dir / "skill_meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    skill_name = meta.get("name", skill_dir.name)

    # Detect tags from skill content
    tags = set(meta.get("tags", []))
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8").lower()
        lang_tags = {
            "rust": "rust", "go": "go", "golang": "go",
            "c++": "cpp", "cpp": "cpp", "typescript": "typescript",
            "javascript": "javascript", "hive": "hive", "python": "python",
        }
        for keyword, tag in lang_tags.items():
            if keyword in content:
                tags.add(tag)
        if "async" in content:
            tags.add("async")
        if "concurrency" in content or "goroutine" in content:
            tags.add("concurrency")
        if "security" in content:
            tags.add("security")

    manifest = {
        "name": skill_name,
        "title": meta.get("title", skill_name.replace("_", " ").title()),
        "description": meta.get("description", ""),
        "version": meta.get("version", "1.0.0"),
        "author": AUTHOR,
        "repository": REPO_URL,
        "tags": sorted(tags),
        "agents": ["claude-code", "cursor", "copilot", "gemini"],
        "files": ["SKILL.md", "skill_meta.json"],
    }
    return manifest


def generate_readme(skill_dir: Path, manifest: dict) -> str:
    """Generate a README.md from SKILL.md content and manifest."""
    skill_md = skill_dir / "SKILL.md"
    skill_content = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""

    # Extract first heading as title
    title = manifest.get("title", skill_dir.name)
    description = manifest.get("description", "")
    tags = manifest.get("tags", [])

    readme_parts = [
        f"# {title}",
        "",
        f"> {description}" if description else "",
        "",
        "## Installation",
        "",
        f"```bash",
        f"npx skillsadd {AUTHOR}/{manifest['name']}",
        f"```",
        "",
        "## Tags",
        "",
        ", ".join(f"`{t}`" for t in tags) if tags else "_none_",
        "",
        "---",
        "",
        "## Skill Content",
        "",
        skill_content,
    ]
    return "\n".join(readme_parts)


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------

def package_skill(skill_dir: Path, output_dir: Path, dry_run: bool = False) -> bool:
    """Package a single skill into skills.sh format. Returns True on success."""
    name = skill_dir.name
    dest = output_dir / name

    # Validate first
    errors = validate_skill(skill_dir)
    critical = [e for e in errors if "missing" in e.lower() and "recommended" not in e.lower()]
    if critical:
        for e in critical:
            log.error("FAIL: %s", e)
        return False
    for e in errors:
        if "recommended" in e.lower():
            log.warning("WARN: %s", e)

    manifest = generate_manifest(skill_dir)
    readme = generate_readme(skill_dir, manifest)

    if dry_run:
        log.info("[DRY RUN] Would package %s -> %s", name, dest)
        log.info("  Manifest: %s", json.dumps(manifest, indent=2)[:200])
        return True

    # Create output directory
    dest.mkdir(parents=True, exist_ok=True)

    # Copy SKILL.md
    shutil.copy2(skill_dir / "SKILL.md", dest / "SKILL.md")

    # Copy skill_meta.json
    meta_src = skill_dir / "skill_meta.json"
    if meta_src.exists():
        shutil.copy2(meta_src, dest / "skill_meta.json")

    # Write manifest.json
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Write README.md
    (dest / "README.md").write_text(readme, encoding="utf-8")

    log.info("Packaged %s -> %s (%d files)", name, dest, len(list(dest.iterdir())))
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Package HiveAI skills for skills.sh distribution"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--skill", type=str, help="Package a specific skill by name")
    group.add_argument("--all", action="store_true", help="Package all skills")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help=f"Output directory (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate, do not package")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve skills to process
    if args.all:
        skill_dirs = discover_skills()
        if not skill_dirs:
            log.error("No skills found in %s", SKILLS_DIR)
            sys.exit(1)
    else:
        skill_path = SKILLS_DIR / args.skill
        if not skill_path.is_dir():
            log.error("Skill directory not found: %s", skill_path)
            sys.exit(1)
        skill_dirs = [skill_path]

    output_dir = Path(args.output)

    # Validate-only mode
    if args.validate_only:
        total_errors = 0
        for sd in skill_dirs:
            errors = validate_skill(sd)
            if errors:
                for e in errors:
                    level = "WARN" if "recommended" in e.lower() else "FAIL"
                    print(f"  [{level}] {e}")
                total_errors += len([e for e in errors if "recommended" not in e.lower()])
            else:
                print(f"  [OK] {sd.name}")
        print(f"\n{len(skill_dirs)} skills checked, {total_errors} critical errors")
        sys.exit(1 if total_errors > 0 else 0)

    # Package skills
    success = 0
    failed = 0
    for sd in skill_dirs:
        if package_skill(sd, output_dir, dry_run=args.dry_run):
            success += 1
        else:
            failed += 1

    print(f"\nPackaged: {success}, Failed: {failed}, Output: {output_dir}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
