"""
scripts/run_all_phases.py

Runs all 3 mining phases sequentially. Designed to be launched once and left
running for days. Resumable — each phase skips already-mined topics.

Usage:
    python scripts/run_all_phases.py
"""
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = str(PROJECT_ROOT / "scripts" / "brain_mine.py")


def run_phase(label, args):
    print(f"\n{'='*60}")
    print(f"  STARTING: {label}")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Command: python scripts/brain_mine.py {' '.join(args)}")
    print(f"{'='*60}\n")

    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print(f"\n*** {label} exited with code {result.returncode} ***")
        print("Continuing to next phase anyway (progress is saved).\n")
    else:
        print(f"\n*** {label} completed successfully ***\n")

    return result.returncode


def main():
    start = time.time()
    print(f"Full mining pipeline started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"This will run Phase 1 -> Phase 2 -> Phase 3 sequentially.")
    print(f"All progress is resumable. Safe to interrupt and restart.\n")

    # Phase 1: Fast breadth (qwen3:14b, think:false)
    run_phase("Phase 1 - Fast Breadth (qwen3:14b)", ["--fast", "--pairs", "6", "--workers", "3"])

    # Phase 2: Deep review (qwen3:32b, think:true, 3 workers)
    run_phase("Phase 2 - Deep Review (qwen3:32b)", ["--review", "--workers", "3"])

    # Phase 3: o1-style reasoning (qwen3:32b, think:true, 3 workers)
    run_phase("Phase 3 - o1 Reasoning (qwen3:32b)", ["--o1", "--workers", "3"])

    elapsed = time.time() - start
    hours = elapsed / 3600
    print(f"\n{'='*60}")
    print(f"  ALL PHASES COMPLETE")
    print(f"  Total time: {hours:.1f} hours ({hours/24:.1f} days)")
    print(f"  Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Show final status
    run_phase("Final Status Check", ["--status"])


if __name__ == "__main__":
    main()
