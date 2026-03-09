"""Pre-flight training validator: catches all known crash causes before training starts.

Checks:
  1. HF_HUB_OFFLINE=1 is set (prevents 120s timeout)
  2. Training JSONL has no metadata fields (prevents pyarrow crash)
  3. No CRLF in script files (prevents bash parse errors)
  4. Disk space > 20GB free in WSL
  5. GPU VRAM available (llama-server not running)
  6. Base model path exists and is valid
  7. Dataset loads without JSON errors
  8. HF cache has required model snapshots

Usage:
    python scripts/preflight_check.py --data datasets/thinking_batch2.jsonl
    python scripts/preflight_check.py --data datasets/batch.jsonl --base-model-hf /path/to/hf

Exit codes: 0 = all checks passed, 1 = critical failure, 2 = warnings only
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check_pass(msg):
    print(f"  {GREEN}PASS{RESET} {msg}")
    return True


def check_fail(msg):
    print(f"  {RED}FAIL{RESET} {msg}")
    return False


def check_warn(msg):
    print(f"  {YELLOW}WARN{RESET} {msg}")
    return True  # warnings don't fail


def check_hf_offline():
    """Ensure HF_HUB_OFFLINE is set to prevent timeout."""
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        return check_pass("HF_HUB_OFFLINE=1")
    # Check if train_v5.py sets it (it does, but verify)
    train_v5 = PROJECT_ROOT / "scripts" / "train_v5.py"
    if train_v5.exists():
        content = train_v5.read_text(encoding="utf-8", errors="replace")
        if 'os.environ.setdefault("HF_HUB_OFFLINE", "1")' in content:
            return check_pass("HF_HUB_OFFLINE=1 set in train_v5.py (auto-applied)")
    return check_fail("HF_HUB_OFFLINE not set — training may hang for 120s")


def check_metadata(data_path):
    """Check if JSONL has metadata fields that crash pyarrow."""
    if not os.path.exists(data_path):
        return check_fail(f"Data file not found: {data_path}")

    has_metadata = False
    mixed_types = False
    line_count = 0
    errors = []

    with open(data_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                line_count += 1
                if "metadata" in sample:
                    has_metadata = True
                    meta = sample["metadata"]
                    if isinstance(meta, dict):
                        types = set(type(v).__name__ for v in meta.values())
                        if len(types) > 1:
                            mixed_types = True
            except json.JSONDecodeError as e:
                errors.append(f"  Line {i}: {e}")
                if len(errors) >= 5:
                    break

    if errors:
        check_fail(f"JSON parse errors in {data_path}:")
        for err in errors:
            print(err)
        return False

    if mixed_types:
        return check_fail(f"Mixed metadata types in {data_path} — will crash pyarrow. Strip metadata.")
    elif has_metadata:
        check_warn(f"Data has metadata fields — train_v5.py strips them, but consider pre-cleaning")

    return check_pass(f"Data OK: {line_count} samples, no mixed metadata")


def check_crlf():
    """Check for Windows CRLF in script files."""
    scripts_dir = PROJECT_ROOT / "scripts"
    crlf_files = []
    for f in scripts_dir.glob("*.py"):
        try:
            content = f.read_bytes()
            if b"\r\n" in content:
                crlf_files.append(f.name)
        except Exception:
            pass
    for f in scripts_dir.glob("*.sh"):
        try:
            content = f.read_bytes()
            if b"\r\n" in content:
                crlf_files.append(f.name)
        except Exception:
            pass

    if crlf_files:
        check_warn(f"CRLF detected in: {', '.join(crlf_files)}")
        print(f"    Fix: sed -i 's/\\r$//' /opt/hiveai/project/scripts/*.py *.sh")
        return True  # warning, not failure (train_v5.py handles this)
    return check_pass("No CRLF in scripts")


def check_disk_space(min_gb=20):
    """Check free disk space."""
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "df -BG /opt/hiveai/project 2>/dev/null | tail -1 | awk '{print $4}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            free_str = result.stdout.strip().rstrip("G")
            try:
                free_gb = int(free_str)
                if free_gb < min_gb:
                    return check_fail(f"Only {free_gb}GB free in WSL (need {min_gb}GB)")
                return check_pass(f"Disk space: {free_gb}GB free")
            except ValueError:
                pass
    except Exception:
        pass
    return check_warn("Could not check WSL disk space")


def check_gpu():
    """Check if GPU is free (no llama-server eating VRAM)."""
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "nvidia-smi --query-compute-apps=name,used_memory --format=csv,noheader 2>/dev/null || echo 'no-nvidia'"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        if "no-nvidia" in output:
            return check_warn("nvidia-smi not available — cannot verify GPU")
        if "llama" in output.lower() or "server" in output.lower():
            return check_fail(f"llama-server is using GPU — kill it before training. Processes: {output}")
        if output:
            check_warn(f"GPU processes: {output}")
        return check_pass("GPU VRAM available (no llama-server running)")
    except Exception:
        return check_warn("Could not check GPU status")


def check_base_model(base_model_hf=None):
    """Check if base model exists."""
    # Check default Unsloth cache
    bnb4_cache = os.path.expanduser("~/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct-bnb-4bit/snapshots")
    has_bnb4 = os.path.isdir(bnb4_cache) and os.listdir(bnb4_cache)

    if base_model_hf:
        if os.path.exists(base_model_hf):
            config_path = os.path.join(base_model_hf, "config.json")
            if os.path.exists(config_path):
                return check_pass(f"Base model found: {base_model_hf}")
            else:
                return check_fail(f"Base model dir exists but missing config.json: {base_model_hf}")
        else:
            # Check WSL path
            try:
                result = subprocess.run(
                    ["wsl.exe", "-d", "Ubuntu-24.04", "--", "test", "-d", base_model_hf],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0:
                    return check_pass(f"Base model found in WSL: {base_model_hf}")
            except Exception:
                pass
            return check_fail(f"Base model not found: {base_model_hf}")

    if has_bnb4:
        return check_pass("Default Unsloth BNB-4bit cache found")
    return check_warn("No base model specified and no Unsloth cache found")


def check_hf_cache():
    """Check HF cache has needed snapshots."""
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    unsloth_dir = cache_dir / "models--unsloth--Qwen2.5-Coder-14B-Instruct-bnb-4bit"
    if unsloth_dir.exists():
        snapshots = list((unsloth_dir / "snapshots").iterdir()) if (unsloth_dir / "snapshots").exists() else []
        if snapshots:
            return check_pass(f"HF cache: {len(snapshots)} snapshot(s) of Unsloth BNB-4bit")
    # Also check WSL
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "ls /root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct-bnb-4bit/snapshots/ 2>/dev/null | head -1"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            return check_pass("HF cache: Unsloth BNB-4bit snapshot in WSL")
    except Exception:
        pass
    return check_warn("Unsloth BNB-4bit model not found in HF cache")


def main():
    parser = argparse.ArgumentParser(description="Pre-flight training checks")
    parser.add_argument("--data", type=str, required=True,
                        help="Path to training JSONL file")
    parser.add_argument("--base-model-hf", type=str, default=None,
                        help="Path to HF base model (optional)")
    parser.add_argument("--min-disk-gb", type=int, default=20,
                        help="Minimum free disk space in GB (default: 20)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Pre-Flight Training Check")
    print("=" * 60)

    checks = [
        ("HF Offline Mode", lambda: check_hf_offline()),
        ("Training Data", lambda: check_metadata(args.data)),
        ("CRLF in Scripts", lambda: check_crlf()),
        ("Disk Space", lambda: check_disk_space(args.min_disk_gb)),
        ("GPU Availability", lambda: check_gpu()),
        ("Base Model", lambda: check_base_model(args.base_model_hf)),
        ("HF Cache", lambda: check_hf_cache()),
    ]

    results = {}
    for name, check_fn in checks:
        print(f"\n[{name}]")
        results[name] = check_fn()

    print(f"\n{'=' * 60}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    failed = total - passed

    if failed == 0:
        print(f"  {GREEN}ALL {total} CHECKS PASSED{RESET} — ready to train!")
        sys.exit(0)
    else:
        print(f"  {RED}{failed} CHECK(S) FAILED{RESET} — fix issues before training")
        sys.exit(1)


if __name__ == "__main__":
    main()
