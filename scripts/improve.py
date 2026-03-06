#!/usr/bin/env python3
"""
HiveAI Continuous Improvement Loop -- one command to get smarter.

    python scripts/improve.py                     # full cycle: train -> deploy -> eval -> hunt
    python scripts/improve.py --skip-train        # deploy existing adapter + eval + hunt
    python scripts/improve.py --skip-deploy       # just eval + hunt weaknesses
    python scripts/improve.py --status            # show current state of the loop
    python scripts/improve.py --plan              # dry run: show what would happen

The Loop:
    1. TRAIN   -- fine-tune LoRA on current training data (WSL + Unsloth)
    2. DEPLOY  -- merge adapter into base, export GGUF, prepare llama-server
    3. EVAL    -- run eval harness, score by category
    4. HUNT    -- analyze eval, identify weaknesses, generate targeted pairs
    5. PREP    -- rebuild training JSONL with new pairs for next cycle
    6. REPORT  -- summarize cycle results, recommend next action

Each cycle compounds on the last. The model's weaknesses drive the next
round of training data, creating a self-improving feedback loop.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("improve")

# ---------------------------------------------------------------------------
# Configuration -- update these for each version
# ---------------------------------------------------------------------------
CURRENT_VERSION = "v6"
NEXT_VERSION = "v7"

ADAPTER_DIR = PROJECT_ROOT / "loras" / CURRENT_VERSION
GGUF_DIR = PROJECT_ROOT / "models" / f"hiveai-{CURRENT_VERSION}"
TRAINING_DATA = PROJECT_ROOT / "loras" / "training_data" / f"{CURRENT_VERSION}.jsonl"
NEXT_TRAINING_DATA = PROJECT_ROOT / "loras" / "training_data" / f"{NEXT_VERSION}.jsonl"
WEAKNESS_PATCHES_DIR = PROJECT_ROOT / "loras" / "training_data" / "weakness_patches"

MODEL_NAME = f"hiveai-{CURRENT_VERSION}"
UNSLOTH_MODEL = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"
DEFAULT_QUANT = "q5_k_m"

LLAMA_SERVER_URL = "http://localhost:11435"
LLAMA_SERVER_EXE = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"

WSL_DISTRO = "Ubuntu-24.04"
WSL_VENV = "/opt/hiveai-env"
WSL_PROJECT = "/opt/hiveai/project"

# Cycle history
IMPROVE_HISTORY = PROJECT_ROOT / "loras" / "improve_history.json"


def load_history() -> list[dict]:
    if IMPROVE_HISTORY.exists():
        return json.loads(IMPROVE_HISTORY.read_text())
    return []


def save_history(history: list[dict]):
    IMPROVE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    IMPROVE_HISTORY.write_text(json.dumps(history, indent=2))


# ---------------------------------------------------------------------------
# Step 1: Train
# ---------------------------------------------------------------------------
def step_train(max_steps: int = 0, resume: bool = False) -> bool:
    """Launch training in WSL. Blocks until complete."""
    logger.info("=" * 60)
    logger.info("  STEP 1: TRAIN")
    logger.info("=" * 60)

    if not TRAINING_DATA.exists():
        logger.error(f"Training data not found: {TRAINING_DATA}")
        logger.info(f"Run: python scripts/prepare_v5_data.py --export")
        return False

    # Check if adapter already exists (training already done)
    adapter_safetensors = ADAPTER_DIR / "adapter_model.safetensors"
    if adapter_safetensors.exists() and not resume:
        size_mb = adapter_safetensors.stat().st_size / 1e6
        logger.info(f"Adapter already exists: {adapter_safetensors} ({size_mb:.0f} MB)")
        logger.info("Skipping training. Use --resume to continue from checkpoint.")
        return True

    cmd_parts = [
        f"source {WSL_VENV}/bin/activate",
        f"cd {WSL_PROJECT}",
        "python scripts/train_v5.py --no-kl --force-unsloth",
    ]
    if max_steps:
        cmd_parts[-1] += f" --test {max_steps}"

    cmd = f"wsl -d {WSL_DISTRO} -- bash -c \"{' && '.join(cmd_parts)}\""

    logger.info(f"Launching training...")
    logger.info(f"  Data: {TRAINING_DATA}")
    logger.info(f"  Output: {ADAPTER_DIR}")

    t0 = time.time()
    result = subprocess.run(cmd, shell=True, timeout=86400)  # 24h max
    elapsed = time.time() - t0

    if result.returncode != 0:
        logger.error(f"Training failed (exit {result.returncode}, {elapsed/3600:.1f}h)")
        return False

    if adapter_safetensors.exists():
        logger.info(f"Training complete in {elapsed/3600:.1f}h")
        return True

    logger.error("Training finished but no adapter file found")
    return False


# ---------------------------------------------------------------------------
# Step 2: Deploy (merge + GGUF + llama-server config)
# ---------------------------------------------------------------------------
def step_deploy(quant: str = DEFAULT_QUANT) -> str | None:
    """Merge LoRA + export GGUF. Returns GGUF path or None."""
    logger.info("=" * 60)
    logger.info("  STEP 2: DEPLOY")
    logger.info("=" * 60)

    # Check for existing GGUF
    if GGUF_DIR.exists():
        existing = list(GGUF_DIR.glob("*.gguf"))
        if existing:
            gguf = existing[0]
            logger.info(f"GGUF already exists: {gguf} ({gguf.stat().st_size/1e9:.1f} GB)")
            return str(gguf)

    from hiveai.lora.merge_cycle import merge_and_export_gguf_unsloth

    gguf_path = merge_and_export_gguf_unsloth(
        adapter_dir=str(ADAPTER_DIR),
        gguf_output_dir=str(GGUF_DIR),
        quant=quant,
        unsloth_model=UNSLOTH_MODEL,
    )

    if gguf_path:
        logger.info(f"GGUF ready: {gguf_path}")
        print_server_command(gguf_path)
    else:
        logger.error("Deploy failed -- no GGUF produced")

    return gguf_path


def print_server_command(gguf_path: str):
    """Print the llama-server launch command."""
    print(f"\n  To serve:\n")
    print(f"    \"{LLAMA_SERVER_EXE}\" \\")
    print(f"      --model \"{gguf_path}\" \\")
    print(f"      --port 11435 --n-gpu-layers 999 --ctx-size 8192 \\")
    print(f"      --flash-attn on --cache-type-k q8_0 --cache-type-v q4_0 \\")
    print(f"      --no-mmap --mlock\n")


# ---------------------------------------------------------------------------
# Step 3: Eval
# ---------------------------------------------------------------------------
def step_eval() -> dict | None:
    """Run eval harness, return results dict."""
    logger.info("=" * 60)
    logger.info("  STEP 3: EVAL")
    logger.info("=" * 60)

    # Check if llama-server is running
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{LLAMA_SERVER_URL}/health", timeout=5)
        if resp.status != 200:
            logger.warning(f"llama-server not healthy (status {resp.status})")
    except Exception:
        logger.error(f"llama-server not reachable at {LLAMA_SERVER_URL}")
        logger.info("Start llama-server with the GGUF file first, then re-run with --skip-deploy")
        return None

    eval_script = PROJECT_ROOT / "scripts" / "run_eval.py"
    cmd = [
        sys.executable, str(eval_script),
        "--model", MODEL_NAME,
        "--base-url", LLAMA_SERVER_URL,
    ]

    logger.info(f"Running eval: {MODEL_NAME} via {LLAMA_SERVER_URL}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=14400)
    elapsed = time.time() - t0

    if result.returncode != 0:
        logger.error(f"Eval failed (exit {result.returncode}, {elapsed/60:.0f}m)")
        return None

    # Find the eval JSON that was just written
    evals_dir = PROJECT_ROOT / "evals"
    if evals_dir.exists():
        evals = sorted(evals_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if evals:
            latest = evals[0]
            eval_data = json.loads(latest.read_text())
            score = eval_data.get("overall_score", 0)
            logger.info(f"Eval complete: {score:.3f} ({elapsed/60:.0f}m)")
            return eval_data

    logger.warning("Eval finished but no results file found")
    return None


# ---------------------------------------------------------------------------
# Step 4: Hunt weaknesses
# ---------------------------------------------------------------------------
def step_hunt(eval_data: dict, generate: bool = True,
              pairs_per_category: int = 15) -> list[dict]:
    """Analyze eval results, optionally generate targeted pairs."""
    logger.info("=" * 60)
    logger.info("  STEP 4: HUNT WEAKNESSES")
    logger.info("=" * 60)

    from scripts.weakness_hunter import analyze_weaknesses, print_analysis, generate_targeted_pairs, export_pairs

    weaknesses = analyze_weaknesses(eval_data, threshold=0.75)
    print_analysis(eval_data, weaknesses, 0.75)

    if not weaknesses:
        logger.info("No weaknesses found -- model is above threshold everywhere!")
        return []

    if generate:
        logger.info(f"Generating targeted pairs for {len(weaknesses)} weak categories...")
        pairs = generate_targeted_pairs(weaknesses, pairs_per_category=pairs_per_category)
        if pairs:
            export_pairs(pairs, eval_data.get("model", MODEL_NAME))
            logger.info(f"Generated {len(pairs)} weakness-targeted pairs")
        return pairs

    return []


# ---------------------------------------------------------------------------
# Step 5: Prep next training data
# ---------------------------------------------------------------------------
def step_prep() -> bool:
    """Rebuild training JSONL including weakness patches."""
    logger.info("=" * 60)
    logger.info("  STEP 5: PREP NEXT TRAINING DATA")
    logger.info("=" * 60)

    # Count weakness patches
    patch_count = 0
    if WEAKNESS_PATCHES_DIR.exists():
        for patch in WEAKNESS_PATCHES_DIR.glob("*.jsonl"):
            with open(patch, encoding="utf-8") as f:
                patch_count += sum(1 for _ in f)

    if patch_count > 0:
        logger.info(f"Found {patch_count} weakness-targeted pairs to include")

    # Run the data prep script
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "prepare_v5_data.py"), "--export"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=300)

    if result.returncode != 0:
        logger.error("Data prep failed")
        return False

    # The script outputs to v5.jsonl -- copy to next version
    v5_jsonl = PROJECT_ROOT / "loras" / "training_data" / "v5.jsonl"
    if v5_jsonl.exists():
        import shutil
        shutil.copy2(v5_jsonl, NEXT_TRAINING_DATA)
        pair_count = sum(1 for _ in open(NEXT_TRAINING_DATA, encoding="utf-8"))
        logger.info(f"Next training data ready: {NEXT_TRAINING_DATA} ({pair_count} pairs)")
        return True

    logger.error("v5.jsonl not found after prep")
    return False


# ---------------------------------------------------------------------------
# Step 6: Report
# ---------------------------------------------------------------------------
def step_report(eval_data: dict | None, weaknesses: list, pairs_generated: int,
                gguf_path: str | None, cycle_start: float):
    """Print final cycle summary."""
    elapsed = time.time() - cycle_start

    print("\n" + "=" * 65)
    print("  IMPROVEMENT CYCLE COMPLETE")
    print("=" * 65)

    if eval_data:
        score = eval_data.get("overall_score", 0)
        by_cat = eval_data.get("by_category", {})
        best_cat = max(by_cat.items(), key=lambda x: x[1].get("score", 0)) if by_cat else ("?", {"score": 0})
        worst_cat = min(by_cat.items(), key=lambda x: x[1].get("score", 0)) if by_cat else ("?", {"score": 0})

        print(f"\n  Model:     {MODEL_NAME}")
        print(f"  Score:     {score:.3f}")
        print(f"  Best:      {best_cat[0]} ({best_cat[1].get('score', 0):.3f})")
        print(f"  Worst:     {worst_cat[0]} ({worst_cat[1].get('score', 0):.3f})")
        print(f"  Weak cats: {len(weaknesses)}")

    if gguf_path:
        print(f"  GGUF:      {gguf_path}")
    if pairs_generated:
        print(f"  New pairs: {pairs_generated} (targeted at weaknesses)")
    print(f"  Time:      {elapsed/60:.0f}m")

    # Baselines for reference
    print(f"\n  Baselines:")
    print(f"    qwen3:14b (baseline):  0.741")
    print(f"    hiveai-v1 (14B LoRA):  0.853 (+15%)")

    # History
    history = load_history()
    if len(history) > 1:
        prev = history[-2]
        prev_score = prev.get("eval_score", 0)
        if eval_data:
            delta = score - prev_score
            print(f"\n  vs last cycle: {delta:+.3f} ({'improved' if delta > 0 else 'regressed'})")

    # Next steps
    print(f"\n  Next steps:")
    if weaknesses:
        print(f"    1. Review weakness patches in {WEAKNESS_PATCHES_DIR}/")
        print(f"    2. Start next training: python scripts/improve.py")
    else:
        print(f"    All categories above threshold -- consider:")
        print(f"    1. Adding more challenging eval questions")
        print(f"    2. Raising the threshold")
        print(f"    3. Adding new training domains")

    print("=" * 65)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def show_status():
    """Show the current state of the improvement loop."""
    print("\n" + "=" * 60)
    print("  HiveAI Improvement Loop Status")
    print("=" * 60)

    # Adapter
    adapter_file = ADAPTER_DIR / "adapter_model.safetensors"
    if adapter_file.exists():
        size_mb = adapter_file.stat().st_size / 1e6
        print(f"\n  Adapter:   {ADAPTER_DIR} ({size_mb:.0f} MB)")
    else:
        print(f"\n  Adapter:   NOT FOUND (training needed)")

    # GGUF
    if GGUF_DIR.exists():
        ggufs = list(GGUF_DIR.glob("*.gguf"))
        if ggufs:
            gguf = ggufs[0]
            print(f"  GGUF:      {gguf} ({gguf.stat().st_size/1e9:.1f} GB)")
        else:
            print(f"  GGUF:      NOT FOUND (deploy needed)")
    else:
        print(f"  GGUF:      NOT FOUND (deploy needed)")

    # Training data
    if TRAINING_DATA.exists():
        pair_count = sum(1 for _ in open(TRAINING_DATA, encoding="utf-8"))
        size_mb = TRAINING_DATA.stat().st_size / 1e6
        print(f"  Data:      {TRAINING_DATA.name} ({pair_count} pairs, {size_mb:.0f} MB)")
    else:
        print(f"  Data:      NOT FOUND")

    # Evals
    evals_dir = PROJECT_ROOT / "evals"
    if evals_dir.exists():
        evals = sorted(evals_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if evals:
            latest = json.loads(evals[0].read_text(encoding="utf-8"))
            model = latest.get("model", "?")
            score = latest.get("overall_score", 0)
            ts = latest.get("timestamp", "?")[:19]
            print(f"  Last eval: {model} = {score:.3f} ({ts})")

    # Weakness patches
    if WEAKNESS_PATCHES_DIR.exists():
        patches = list(WEAKNESS_PATCHES_DIR.glob("*.jsonl"))
        if patches:
            total = sum(sum(1 for _ in open(p, encoding="utf-8")) for p in patches)
            print(f"  Patches:   {len(patches)} files, {total} pairs")

    # Cycle history
    history = load_history()
    if history:
        print(f"\n  Cycle History ({len(history)} cycles):")
        print(f"  {'#':>3}  {'Model':15}  {'Score':>6}  {'Pairs':>5}  {'Date':12}")
        for h in history[-5:]:
            print(f"  {h.get('cycle', '?'):>3}  {h.get('model', '?'):15}  "
                  f"{h.get('eval_score', 0):6.3f}  {h.get('pairs', 0):>5}  "
                  f"{h.get('timestamp', '?')[:10]:12}")

    # llama-server status
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{LLAMA_SERVER_URL}/health", timeout=3)
        print(f"\n  llama-server: RUNNING ({LLAMA_SERVER_URL})")
    except Exception:
        print(f"\n  llama-server: NOT RUNNING")

    # Training status (check WSL)
    try:
        result = subprocess.run(
            ["wsl", "-d", WSL_DISTRO, "--", "pgrep", "-f", "train_v5.py"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print(f"  Training:   IN PROGRESS (WSL)")
        else:
            print(f"  Training:   idle")
    except Exception:
        print(f"  Training:   unknown")

    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="HiveAI Continuous Improvement Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/improve.py                  # full cycle
  python scripts/improve.py --skip-train     # skip training (adapter exists)
  python scripts/improve.py --skip-deploy    # skip deploy (just eval + hunt)
  python scripts/improve.py --status         # show loop state
  python scripts/improve.py --plan           # dry run
        """
    )
    parser.add_argument("--skip-train", action="store_true", help="Skip training step")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip deploy step")
    parser.add_argument("--skip-hunt", action="store_true", help="Skip weakness hunting")
    parser.add_argument("--skip-prep", action="store_true", help="Skip data prep for next cycle")
    parser.add_argument("--no-generate", action="store_true",
                        help="Analyze weaknesses but don't generate pairs")
    parser.add_argument("--quant", default=DEFAULT_QUANT, help=f"GGUF quantization (default: {DEFAULT_QUANT})")
    parser.add_argument("--pairs", type=int, default=15, help="Pairs per weak category (default: 15)")
    parser.add_argument("--status", action="store_true", help="Show current loop status")
    parser.add_argument("--plan", action="store_true", help="Dry run: show what would happen")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.plan:
        print("\n  Improvement Cycle Plan:")
        print(f"  1. TRAIN:  {'SKIP' if args.skip_train else f'WSL + Unsloth on {TRAINING_DATA.name}'}")
        print(f"  2. DEPLOY: {'SKIP' if args.skip_deploy else f'Merge + GGUF ({args.quant}) -> llama-server'}")
        print(f"  3. EVAL:   run_eval.py --model {MODEL_NAME} --base-url {LLAMA_SERVER_URL}")
        print(f"  4. HUNT:   {'SKIP' if args.skip_hunt else f'weakness_hunter.py ({args.pairs} pairs/cat)'}")
        print(f"  5. PREP:   {'SKIP' if args.skip_prep else f'Rebuild {NEXT_VERSION}.jsonl with patches'}")
        return

    cycle_start = time.time()
    gguf_path = None
    eval_data = None
    weaknesses = []
    pairs_generated = 0

    # TRAIN
    if not args.skip_train:
        if not step_train():
            logger.error("Training failed -- aborting cycle")
            sys.exit(1)

    # DEPLOY
    if not args.skip_deploy:
        gguf_path = step_deploy(quant=args.quant)
        if not gguf_path:
            logger.error("Deploy failed -- aborting cycle")
            sys.exit(1)

    # EVAL
    eval_data = step_eval()
    if not eval_data:
        logger.warning("Eval failed or llama-server not running")
        logger.info("Start llama-server and re-run with: --skip-train --skip-deploy")
        # Still save partial cycle
        history = load_history()
        history.append({
            "cycle": len(history) + 1,
            "model": MODEL_NAME,
            "eval_score": 0,
            "pairs": 0,
            "timestamp": datetime.now().isoformat(),
            "status": "eval_failed",
        })
        save_history(history)
        sys.exit(1)

    # HUNT
    if not args.skip_hunt:
        from scripts.weakness_hunter import analyze_weaknesses
        weaknesses = analyze_weaknesses(eval_data, threshold=0.75)
        if weaknesses and not args.no_generate:
            pairs = step_hunt(eval_data, generate=True, pairs_per_category=args.pairs)
            pairs_generated = len(pairs)
        elif weaknesses:
            step_hunt(eval_data, generate=False)

    # PREP
    if not args.skip_prep and pairs_generated > 0:
        step_prep()

    # REPORT
    step_report(eval_data, weaknesses, pairs_generated, gguf_path, cycle_start)

    # Save cycle to history
    history = load_history()
    history.append({
        "cycle": len(history) + 1,
        "model": MODEL_NAME,
        "eval_score": eval_data.get("overall_score", 0) if eval_data else 0,
        "pairs": pairs_generated,
        "weaknesses": len(weaknesses),
        "timestamp": datetime.now().isoformat(),
        "status": "complete",
    })
    save_history(history)


if __name__ == "__main__":
    main()
