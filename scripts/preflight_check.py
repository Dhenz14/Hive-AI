#!/usr/bin/env python3
"""Pre-flight checks for HiveAI training pipeline.
Run before any training to catch preventable failures early.

Usage:
    python scripts/preflight_check.py [--data PATH] [--base-model PATH]

Exit codes:
    0 = all checks passed
    1 = critical failure (training will crash)
    2 = warnings only (training may work but risky)
"""

import os, sys, json, subprocess, shutil, argparse

def check_hf_offline():
    """HF_HUB_OFFLINE should be set to avoid 120s timeouts"""
    val = os.environ.get("HF_HUB_OFFLINE", "")
    if val != "1":
        return "WARN", "HF_HUB_OFFLINE not set to 1. Training may hang on HF validation."
    return "OK", "HF_HUB_OFFLINE=1"

def check_disk_space(min_gb=20):
    """Check WSL has enough free disk space"""
    try:
        stat = shutil.disk_usage("/opt/hiveai/project")
        free_gb = stat.free / (1024**3)
        if free_gb < min_gb:
            return "FAIL", f"Only {free_gb:.1f}GB free (need {min_gb}GB minimum)"
        return "OK", f"{free_gb:.1f}GB free"
    except Exception as e:
        return "WARN", f"Could not check disk: {e}"

def check_gpu_free():
    """Check if GPU VRAM is available (llama-server not hogging it)"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return "WARN", "nvidia-smi failed"
        used, total = [int(x.strip()) for x in result.stdout.strip().split(",")]
        free = total - used
        if free < 8000:  # Need at least 8GB for training
            return "FAIL", f"Only {free}MB VRAM free ({used}/{total}MB used). Kill llama-server first."
        return "OK", f"{free}MB VRAM free ({used}/{total}MB)"
    except FileNotFoundError:
        return "WARN", "nvidia-smi not found"
    except Exception as e:
        return "WARN", f"GPU check failed: {e}"

def check_llama_server():
    """Warn if llama-server is running (eats ~10GB VRAM)"""
    try:
        result = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return "WARN", "llama-server is running. It uses ~10GB VRAM. Kill it before training."
        return "OK", "llama-server not running"
    except Exception:
        return "OK", "Could not check (non-Linux?)"

def check_data_file(path):
    """Validate training JSONL file"""
    if not path:
        return "SKIP", "No data file specified"
    if not os.path.exists(path):
        return "FAIL", f"Data file not found: {path}"

    errors = []
    line_count = 0
    has_metadata = False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {i}: invalid JSON — {e}")
                    if len(errors) >= 5:
                        break
                    continue

                line_count += 1

                # Check for metadata field (breaks pyarrow)
                if "metadata" in obj:
                    has_metadata = True

                # Check required fields
                if "instruction" not in obj and "input" not in obj:
                    if "messages" not in obj:  # Allow chat format too
                        errors.append(f"Line {i}: missing 'instruction' field")
                        if len(errors) >= 5:
                            break
    except Exception as e:
        return "FAIL", f"Could not read data file: {e}"

    if errors:
        return "FAIL", f"{len(errors)} errors in data file: {errors[0]}"

    warnings = []
    if has_metadata:
        warnings.append("Has 'metadata' field — mixed types may crash pyarrow. Strip metadata before training.")
    if line_count < 10:
        warnings.append(f"Only {line_count} pairs — very small dataset")

    if warnings:
        return "WARN", f"{line_count} pairs. " + " ".join(warnings)

    return "OK", f"{line_count} valid training pairs"

def check_base_model(path):
    """Check if base model path exists and has required files"""
    if not path:
        return "SKIP", "No base model specified (will use default)"
    if not os.path.exists(path):
        return "FAIL", f"Base model not found: {path}"

    # Check for safetensors or bin files
    has_weights = any(
        f.endswith(('.safetensors', '.bin'))
        for f in os.listdir(path)
    )
    has_config = os.path.exists(os.path.join(path, "config.json"))

    if not has_weights:
        return "FAIL", f"No model weights found in {path}"
    if not has_config:
        return "WARN", f"No config.json in {path}"

    return "OK", f"Base model found at {path}"

def check_crlf():
    """Check for Windows CRLF in critical scripts"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bad_files = []
    for fname in os.listdir(script_dir):
        if fname.endswith(('.py', '.sh')):
            fpath = os.path.join(script_dir, fname)
            try:
                with open(fpath, 'rb') as f:
                    content = f.read(4096)  # Check first 4KB
                if b'\r\n' in content:
                    bad_files.append(fname)
            except Exception:
                pass

    if bad_files:
        return "WARN", f"CRLF detected in: {', '.join(bad_files[:5])}. Run: sed -i 's/\r$//' scripts/*.py scripts/*.sh"
    return "OK", "No CRLF issues"

def check_hf_cache():
    """Check if required HF model snapshots are cached"""
    cache_base = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir = os.path.join(cache_base, "models--unsloth--Qwen2.5-Coder-14B-Instruct-bnb-4bit")

    if os.path.exists(model_dir):
        snapshots = os.path.join(model_dir, "snapshots")
        if os.path.exists(snapshots) and os.listdir(snapshots):
            return "OK", "Unsloth 4-bit model cached"

    # Check for standard model
    model_dir2 = os.path.join(cache_base, "models--Qwen--Qwen2.5-Coder-14B-Instruct")
    if os.path.exists(model_dir2):
        return "OK", "Qwen base model cached"

    return "WARN", "No cached model found. First training run will download ~8GB."


def main():
    parser = argparse.ArgumentParser(description="Pre-flight checks for HiveAI training")
    parser.add_argument("--data", help="Path to training JSONL file")
    parser.add_argument("--base-model", help="Path to base model directory")
    parser.add_argument("--quiet", action="store_true", help="Only show failures and warnings")
    args = parser.parse_args()

    checks = [
        ("HF Offline Mode", check_hf_offline),
        ("Disk Space", lambda: check_disk_space(20)),
        ("GPU VRAM", check_gpu_free),
        ("llama-server", check_llama_server),
        ("CRLF Check", check_crlf),
        ("HF Cache", check_hf_cache),
        ("Training Data", lambda: check_data_file(args.data)),
        ("Base Model", lambda: check_base_model(args.base_model)),
    ]

    print("=" * 60)
    print("  HiveAI Pre-Flight Check")
    print("=" * 60)

    results = []
    for name, check_fn in checks:
        status, msg = check_fn()
        results.append((name, status, msg))

        if args.quiet and status in ("OK", "SKIP"):
            continue

        icon = {"OK": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "–"}[status]
        color_start = {"OK": "", "WARN": "\033[33m", "FAIL": "\033[31m", "SKIP": ""}[status]
        color_end = "\033[0m" if color_start else ""
        print(f"  {color_start}{icon} {name}: {msg}{color_end}")

    print("=" * 60)

    fails = sum(1 for _, s, _ in results if s == "FAIL")
    warns = sum(1 for _, s, _ in results if s == "WARN")

    if fails:
        print(f"\033[31m  BLOCKED: {fails} critical issue(s) must be fixed before training\033[0m")
        return 1
    elif warns:
        print(f"\033[33m  READY with {warns} warning(s)\033[0m")
        return 2
    else:
        print(f"  ALL CLEAR — ready for training")
        return 0


if __name__ == "__main__":
    sys.exit(main())
