"""
Train a LoRA on a single subject category and evaluate it.

Usage:
    python scripts/train_subject.py rust          # train on rust data
    python scripts/train_subject.py hive_sdk      # train on hive SDK data
    python scripts/train_subject.py --list        # list available categories
    python scripts/train_subject.py rust --smoke 5 # 5-step smoke test

Workflow:
    1. Trains LoRA on category data (loras/training_data/by_category/{cat}.jsonl)
    2. Converts adapter to GGUF
    3. Starts llama-server with the LoRA
    4. Runs eval on that category only
    5. Reports score vs base

Environment variables (all optional — sensible defaults are derived from script location):
    HIVEAI_WSL_PROJECT   WSL project root          (default: /opt/hiveai/project)
    HIVEAI_WSL_VENV      WSL virtualenv root       (default: /opt/hiveai-env)
    HIVEAI_WSL_DISTRO    WSL distro name            (default: Ubuntu-24.04)
    LLAMA_CPP_DIR        llama.cpp install dir (Win) (default: C:/llama.cpp)
    HIVEAI_BASE_MODEL    WSL path to HF base model  (default: {WSL_PROJECT}/models/qwen2.5-coder-14b)

Requires:
    - WSL with training env
    - llama.cpp converter at {LLAMA_CPP_DIR}/convert_lora_to_gguf.py
    - llama-server at {LLAMA_CPP_DIR}/bin/llama-server.exe
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CATEGORY_DIR = PROJECT_ROOT / "loras" / "training_data" / "by_category"
LORA_OUTPUT_BASE = PROJECT_ROOT / "loras" / "subjects"
MODELS_DIR = PROJECT_ROOT / "models"
BASE_GGUF = MODELS_DIR / "Qwen2.5-Coder-14B-Instruct-Q5_K_M.gguf"
LLAMA_CPP_DIR = Path(os.environ.get("LLAMA_CPP_DIR", "C:/llama.cpp"))
CONVERTER = LLAMA_CPP_DIR / "convert_lora_to_gguf.py"
LLAMA_SERVER = LLAMA_CPP_DIR / "bin" / "llama-server.exe"
EVAL_SCRIPT = PROJECT_ROOT / "scripts" / "run_eval.py"
TRAIN_SCRIPT = PROJECT_ROOT / "scripts" / "train_v5.py"

# WSL paths
WSL_PROJECT = os.environ.get("HIVEAI_WSL_PROJECT", "/opt/hiveai/project")
WSL_VENV = os.environ.get("HIVEAI_WSL_VENV", "/opt/hiveai-env")
WSL_DISTRO = os.environ.get("HIVEAI_WSL_DISTRO", "Ubuntu-24.04")
WSL_BASE_MODEL = os.environ.get("HIVEAI_BASE_MODEL", f"{WSL_PROJECT}/models/qwen2.5-coder-14b")

def _win_to_wsl_mnt(win_path: Path) -> str:
    """Convert a Windows path to WSL /mnt/... path.
    e.g. C:\\Users\\dan\\hiveai -> /mnt/c/Users/dan/hiveai"""
    p = str(win_path.resolve())
    return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")

WSL_MNT_PROJECT = _win_to_wsl_mnt(PROJECT_ROOT)
WSL_MNT_LLAMA_CPP = _win_to_wsl_mnt(LLAMA_CPP_DIR)


def list_categories():
    """List available categories with pair counts."""
    cats = []
    for f in sorted(CATEGORY_DIR.glob("*.jsonl")):
        count = sum(1 for _ in open(f))
        cats.append((f.stem, count))

    print(f"{'Category':25s} {'Pairs':>6s}  {'Est. Steps':>10s}  {'Est. Time':>10s}")
    print("-" * 60)
    for cat, count in sorted(cats, key=lambda x: -x[1]):
        # Steps = (pairs * 2 epochs) / 16 batch size
        steps = (count * 2) // 16
        # ~16s/step without KL, ~105s/step with KL
        time_no_kl = steps * 16 / 3600
        time_kl = steps * 105 / 3600
        print(f"  {cat:23s} {count:6d}  {steps:10d}  {time_no_kl:.1f}h-{time_kl:.1f}h")


def sync_to_wsl():
    """Sync training script and category data to WSL."""
    print("Syncing files to WSL...")
    cmds = [
        f"cp {WSL_MNT_PROJECT}/scripts/train_v5.py {WSL_PROJECT}/scripts/",
        f"mkdir -p {WSL_PROJECT}/loras/training_data/by_category",
        f"cp -r {WSL_MNT_PROJECT}/loras/training_data/by_category/ {WSL_PROJECT}/loras/training_data/by_category/",
        f"mkdir -p {WSL_PROJECT}/loras/subjects",
    ]
    for cmd in cmds:
        subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "bash", "-c", cmd],
                       check=True, capture_output=True)
    print("  Synced.")


def train_category(category: str, smoke_steps: int = 0, no_kl: bool = False):
    """Train a LoRA on a single category."""
    data_file = f"{WSL_PROJECT}/loras/training_data/by_category/{category}.jsonl"
    output_dir = f"{WSL_PROJECT}/loras/subjects/{category}"
    log_file = f"{WSL_PROJECT}/logs/train_{category}.log"

    # Clean previous output
    subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "bash", "-c",
                    f"rm -rf {output_dir}/*"], capture_output=True)

    cmd_parts = [
        f"source {WSL_VENV}/bin/activate",
        f"cd {WSL_PROJECT}",
        f"python scripts/train_v5.py --force-unsloth",
        f"--data {data_file}",
        f"--output-dir {output_dir}",
    ]
    if smoke_steps:
        cmd_parts.append(f"--test {smoke_steps}")
    if no_kl:
        cmd_parts.append("--no-kl")

    full_cmd = " ".join(cmd_parts) + f" 2>&1 | tee {log_file}"

    print(f"\nTraining {category}...")
    print(f"  Data: {data_file}")
    print(f"  Output: {output_dir}")
    print(f"  Log: {log_file}")
    if smoke_steps:
        print(f"  Smoke test: {smoke_steps} steps")

    result = subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-c", full_cmd],
        timeout=72000,  # 20h max
    )

    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return False

    print(f"  Training complete!")
    return True


def convert_to_gguf(category: str):
    """Convert PEFT adapter to GGUF format."""
    adapter_dir = LORA_OUTPUT_BASE / category
    gguf_path = MODELS_DIR / f"hiveai-{category}-lora-f16.gguf"

    # Check if adapter exists in WSL
    wsl_adapter = f"{WSL_PROJECT}/loras/subjects/{category}"
    result = subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-c",
         f"ls {wsl_adapter}/adapter_model.safetensors 2>/dev/null"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print(f"  No adapter found at {wsl_adapter}")
        return None

    # Copy adapter from WSL to Windows
    adapter_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-c",
         f"cp -r {wsl_adapter}/* {WSL_MNT_PROJECT}/loras/subjects/{category}/"],
        check=True, capture_output=True
    )

    print(f"\nConverting {category} adapter to GGUF...")
    result = subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-c",
         f"source {WSL_VENV}/bin/activate && "
         f"python {WSL_MNT_LLAMA_CPP}/convert_lora_to_gguf.py "
         f"{wsl_adapter} "
         f"--base {WSL_BASE_MODEL} "
         f"--outfile {WSL_MNT_PROJECT}/models/hiveai-{category}-lora-f16.gguf "
         f"--outtype f16"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"  Conversion failed: {result.stderr[-500:]}")
        return None

    print(f"  GGUF saved: {gguf_path}")
    return gguf_path


def eval_category(category: str, gguf_path: Path):
    """Start server with LoRA, eval just this category, return score."""
    print(f"\nEvaluating {category}...")

    # Kill any existing llama-server
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                   capture_output=True)
    time.sleep(2)

    # Start llama-server with the LoRA
    server_proc = subprocess.Popen(
        [str(LLAMA_SERVER),
         "--model", str(BASE_GGUF),
         "--port", "11435",
         "--flash-attn", "on",
         "--cache-type-k", "q8_0",
         "--cache-type-v", "q4_0",
         "--ctx-size", "8192",
         "--lora", str(gguf_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Wait for server
    for i in range(30):
        time.sleep(2)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://localhost:11435/health")
            if b"ok" in resp.read():
                break
        except Exception:
            pass
    else:
        print("  Server failed to start!")
        server_proc.kill()
        return None

    # Enable LoRA
    import urllib.request
    req = urllib.request.Request(
        "http://localhost:11435/lora-adapters",
        data=json.dumps([{"id": 0, "scale": 1.0}]).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    urllib.request.urlopen(req)

    # Map our category names to eval category names
    eval_cat = category
    if category.startswith("hive_"):
        eval_cat = category  # eval uses same names

    # Run eval on just this category
    result = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT),
         "--model", f"hiveai-{category}",
         "--base-url", "http://localhost:11435",
         "--category", eval_cat],
        capture_output=True, text=True
    )

    # Kill server
    server_proc.kill()
    server_proc.wait()

    # Parse result
    if result.returncode != 0:
        print(f"  Eval failed: {result.stderr[-300:]}")
        return None

    # Find the JSON output file
    eval_files = sorted(Path("evals").glob(f"hiveai-{category}_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not eval_files:
        print("  No eval output found")
        return None

    with open(eval_files[0]) as f:
        report = json.load(f)

    score = report.get("overall_score", 0)
    cat_scores = report.get("by_category", {})

    print(f"  Overall: {score:.3f}")
    for cat, data in cat_scores.items():
        print(f"  {cat}: {data['score']:.3f} ({data['count']} challenges)")

    return report


def main():
    parser = argparse.ArgumentParser(description="Train and eval a single subject category")
    parser.add_argument("category", nargs="?", help="Category to train")
    parser.add_argument("--list", action="store_true", help="List available categories")
    parser.add_argument("--smoke", type=int, default=0, help="Smoke test N steps")
    parser.add_argument("--no-kl", action="store_true", help="Disable KL for faster training")
    parser.add_argument("--train-only", action="store_true", help="Train without eval")
    parser.add_argument("--eval-only", action="store_true", help="Eval existing LoRA without training")
    args = parser.parse_args()

    if args.list:
        list_categories()
        return

    if not args.category:
        parser.print_help()
        return

    category = args.category
    data_file = CATEGORY_DIR / f"{category}.jsonl"
    if not data_file.exists():
        print(f"Category '{category}' not found. Available:")
        list_categories()
        return

    if not args.eval_only:
        # Sync and train
        sync_to_wsl()
        success = train_category(category, smoke_steps=args.smoke, no_kl=args.no_kl)
        if not success:
            sys.exit(1)

    if args.train_only or args.smoke:
        print("Training done (skipping eval).")
        return

    # Convert and eval
    gguf_path = convert_to_gguf(category)
    if not gguf_path:
        sys.exit(1)

    report = eval_category(category, gguf_path)
    if report:
        print(f"\nResult: {category} LoRA scored {report['overall_score']:.3f}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
