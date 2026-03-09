#!/usr/bin/env python3
"""Convert skill modules (SKILL.md files) into training pairs.

Parses each SKILL.md -> extracts sections with code examples ->
generates instruction/output pairs using multiple question templates.

Usage:
    python scripts/skills_to_pairs.py                     # dry run (stats only)
    python scripts/skills_to_pairs.py --export            # write JSONL
    python scripts/skills_to_pairs.py --export --output skills_pairs.jsonl
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_OUTPUT = PROJECT_ROOT / "loras" / "training_data" / "skills_pairs.jsonl"

# Question templates for converting skill sections to training pairs
TEMPLATES = [
    # Explain/teach
    "Explain {topic} in detail. Include code examples and common pitfalls.",
    "How does {topic} work? Provide a thorough explanation with examples.",
    "What are the key concepts behind {topic}? Show practical code examples.",
    # Implementation
    "Show me how to implement {topic} with production-quality code.",
    "Write a complete example demonstrating {topic}. Include error handling and best practices.",
    # Debugging/mistakes
    "What are the most common mistakes when working with {topic}? How do I avoid them?",
    "I'm having trouble with {topic}. What should I check and how do I debug it?",
    # Comparison/tradeoffs
    "What are the tradeoffs when using {topic}? When should I use it vs alternatives?",
]

# Hive-specific templates (for Hive skill modules)
HIVE_TEMPLATES = [
    "How do I {topic} on the Hive blockchain? Show the code using dhive or beem.",
    "Explain {topic} in the context of Hive. Include API calls and transaction examples.",
    "What's the correct way to handle {topic} on Hive? Show common mistakes and best practices.",
]


def parse_skill_file(filepath: Path) -> list[dict]:
    """Parse a SKILL.md file into sections with headers and content."""
    text = filepath.read_text(encoding="utf-8")
    sections = []

    # Split by ## headers (level 2 and 3)
    parts = re.split(r"^(#{2,3}\s+.+)$", text, flags=re.MULTILINE)

    current_header = None
    current_body = ""

    for part in parts:
        if re.match(r"^#{2,3}\s+", part):
            # Save previous section
            if current_header and current_body.strip():
                sections.append({
                    "header": current_header.strip("# \n"),
                    "body": current_body.strip(),
                    "has_code": "```" in current_body,
                })
            current_header = part
            current_body = ""
        else:
            current_body += part

    # Save last section
    if current_header and current_body.strip():
        sections.append({
            "header": current_header.strip("# \n"),
            "body": current_body.strip(),
            "has_code": "```" in current_body,
        })

    return sections


def section_to_pairs(section: dict, skill_name: str, is_hive: bool) -> list[dict]:
    """Convert a skill section into training pairs using templates."""
    pairs = []
    header = section["header"]
    body = section["body"]

    # Skip very short sections (likely just headers or links)
    if len(body) < 100:
        return []

    # Skip table-of-contents or index sections
    if header.lower() in ("table of contents", "index", "overview") and not section["has_code"]:
        return []

    topic = header.lower().replace("_", " ").strip()

    # Pick templates based on domain and content
    templates = list(TEMPLATES)
    if is_hive:
        templates.extend(HIVE_TEMPLATES)

    # Only use 2-3 templates per section to avoid bloat
    # Prefer implementation templates if section has code
    if section["has_code"]:
        selected = [t for t in templates if "implement" in t.lower() or "show" in t.lower() or "write" in t.lower()][:2]
        selected.append(templates[0])  # Always include explain template
    else:
        selected = templates[:3]  # Explain + how + key concepts

    for template in selected:
        instruction = template.format(topic=topic)
        # Build output: use skill section body as the authoritative answer
        output = body

        # Add skill context header if not already clear
        if skill_name.lower() not in body[:200].lower():
            context = f"## {header}\n\n"
            output = context + output

        pairs.append({
            "instruction": instruction,
            "input": "",
            "output": output,
            "_skill": skill_name,
            "_section": header,
        })

    return pairs


def instruction_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def deduplicate(pairs: list[dict]) -> list[dict]:
    seen = {}
    for pair in pairs:
        h = instruction_hash(pair["instruction"])
        if h not in seen or len(pair["output"]) > len(seen[h]["output"]):
            seen[h] = pair
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser(description="Convert SKILL.md files to training pairs")
    parser.add_argument("--export", action="store_true", help="Write output JSONL")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--skills-dir", type=str, default=str(SKILLS_DIR))
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.exists():
        print(f"ERROR: Skills directory not found: {skills_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover all SKILL.md files
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    # Also check for flat .md files (hive-architecture.md style)
    flat_skills = sorted(skills_dir.glob("*.md"))
    all_skill_files = list(set(skill_files + flat_skills))

    print(f"Discovered {len(all_skill_files)} skill files")

    all_pairs = []
    skill_counts = {}

    for filepath in all_skill_files:
        skill_name = filepath.parent.name if filepath.name == "SKILL.md" else filepath.stem
        is_hive = "hive" in skill_name.lower()

        sections = parse_skill_file(filepath)
        pairs = []
        for section in sections:
            pairs.extend(section_to_pairs(section, skill_name, is_hive))

        if pairs:
            skill_counts[skill_name] = len(pairs)
            all_pairs.extend(pairs)
            print(f"  {skill_name}: {len(sections)} sections -> {len(pairs)} pairs")

    print(f"\nExtracted {len(all_pairs)} raw pairs from {len(skill_counts)} skills")

    # Deduplicate
    before_dedup = len(all_pairs)
    all_pairs = deduplicate(all_pairs)
    print(f"Dedup: {before_dedup - len(all_pairs)} removed, {len(all_pairs)} unique pairs")

    # Domain breakdown
    hive_pairs = sum(1 for p in all_pairs if "hive" in p.get("_skill", "").lower())
    print(f"\nHive domain: {hive_pairs} pairs")
    print(f"Other domains: {len(all_pairs) - hive_pairs} pairs")

    if args.export:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for pair in all_pairs:
                clean = {
                    "instruction": pair["instruction"],
                    "input": pair["input"],
                    "output": pair["output"],
                }
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\nExported {len(all_pairs)} pairs to {output_path} ({size_mb:.1f} MB)")
    else:
        print(f"\nDry run — use --export to write JSONL")


if __name__ == "__main__":
    main()
