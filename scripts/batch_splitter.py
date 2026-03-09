"""Batch Splitter: Split large JSONL into micro-training batches.

Usage:
    python scripts/batch_splitter.py datasets/thinking_all.jsonl --batch-size 500
    python scripts/batch_splitter.py datasets/thinking_all.jsonl --batch-size 500 --output-dir datasets

Output:
    datasets/thinking_all_batch1.jsonl (500 pairs)
    datasets/thinking_all_batch2.jsonl (500 pairs)
    datasets/thinking_all_batch3.jsonl (remaining)
    datasets/thinking_all_manifest.json (batch metadata)
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Split JSONL into micro-training batches")
    parser.add_argument("input", help="Path to input JSONL file")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Number of pairs per batch (default: 500)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: same as input)")
    parser.add_argument("--shuffle", action="store_true", default=True,
                        help="Shuffle before splitting (default: True)")
    parser.add_argument("--no-shuffle", action="store_true",
                        help="Disable shuffling (preserve order)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for shuffling (default: 42)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Load all samples
    samples = []
    with open(args.input, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                samples.append(sample)
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping line {i}: {e}")

    if not samples:
        print("ERROR: No valid samples found")
        sys.exit(1)

    print(f"Loaded {len(samples)} samples from {args.input}")

    # Shuffle
    if args.shuffle and not args.no_shuffle:
        random.seed(args.seed)
        random.shuffle(samples)
        print(f"Shuffled with seed={args.seed}")

    # Split into batches
    batches = []
    for i in range(0, len(samples), args.batch_size):
        batches.append(samples[i:i + args.batch_size])

    print(f"Split into {len(batches)} batches of up to {args.batch_size}")

    # Determine output paths
    input_path = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    base_name = input_path.stem

    os.makedirs(output_dir, exist_ok=True)

    # Write batches
    batch_files = []
    for batch_idx, batch in enumerate(batches, 1):
        batch_path = output_dir / f"{base_name}_batch{batch_idx}.jsonl"
        with open(batch_path, "w", encoding="utf-8") as f:
            for sample in batch:
                # Strip metadata to prevent pyarrow crashes
                clean = {k: v for k, v in sample.items() if k != "metadata"}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

        batch_files.append({
            "batch": batch_idx,
            "file": str(batch_path),
            "count": len(batch),
            "status": "pending",
        })
        print(f"  Batch {batch_idx}: {batch_path} ({len(batch)} pairs)")

    # Write manifest
    manifest = {
        "source": str(args.input),
        "total_samples": len(samples),
        "batch_size": args.batch_size,
        "num_batches": len(batches),
        "seed": args.seed if (args.shuffle and not args.no_shuffle) else None,
        "batches": batch_files,
    }
    manifest_path = output_dir / f"{base_name}_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest: {manifest_path}")
    print(f"Done! {len(batches)} batches ready for micro-training.")


if __name__ == "__main__":
    main()
