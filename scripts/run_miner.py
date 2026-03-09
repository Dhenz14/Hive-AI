#!/usr/bin/env python3
"""Run the multi-provider miner for a specified duration.

Wraps hiveai.lora.miner.MinerWorker with scheduling, output collection,
and graceful shutdown. Produces clean JSONL ready for training.

Usage:
    python scripts/run_miner.py --hours 4                    # mine for 4 hours
    python scripts/run_miner.py --hours 24 --output mined.jsonl  # custom output
    python scripts/run_miner.py --pairs 500                  # mine until 500 pairs collected
    python scripts/run_miner.py --providers gemini,groq      # specific providers only

Environment variables (set in .env or export):
    GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, etc.
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT = PROJECT_ROOT / "loras" / "training_data" / "mined_pairs.jsonl"


def load_env():
    """Load .env file if present."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def check_api_keys() -> list[str]:
    """Check which API keys are available."""
    key_map = {
        "gemini": "GEMINI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "groq": "GROQ_API_KEY",
        "cerebras": "CEREBRAS_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "huggingface": "HF_TOKEN",
    }
    available = []
    for provider, env_var in key_map.items():
        if os.environ.get(env_var):
            available.append(provider)
    return available


def main():
    parser = argparse.ArgumentParser(description="Run multi-provider miner")
    parser.add_argument("--hours", type=float, default=1.0, help="Mining duration in hours")
    parser.add_argument("--pairs", type=int, default=0, help="Stop after N pairs (0=time-based)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--providers", type=str, default="", help="Comma-separated provider filter")
    parser.add_argument("--min-quality", type=float, default=0.45, help="Minimum quality score")
    parser.add_argument("--dry-run", action="store_true", help="Check API keys and exit")
    args = parser.parse_args()

    load_env()

    available_providers = check_api_keys()
    print(f"Available providers: {', '.join(available_providers) or 'NONE'}")

    if not available_providers:
        print("ERROR: No API keys found. Set GEMINI_API_KEY, OPENROUTER_API_KEY, etc.", file=sys.stderr)
        print("Check .env.example for required variables.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Dry run — API keys checked, exiting.")
        return

    # Filter providers if specified
    if args.providers:
        requested = set(args.providers.lower().split(","))
        filtered = [p for p in available_providers if p in requested]
        if not filtered:
            print(f"ERROR: None of requested providers ({args.providers}) have API keys", file=sys.stderr)
            sys.exit(1)
        available_providers = filtered
        print(f"Using providers: {', '.join(available_providers)}")

    try:
        from hiveai.lora.miner import MinerWorker
    except ImportError as e:
        print(f"ERROR: Cannot import MinerWorker: {e}", file=sys.stderr)
        print("Make sure you're in the project root and dependencies are installed.", file=sys.stderr)
        sys.exit(1)

    # Setup output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Count existing pairs
    existing_count = 0
    if output_path.exists():
        existing_count = sum(1 for _ in open(output_path, "r", encoding="utf-8"))
        print(f"Appending to existing file ({existing_count} pairs)")

    # Start miner
    print(f"\nStarting miner for {args.hours}h (target: {'unlimited' if not args.pairs else args.pairs} pairs)")
    print(f"Output: {output_path}")
    print(f"Min quality: {args.min_quality}")
    print("-" * 60)

    worker = MinerWorker()
    shutdown = False

    def signal_handler(sig, frame):
        nonlocal shutdown
        print("\nShutdown signal received, stopping miner...")
        shutdown = True
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker.start()

    start_time = time.time()
    duration_secs = args.hours * 3600
    last_report = start_time
    collected = 0

    try:
        while not shutdown:
            elapsed = time.time() - start_time

            # Time limit
            if elapsed >= duration_secs:
                print(f"\nTime limit reached ({args.hours}h)")
                break

            # Pair limit
            if args.pairs > 0 and collected >= args.pairs:
                print(f"\nPair limit reached ({args.pairs})")
                break

            # Check for new pairs from worker (poll DB or stats)
            if hasattr(worker, "stats"):
                collected = getattr(worker.stats, "accepted", 0)

            # Progress report every 5 minutes
            if time.time() - last_report >= 300:
                mins = int(elapsed / 60)
                rate = collected / max(elapsed / 3600, 0.01)
                print(f"  [{mins}m] Collected: {collected} pairs | Rate: {rate:.1f}/hr")
                last_report = time.time()

            time.sleep(10)

    finally:
        worker.stop()

    # Export collected pairs from DB
    print(f"\nMining complete. Collected {collected} pairs in {elapsed/60:.0f} minutes.")

    # Try to export from the distiller's DB
    try:
        from hiveai.lora.distiller import KnowledgeDistiller
        distiller = KnowledgeDistiller.__new__(KnowledgeDistiller)
        # Access DB to get recently mined pairs
        import sqlite3
        db_path = PROJECT_ROOT / "hiveai" / "data" / "knowledge.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT instruction, response FROM training_pairs
                WHERE eligible = 1 AND quality_score >= ?
                ORDER BY created_at DESC LIMIT ?
            """, (args.min_quality, max(collected, 1000)))

            with open(output_path, "a", encoding="utf-8") as f:
                exported = 0
                for instruction, response in cursor.fetchall():
                    pair = {
                        "instruction": instruction,
                        "input": "",
                        "output": response,
                    }
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                    exported += 1

            conn.close()
            total = existing_count + exported
            print(f"Exported {exported} new pairs (total in file: {total})")
        else:
            print(f"WARN: Knowledge DB not found at {db_path}")
    except Exception as e:
        print(f"WARN: Could not export from DB: {e}")
        print("Pairs may be in the Flask app's database — check hiveai/data/knowledge.db")


if __name__ == "__main__":
    main()
