#!/usr/bin/env python3
"""
Prepare vision fine-tuning data for Unsloth's FastVisionModel.

Scans a directory of image + text pairs, validates them, and outputs JSONL
in the format required by FastVisionModel training.

Directory structure expected:
    data/vision/
        screenshot_001.png
        screenshot_001.txt        # paired text file (instruction + output)
        architecture_diagram.jpg
        architecture_diagram.txt
        ...

Text file format (each .txt paired with an image):
    First line: instruction (what to ask about the image)
    Remaining lines: expected output (description, code, analysis)

    Example:
        Describe the architecture shown in this diagram.
        This diagram shows a microservices architecture with three layers...

Output JSONL format (for Unsloth FastVisionModel):
    {"image": "path/to/img.png", "instruction": "...", "output": "..."}

Data collection guidelines (for future reference):
    1. Screenshots of code + explanation of what the code does
    2. Architecture diagrams + structured description of components
    3. Terminal output screenshots + explanation of what happened
    4. UI mockups + description of layout and interactions
    5. Error screenshots + diagnosis and fix
    6. Aim for 500+ pairs minimum for meaningful fine-tuning
    7. Images should be 224x224 to 1024x1024 (will be resized by model)
    8. PNG or JPEG only; keep file sizes under 5MB each
    9. Instructions should be specific, not generic ("What is this?")
   10. Outputs should be detailed (100+ words for descriptions)

Usage:
    # Scan and validate
    python scripts/prepare_vision_data.py --input-dir data/vision/ --validate

    # Generate training JSONL
    python scripts/prepare_vision_data.py --input-dir data/vision/ --output vision_pairs.jsonl

    # Show statistics
    python scripts/prepare_vision_data.py --input-dir data/vision/ --stats
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_IMAGE_SIZE_MB = 10
MIN_TEXT_LENGTH = 20
MIN_OUTPUT_LENGTH = 30


def find_pairs(input_dir: Path) -> list[dict]:
    """Scan directory for image + text file pairs.

    For each image file, looks for a .txt file with the same stem.
    Returns list of {"image": path, "text": path} dicts.
    """
    if not input_dir.exists():
        log.error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)

    pairs = []
    images = sorted(
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )

    for img in images:
        txt = img.with_suffix(".txt")
        if txt.exists():
            pairs.append({"image": img, "text": txt})
        else:
            log.warning(f"No text pair for image: {img.name}")

    # Also check for orphan text files
    txt_files = {f.stem for f in input_dir.iterdir() if f.suffix == ".txt"}
    img_files = {f.stem for f in images}
    orphan_txts = txt_files - img_files
    for stem in sorted(orphan_txts):
        log.warning(f"Orphan text file (no image): {stem}.txt")

    return pairs


def parse_text_file(text_path: Path) -> tuple[str, str]:
    """Parse a text file into (instruction, output).

    First line = instruction, remaining lines = output.
    """
    content = text_path.read_text(encoding="utf-8").strip()
    if not content:
        return "", ""

    lines = content.split("\n", 1)
    instruction = lines[0].strip()
    output = lines[1].strip() if len(lines) > 1 else ""
    return instruction, output


def validate_pair(pair: dict) -> list[str]:
    """Validate a single image + text pair. Returns list of issues (empty = valid)."""
    issues = []
    img_path: Path = pair["image"]
    txt_path: Path = pair["text"]

    # Image checks
    if not img_path.exists():
        issues.append(f"Image missing: {img_path.name}")
        return issues

    img_size_mb = img_path.stat().st_size / (1024 * 1024)
    if img_size_mb > MAX_IMAGE_SIZE_MB:
        issues.append(f"Image too large: {img_path.name} ({img_size_mb:.1f} MB > {MAX_IMAGE_SIZE_MB} MB)")
    if img_size_mb < 0.001:
        issues.append(f"Image suspiciously small: {img_path.name} ({img_size_mb * 1024:.1f} KB)")

    # Text checks
    instruction, output = parse_text_file(txt_path)
    if len(instruction) < MIN_TEXT_LENGTH:
        issues.append(f"Instruction too short ({len(instruction)} chars): {txt_path.name}")
    if len(output) < MIN_OUTPUT_LENGTH:
        issues.append(f"Output too short ({len(output)} chars): {txt_path.name}")

    return issues


def validate_all(pairs: list[dict]) -> tuple[int, int]:
    """Validate all pairs and log issues. Returns (valid_count, total_count)."""
    valid = 0
    for pair in pairs:
        issues = validate_pair(pair)
        if issues:
            for issue in issues:
                log.warning(f"  {issue}")
        else:
            valid += 1

    log.info(f"Validation: {valid}/{len(pairs)} pairs valid")
    return valid, len(pairs)


def print_stats(pairs: list[dict]):
    """Print statistics about the dataset."""
    if not pairs:
        log.info("No pairs found.")
        return

    img_sizes = []
    txt_lengths = []
    instruction_lengths = []
    output_lengths = []
    ext_counts: dict[str, int] = {}

    for pair in pairs:
        img_path: Path = pair["image"]
        img_sizes.append(img_path.stat().st_size / (1024 * 1024))

        ext = img_path.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

        instruction, output = parse_text_file(pair["text"])
        instruction_lengths.append(len(instruction))
        output_lengths.append(len(output))
        txt_lengths.append(len(instruction) + len(output))

    print(f"\n{'='*50}")
    print(f"  Vision Dataset Statistics")
    print(f"{'='*50}")
    print(f"  Total pairs:        {len(pairs)}")
    print(f"  Image formats:      {', '.join(f'{k}: {v}' for k, v in sorted(ext_counts.items()))}")
    print(f"  Image sizes:        {min(img_sizes):.2f} - {max(img_sizes):.2f} MB "
          f"(avg {sum(img_sizes)/len(img_sizes):.2f} MB)")
    print(f"  Total image data:   {sum(img_sizes):.1f} MB")
    print(f"  Instruction length: {min(instruction_lengths)} - {max(instruction_lengths)} chars "
          f"(avg {sum(instruction_lengths)//len(instruction_lengths)})")
    print(f"  Output length:      {min(output_lengths)} - {max(output_lengths)} chars "
          f"(avg {sum(output_lengths)//len(output_lengths)})")
    print(f"{'='*50}\n")


def generate_jsonl(pairs: list[dict], output_path: Path, use_absolute: bool = False):
    """Generate training JSONL from validated pairs.

    Output format for Unsloth FastVisionModel:
        {"image": "path/to/img.png", "instruction": "...", "output": "..."}
    """
    written = 0
    skipped = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            issues = validate_pair(pair)
            if issues:
                skipped += 1
                continue

            instruction, output = parse_text_file(pair["text"])
            img_path = str(pair["image"].resolve()) if use_absolute else str(pair["image"])

            record = {
                "image": img_path,
                "instruction": instruction,
                "output": output,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    log.info(f"Written {written} pairs to {output_path} (skipped {skipped} invalid)")
    return written


def main():
    parser = argparse.ArgumentParser(
        description="Prepare vision fine-tuning data for Unsloth FastVisionModel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input-dir", required=True,
                        help="Directory containing image + text file pairs")
    parser.add_argument("--output", default="vision_pairs.jsonl",
                        help="Output JSONL path (default: vision_pairs.jsonl)")
    parser.add_argument("--validate", action="store_true",
                        help="Validate all pairs and report issues")
    parser.add_argument("--stats", action="store_true",
                        help="Print dataset statistics")
    parser.add_argument("--absolute-paths", action="store_true",
                        help="Use absolute paths in output JSONL")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    pairs = find_pairs(input_dir)
    log.info(f"Found {len(pairs)} image+text pairs in {input_dir}")

    if not pairs:
        log.warning("No pairs found. Expected: image files (.png/.jpg) with matching .txt files")
        sys.exit(0)

    if args.stats:
        print_stats(pairs)
        if not args.validate and args.output == "vision_pairs.jsonl":
            return

    if args.validate:
        valid, total = validate_all(pairs)
        if valid == 0:
            log.error("No valid pairs. Fix issues above before generating JSONL.")
            sys.exit(1)
        if not args.stats and args.output == "vision_pairs.jsonl" and not any(
            a in sys.argv for a in ["--output"]
        ):
            return

    output_path = Path(args.output)
    written = generate_jsonl(pairs, output_path, use_absolute=args.absolute_paths)
    if written == 0:
        log.error("No valid pairs written. Run with --validate to see issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()
