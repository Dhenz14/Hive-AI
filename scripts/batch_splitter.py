#!/usr/bin/env python3
"""Split large JSONL training files into micro-training batches.

Usage:
    python scripts/batch_splitter.py INPUT.jsonl [--batch-size 500] [--output-dir datasets/batches] [--seed 42] [--shuffle]

Output:
    datasets/batches/INPUT_batch1.jsonl (500 pairs)
    datasets/batches/INPUT_batch2.jsonl (500 pairs)
    ...
    datasets/batches/INPUT_manifest.json (metadata)
"""

import json, os, sys, argparse, random
from pathlib import Path


def load_jsonl(path):
    """Load JSONL file, skip blank lines and invalid JSON."""
    pairs = []
    errors = 0
    with open(path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Strip metadata field if present (breaks pyarrow)
                obj.pop('metadata', None)
                pairs.append(obj)
            except json.JSONDecodeError:
                errors += 1
                if errors <= 3:
                    print(f"  WARN: Skipping invalid JSON on line {i}")
    if errors:
        print(f"  Skipped {errors} invalid lines total")
    return pairs


def split_batches(pairs, batch_size):
    """Split pairs into batches of batch_size."""
    batches = []
    for i in range(0, len(pairs), batch_size):
        batches.append(pairs[i:i + batch_size])
    return batches


def write_batch(batch, path):
    """Write a batch to JSONL file."""
    with open(path, 'w', encoding='utf-8') as f:
        for pair in batch:
            f.write(json.dumps(pair, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description="Split JSONL into micro-training batches")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("--batch-size", type=int, default=500, help="Pairs per batch (default: 500)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same dir as input)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for shuffling")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle before splitting")
    parser.add_argument("--prefix", default=None, help="Batch filename prefix (default: input filename)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    # Determine output directory
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading {input_path}...")
    pairs = load_jsonl(input_path)
    print(f"  Loaded {len(pairs)} pairs")

    if len(pairs) == 0:
        print("ERROR: No valid pairs found")
        sys.exit(1)

    # Shuffle if requested
    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(pairs)
        print(f"  Shuffled with seed={args.seed}")

    # Split into batches
    batches = split_batches(pairs, args.batch_size)
    print(f"  Split into {len(batches)} batches of up to {args.batch_size}")

    # Write batches
    prefix = args.prefix or input_path.stem
    batch_files = []
    for i, batch in enumerate(batches, 1):
        batch_name = f"{prefix}_batch{i}.jsonl"
        batch_path = output_dir / batch_name
        write_batch(batch, batch_path)
        batch_files.append({
            "file": str(batch_path),
            "name": batch_name,
            "count": len(batch),
            "batch_number": i,
        })
        print(f"  Wrote {batch_name} ({len(batch)} pairs)")

    # Write manifest
    manifest = {
        "source": str(input_path),
        "total_pairs": len(pairs),
        "batch_size": args.batch_size,
        "num_batches": len(batches),
        "shuffled": args.shuffle,
        "seed": args.seed if args.shuffle else None,
        "batches": batch_files,
    }
    manifest_path = output_dir / f"{prefix}_manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  Manifest: {manifest_path}")
    print(f"  Total: {len(pairs)} pairs \u2192 {len(batches)} batches")


if __name__ == "__main__":
    main()
