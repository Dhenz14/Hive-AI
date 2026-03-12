#!/usr/bin/env python3
"""Retag JSONL training data with a style field for v3.0 style token routing.

Usage:
    # Tag agentic training data
    python scripts/retag_style.py --input datasets/v5_agentic.jsonl --output datasets/v5_agentic_tagged.jsonl --style agentic

    # Tag replay data as direct
    python scripts/retag_style.py --input replay/sampled.jsonl --output replay/sampled_tagged.jsonl --style direct

    # In-place (overwrites input)
    python scripts/retag_style.py --input data.jsonl --style agentic --inplace
"""
import argparse
import json
import sys
from pathlib import Path


def retag(input_path: str, output_path: str, style: str) -> int:
    """Add or overwrite 'style' field in every JSONL record. Returns count."""
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                record["style"] = style
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"WARNING: skipping malformed line: {e}", file=sys.stderr)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Add style field to JSONL training data")
    parser.add_argument("--input", required=True, help="Input JSONL path")
    parser.add_argument("--output", default=None, help="Output JSONL path (default: prints to stdout info)")
    parser.add_argument("--style", required=True, choices=["direct", "agentic"],
                        help="Style tag to apply")
    parser.add_argument("--inplace", action="store_true",
                        help="Overwrite input file in place")
    args = parser.parse_args()

    if args.inplace:
        output = args.input
    elif args.output:
        output = args.output
    else:
        print("ERROR: specify --output or --inplace", file=sys.stderr)
        sys.exit(1)

    count = retag(args.input, output, args.style)
    print(f"Tagged {count} records with style='{args.style}' -> {output}")


if __name__ == "__main__":
    main()
