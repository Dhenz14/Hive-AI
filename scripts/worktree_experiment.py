#!/usr/bin/env python3
"""
Git worktree manager for isolated training experiments.

Creates isolated git worktrees so you can run parallel training experiments
(e.g., v8-rust-test, v8-go-test) without branch switching or workspace conflicts.

Usage:
    python scripts/worktree_experiment.py --name v8-rust-test
    python scripts/worktree_experiment.py --name v8-rust-test --branch experiment/v8-rust
    python scripts/worktree_experiment.py --name v8-rust-test --cleanup
    python scripts/worktree_experiment.py --list

Linux-targeted (WSL2 training environment).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKTREES_DIR = PROJECT_ROOT / "worktrees"

# Config files to copy into new worktrees (relative to project root)
CONFIG_FILES = [
    "scripts/train_v5.py",
    "scripts/build_replay_buffer.py",
    "scripts/prepare_category_data.py",
    "scripts/merge_category_loras.py",
    "scripts/quick_eval.py",
    "loras/training_data",  # symlink or copy
]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result


def create_worktree(name: str, branch: str | None = None) -> Path:
    """Create a git worktree for an experiment."""
    worktree_path = WORKTREES_DIR / name

    if worktree_path.exists():
        print(f"ERROR: Worktree '{name}' already exists at {worktree_path}")
        print("  Use --cleanup to remove it first, or pick a different name.")
        sys.exit(1)

    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)

    # Determine branch name
    branch_name = branch or f"experiment/{name}"

    # Check if branch exists
    result = run(["git", "branch", "--list", branch_name], cwd=PROJECT_ROOT)
    branch_exists = branch_name in result.stdout

    # Create worktree
    cmd = ["git", "worktree", "add"]
    if branch_exists:
        cmd += [str(worktree_path), branch_name]
    else:
        cmd += ["-b", branch_name, str(worktree_path)]

    result = run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"ERROR: git worktree add failed:\n{result.stderr}")
        sys.exit(1)

    print(f"Created worktree: {worktree_path}")
    print(f"Branch: {branch_name}")

    # Copy/symlink config files that might not be in git
    _copy_configs(worktree_path)

    # Create convenience directories
    (worktree_path / "loras").mkdir(exist_ok=True)
    (worktree_path / "evals").mkdir(exist_ok=True)

    print(f"\nReady. To use:")
    print(f"  cd {worktree_path}")
    print(f"  python scripts/train_v5.py --data loras/training_data/v7.jsonl ...")
    print(f"\nTo clean up when done:")
    print(f"  python scripts/worktree_experiment.py --name {name} --cleanup")

    return worktree_path


def _copy_configs(worktree_path: Path):
    """Copy essential config files to the worktree."""
    copied = 0
    for rel_path in CONFIG_FILES:
        src = PROJECT_ROOT / rel_path
        dst = worktree_path / rel_path

        if not src.exists():
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            # Symlink directories (training data can be large)
            if not dst.exists():
                try:
                    dst.symlink_to(src)
                    copied += 1
                except OSError:
                    # Fallback: copy if symlinks not supported
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    copied += 1
        elif src.is_file():
            # Files are already tracked by git, just verify they exist
            if dst.exists():
                copied += 1
            else:
                shutil.copy2(src, dst)
                copied += 1

    print(f"Config files verified/copied: {copied}/{len(CONFIG_FILES)}")


def cleanup_worktree(name: str):
    """Remove a git worktree and optionally its branch."""
    worktree_path = WORKTREES_DIR / name

    if not worktree_path.exists():
        print(f"Worktree '{name}' not found at {worktree_path}")
        sys.exit(1)

    # Remove the worktree
    result = run(["git", "worktree", "remove", str(worktree_path), "--force"],
                 cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"WARNING: git worktree remove failed, cleaning up manually:\n{result.stderr}")
        shutil.rmtree(worktree_path, ignore_errors=True)
        run(["git", "worktree", "prune"], cwd=PROJECT_ROOT)

    print(f"Removed worktree: {worktree_path}")

    # Clean up empty worktrees dir
    if WORKTREES_DIR.exists() and not any(WORKTREES_DIR.iterdir()):
        WORKTREES_DIR.rmdir()
        print("Removed empty worktrees/ directory")


def list_worktrees():
    """List all active git worktrees."""
    result = run(["git", "worktree", "list", "--porcelain"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)

    entries = result.stdout.strip().split("\n\n")
    print(f"Active worktrees ({len(entries)}):")
    for entry in entries:
        lines = entry.strip().split("\n")
        for line in lines:
            print(f"  {line}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Git worktree manager for isolated training experiments"
    )
    parser.add_argument("--name", type=str, help="Experiment name (e.g., v8-rust-test)")
    parser.add_argument("--branch", type=str, default=None,
                        help="Git branch name (default: experiment/<name>)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove the worktree instead of creating it")
    parser.add_argument("--list", action="store_true",
                        help="List all active worktrees")
    args = parser.parse_args()

    if args.list:
        list_worktrees()
        return

    if not args.name:
        parser.error("--name is required (unless using --list)")

    if args.cleanup:
        cleanup_worktree(args.name)
    else:
        create_worktree(args.name, args.branch)


if __name__ == "__main__":
    main()
