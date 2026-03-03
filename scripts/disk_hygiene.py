#!/usr/bin/env python3
"""
HiveAI Disk Hygiene — run periodically to prevent disk bloat.

Usage:
    python scripts/disk_hygiene.py          # Report only (safe)
    python scripts/disk_hygiene.py --clean  # Delete detected garbage

Checks:
  1. WSL crash dumps (wsl-crashes/*.dmp)
  2. HuggingFace cache (duplicate downloads)
  3. pip cache
  4. Duplicate/orphaned model files
  5. WSL vhdx bloat (reports only — compact manually)
  6. Downloads folder references in source code (should be zero)
"""
import os
import sys
import glob
import shutil
import subprocess
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────
USER_HOME = Path(os.path.expanduser("~"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# Models we NEED on Windows (everything else is garbage)
NEEDED_GGUFS = {"Qwen3.5-35B-A3B-Q4_K_M.gguf"}
NEEDED_MODEL_DIRS = {"qwen3.5-35b-a3b"}  # Only the one with the GGUF

# WSL models we NEED (everything else should be deleted)
WSL_NEEDED_MODELS = {"qwen3.5-35b-a3b", "qwen3.5-35b-a3b-v3.5-rebuild"}

# Paths that should NEVER appear in source code
BANNED_SOURCE_PATHS = ["Downloads", "C:\\Users\\theyc\\Downloads", "/mnt/c/Users/theyc/Downloads"]

WARN_THRESHOLD_GB = 10  # Warn if any single item exceeds this
VHDX_WARN_RATIO = 2.0   # Warn if vhdx is >2x actual WSL usage


def sizeof_fmt(num_bytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def dir_size(path):
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def check_crash_dumps():
    """Check for WSL crash dumps."""
    crash_dir = USER_HOME / "AppData" / "Local" / "Temp" / "wsl-crashes"
    issues = []
    if crash_dir.exists():
        dumps = list(crash_dir.glob("*.dmp"))
        if dumps:
            total = sum(d.stat().st_size for d in dumps)
            issues.append({
                "type": "crash_dumps",
                "path": str(crash_dir),
                "count": len(dumps),
                "size": total,
                "message": f"{len(dumps)} WSL crash dumps ({sizeof_fmt(total)})",
                "clean_path": str(crash_dir),
            })
    return issues


def check_hf_cache():
    """Check HuggingFace cache for bloat."""
    issues = []
    hf_hub = USER_HOME / ".cache" / "huggingface" / "hub"
    if hf_hub.exists():
        size = dir_size(hf_hub)
        if size > 500 * 1024 * 1024:  # > 500 MB
            issues.append({
                "type": "hf_cache",
                "path": str(hf_hub),
                "size": size,
                "message": f"HuggingFace hub cache: {sizeof_fmt(size)} (models are re-downloadable)",
                "clean_path": str(hf_hub),
            })
    return issues


def check_pip_cache():
    """Check pip cache."""
    issues = []
    pip_cache = USER_HOME / "AppData" / "Local" / "pip" / "cache"
    if pip_cache.exists():
        size = dir_size(pip_cache)
        if size > 500 * 1024 * 1024:
            issues.append({
                "type": "pip_cache",
                "path": str(pip_cache),
                "size": size,
                "message": f"pip cache: {sizeof_fmt(size)}",
                "clean_path": str(pip_cache),
            })
    return issues


def check_orphan_models():
    """Check for duplicate or unnecessary model files on Windows."""
    issues = []
    if not MODELS_DIR.exists():
        return issues

    # Check for model directories we don't need
    for d in MODELS_DIR.iterdir():
        if d.is_dir() and d.name not in NEEDED_MODEL_DIRS:
            size = dir_size(d)
            if size > 100 * 1024 * 1024:
                issues.append({
                    "type": "orphan_model_dir",
                    "path": str(d),
                    "size": size,
                    "message": f"Orphan model dir: {d.name} ({sizeof_fmt(size)})",
                    "clean_path": str(d),
                })

    # Check for GGUF files we don't need
    model_dir = MODELS_DIR / "qwen3.5-35b-a3b"
    if model_dir.exists():
        for gguf in model_dir.glob("*.gguf"):
            if gguf.name not in NEEDED_GGUFS:
                issues.append({
                    "type": "orphan_gguf",
                    "path": str(gguf),
                    "size": gguf.stat().st_size,
                    "message": f"Unneeded GGUF: {gguf.name} ({sizeof_fmt(gguf.stat().st_size)})",
                    "clean_path": str(gguf),
                })

        # Check for redundant hf/ or .cache/ dirs
        for subdir_name in ("hf", ".cache"):
            subdir = model_dir / subdir_name
            if subdir.exists():
                size = dir_size(subdir)
                if size > 100 * 1024 * 1024:
                    issues.append({
                        "type": "redundant_safetensors",
                        "path": str(subdir),
                        "size": size,
                        "message": f"Redundant {subdir_name}/: {sizeof_fmt(size)} (originals in WSL)",
                        "clean_path": str(subdir),
                    })
    return issues


def check_vhdx_bloat():
    """Report WSL vhdx size vs actual usage."""
    issues = []
    vhdx_pattern = str(USER_HOME / "AppData" / "Local" / "wsl" / "*" / "ext4.vhdx")
    for vhdx in glob.glob(vhdx_pattern):
        vhdx_size = os.path.getsize(vhdx)
        # Try to get WSL actual usage
        try:
            result = subprocess.run(
                ["wsl", "-d", "Ubuntu-24.04", "--", "df", "--output=used", "-B1", "/"],
                capture_output=True, text=True, timeout=10,
            )
            used_bytes = int(result.stdout.strip().split("\n")[-1].strip())
            ratio = vhdx_size / used_bytes if used_bytes > 0 else 999
            if ratio > VHDX_WARN_RATIO:
                issues.append({
                    "type": "vhdx_bloat",
                    "path": vhdx,
                    "size": vhdx_size,
                    "message": (
                        f"WSL vhdx bloated: {sizeof_fmt(vhdx_size)} on disk vs "
                        f"{sizeof_fmt(used_bytes)} actual ({ratio:.1f}x). "
                        f"Run: wsl --shutdown && diskpart /s scripts/compact_wsl.txt"
                    ),
                })
        except Exception:
            if vhdx_size > 100 * 1024**3:  # > 100 GB
                issues.append({
                    "type": "vhdx_bloat",
                    "path": vhdx,
                    "size": vhdx_size,
                    "message": f"WSL vhdx: {sizeof_fmt(vhdx_size)} (couldn't check actual usage)",
                })
    return issues


def check_downloads_references():
    """Scan source code for any references to Downloads folder."""
    issues = []
    source_extensions = {".py", ".json", ".env", ".yaml", ".yml", ".toml", ".cfg", ".sh", ".bat", ".ps1"}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "loras"}

    self_name = os.path.basename(__file__)
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname == self_name:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in source_extensions:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        # Skip tokenizer files (they legitimately contain "Downloads" as a vocab token)
                        if "tokenizer" in fname.lower() or "vocab" in fname.lower():
                            continue
                        # Skip comments and log messages using Downloads as a verb
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        # Check for actual path references to Downloads folder
                        if "Downloads/" in line or "Downloads\\" in line or "/Downloads/" in line:
                            issues.append({
                                "type": "downloads_reference",
                                "path": fpath,
                                "size": 0,
                                "message": f"Downloads path ref in {os.path.relpath(fpath, PROJECT_ROOT)}:{i}: {stripped[:100]}",
                            })
            except (OSError, UnicodeDecodeError):
                pass
    return issues


def main():
    clean_mode = "--clean" in sys.argv

    print("=" * 60)
    print("  HiveAI Disk Hygiene Report")
    print("=" * 60)

    all_issues = []
    checks = [
        ("Crash Dumps", check_crash_dumps),
        ("HuggingFace Cache", check_hf_cache),
        ("pip Cache", check_pip_cache),
        ("Orphan Models", check_orphan_models),
        ("WSL vhdx Bloat", check_vhdx_bloat),
        ("Downloads References", check_downloads_references),
    ]

    for name, check_fn in checks:
        print(f"\n  Checking: {name}...", end=" ", flush=True)
        try:
            issues = check_fn()
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        if issues:
            print(f"FOUND {len(issues)} issue(s)")
            all_issues.extend(issues)
            for issue in issues:
                size_str = f" [{sizeof_fmt(issue['size'])}]" if issue["size"] > 0 else ""
                print(f"    - {issue['message']}{size_str}")
        else:
            print("OK")

    total_reclaimable = sum(i["size"] for i in all_issues if i.get("clean_path"))
    cleanable = [i for i in all_issues if i.get("clean_path")]

    print(f"\n{'=' * 60}")
    print(f"  Total reclaimable: {sizeof_fmt(total_reclaimable)}")
    print(f"  Issues: {len(all_issues)} ({len(cleanable)} auto-cleanable)")

    if clean_mode and cleanable:
        print(f"\n  Cleaning {len(cleanable)} items...")
        freed = 0
        for issue in cleanable:
            p = issue["clean_path"]
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                elif os.path.isfile(p):
                    os.remove(p)
                freed += issue["size"]
                print(f"    DELETED: {p} ({sizeof_fmt(issue['size'])})")
            except Exception as e:
                print(f"    FAILED: {p} — {e}")
        print(f"\n  Freed: {sizeof_fmt(freed)}")
    elif cleanable and not clean_mode:
        print(f"\n  Run with --clean to auto-delete {len(cleanable)} items")

    # Always report non-cleanable issues (vhdx, downloads refs)
    non_clean = [i for i in all_issues if not i.get("clean_path")]
    if non_clean:
        print(f"\n  Manual action needed for {len(non_clean)} item(s):")
        for issue in non_clean:
            print(f"    - {issue['message']}")

    print()
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
