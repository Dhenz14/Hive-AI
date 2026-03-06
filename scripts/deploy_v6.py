#!/usr/bin/env python3
"""
Post-training deployment for HiveAI LoRA v6 (Qwen2.5-Coder-14B QLoRA).

    python scripts/deploy_v6.py                  # merge + export GGUF
    python scripts/deploy_v6.py --eval            # + run eval after deploy
    python scripts/deploy_v6.py --skip-merge      # skip merge, GGUF already exists
    python scripts/deploy_v6.py --quant q5_k_m    # different quantization

Pipeline:
    1. Verify adapter files in loras/v6/
    2. Load base model + LoRA adapter via Unsloth
    3. Merge LoRA into base weights (save_pretrained_merged)
    4. Export merged model to GGUF (Q5_K_M for quality/size balance)
    5. Copy GGUF to Windows models/ for llama-server
    6. Sanity test via llama-server
    7. Run eval (optional)

NOTE: This uses llama-server (not Ollama) — the GGUF file is loaded directly.
Run this script in WSL2 where Unsloth is available.
"""
import argparse
import json
import logging
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_DIR = os.path.join(PROJECT_ROOT, "loras", "v6")
META_FILE = os.path.join(ADAPTER_DIR, "training_meta.json")
MERGED_DIR = os.path.join(PROJECT_ROOT, "models", "hiveai-v6-merged")

# Qwen2.5-Coder-14B base (Unsloth pre-quantized)
UNSLOTH_MODEL = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"

# Output GGUF — goes into models/ for llama-server
GGUF_DIR = os.path.join(PROJECT_ROOT, "models", "hiveai-v6")
DEFAULT_QUANT = "q5_k_m"

MODEL_NAME = "hiveai-v6"
VERSION_TAG = "v6.0"

LLAMA_SERVER_URL = "http://localhost:11435"


def verify_adapter():
    """Check that adapter files exist."""
    required = ["adapter_model.safetensors", "adapter_config.json"]
    for fname in required:
        fpath = os.path.join(ADAPTER_DIR, fname)
        if not os.path.exists(fpath):
            logger.error(f"Missing adapter file: {fpath}")
            return False
    logger.info(f"Adapter files verified in {ADAPTER_DIR}")

    if os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"  Training meta: loss={meta.get('loss')}, "
                     f"pairs={meta.get('pair_count')}, "
                     f"time={meta.get('training_time_s', 0) / 3600:.1f}h")
    return True


def merge_and_export_gguf(quant: str = DEFAULT_QUANT):
    """Load adapter, merge into base, export as GGUF in one shot.

    Unsloth's save_pretrained_gguf handles merge + GGUF export together,
    which is more memory-efficient than a two-step process.
    """
    from unsloth import FastLanguageModel

    logger.info(f"Loading base model + LoRA adapter from {ADAPTER_DIR}")
    t0 = time.time()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    logger.info(f"Model + adapter loaded in {time.time() - t0:.1f}s")

    # Export GGUF (merge + quantize in one step)
    os.makedirs(GGUF_DIR, exist_ok=True)
    logger.info(f"Exporting GGUF ({quant}) to {GGUF_DIR}")
    t1 = time.time()

    model.save_pretrained_gguf(
        GGUF_DIR,
        tokenizer,
        quantization_method=quant,
    )
    logger.info(f"GGUF export complete in {time.time() - t1:.1f}s")

    # Find the generated GGUF file
    gguf_files = [f for f in os.listdir(GGUF_DIR) if f.endswith(".gguf")]
    if gguf_files:
        gguf_path = os.path.join(GGUF_DIR, gguf_files[0])
        size_gb = os.path.getsize(gguf_path) / 1e9
        logger.info(f"GGUF: {gguf_path} ({size_gb:.2f} GB)")
        return gguf_path
    else:
        logger.error("No GGUF file found after export!")
        return None


def save_merged_hf(save_16bit: bool = False):
    """Optionally save merged model in HF format (for future re-quantization)."""
    from unsloth import FastLanguageModel

    logger.info(f"Loading base model + LoRA adapter from {ADAPTER_DIR}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )

    os.makedirs(MERGED_DIR, exist_ok=True)
    if save_16bit:
        logger.info(f"Saving merged model (16-bit) to {MERGED_DIR}")
        model.save_pretrained_merged(MERGED_DIR, tokenizer, save_method="merged_16bit")
    else:
        logger.info(f"Saving merged model (4-bit) to {MERGED_DIR}")
        model.save_pretrained_merged(MERGED_DIR, tokenizer, save_method="merged_4bit")
    logger.info(f"Merged model saved to {MERGED_DIR}")


def sanity_test():
    """Quick test: generate one response via llama-server."""
    import requests

    logger.info("Running sanity test via llama-server...")
    prompt = "Write a Python function that posts a comment on the Hive blockchain."

    try:
        t0 = time.time()
        resp = requests.post(
            f"{LLAMA_SERVER_URL}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.7,
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        elapsed = time.time() - t0

        has_code = "def " in content or "```" in content
        has_hive = "hive" in content.lower() or "beem" in content.lower()
        word_count = len(content.split())

        logger.info(f"  Response: {word_count} words, {elapsed:.1f}s")
        logger.info(f"  Has code: {has_code}, mentions Hive: {has_hive}")

        if has_code:
            logger.info("  SANITY TEST PASSED")
            return True
        else:
            logger.warning("  Response didn't contain code block")
            logger.info(f"  First 300 chars: {content[:300]}")
            return False
    except requests.ConnectionError:
        logger.warning("  llama-server not running — skip sanity test")
        logger.info(f"  Start it with the GGUF file and re-test manually")
        return None
    except Exception as e:
        logger.error(f"  SANITY TEST FAILED: {e}")
        return False


def update_config():
    """Update config.py defaults for v6."""
    config_path = os.path.join(PROJECT_ROOT, "hiveai", "config.py")
    if not os.path.exists(config_path):
        logger.warning(f"config.py not found at {config_path}")
        return

    with open(config_path, "r") as f:
        content = f.read()

    # Update LLAMA_SERVER_MODEL default
    import re
    if 'LLAMA_SERVER_MODEL' in content:
        old = re.search(r'LLAMA_SERVER_MODEL\s*=\s*os\.environ\.get\("LLAMA_SERVER_MODEL",\s*"([^"]+)"\)', content)
        if old and old.group(1) != MODEL_NAME:
            content = content.replace(old.group(0),
                                       f'LLAMA_SERVER_MODEL = os.environ.get("LLAMA_SERVER_MODEL", "{MODEL_NAME}")')
            logger.info(f"  Updated LLAMA_SERVER_MODEL default: {old.group(1)} -> {MODEL_NAME}")

    # Add v6 to LLAMA_SERVER_MODELS
    if MODEL_NAME not in content:
        content = content.replace(
            'hiveai-v1,hiveai-v1.5,hiveai-v2',
            f'hiveai-v1,hiveai-v1.5,hiveai-v2,{MODEL_NAME}'
        )
        logger.info(f"  Added {MODEL_NAME} to LLAMA_SERVER_MODELS")

    with open(config_path, "w") as f:
        f.write(content)
    logger.info("config.py updated")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy HiveAI v6 (Qwen2.5-Coder-14B QLoRA → GGUF → llama-server)"
    )
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--skip-merge", action="store_true", help="Skip merge, use existing GGUF")
    parser.add_argument("--quant", default=DEFAULT_QUANT, help=f"GGUF quantization (default: {DEFAULT_QUANT})")
    parser.add_argument("--save-hf", action="store_true", help="Also save merged HF model (for re-quant)")
    parser.add_argument("--save-16bit", action="store_true", help="Save HF model in 16-bit (large!)")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI v6 — Post-Training Deployment")
    print(f"  Base:    Qwen2.5-Coder-14B-Instruct (QLoRA)")
    print(f"  Adapter: {ADAPTER_DIR}")
    print(f"  Target:  llama-server (GGUF)")
    print(f"  Quant:   {args.quant}")
    print("=" * 60)

    # 1. Verify adapter
    if not verify_adapter():
        sys.exit(1)

    # 2. Merge + Export GGUF
    gguf_path = None
    if not args.skip_merge:
        gguf_path = merge_and_export_gguf(quant=args.quant)
        if not gguf_path:
            logger.error("GGUF export failed!")
            sys.exit(1)
    else:
        gguf_files = [f for f in os.listdir(GGUF_DIR) if f.endswith(".gguf")] if os.path.exists(GGUF_DIR) else []
        if gguf_files:
            gguf_path = os.path.join(GGUF_DIR, gguf_files[0])
            logger.info(f"Using existing GGUF: {gguf_path}")
        else:
            logger.error(f"No GGUF found in {GGUF_DIR} — run without --skip-merge")
            sys.exit(1)

    # 3. Optionally save HF format
    if args.save_hf:
        save_merged_hf(save_16bit=args.save_16bit)

    # 4. Update config
    update_config()

    # 5. Sanity test
    sanity_result = sanity_test()

    # 6. Eval
    score = None
    if args.eval:
        logger.info("Running eval harness...")
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "run_eval.py"),
             "--model", MODEL_NAME,
             "--base-url", LLAMA_SERVER_URL],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            logger.warning("Eval harness returned non-zero exit code")

    # Summary
    gguf_size = os.path.getsize(gguf_path) / 1e9 if gguf_path and os.path.exists(gguf_path) else 0
    print("\n" + "=" * 60)
    print("  v6 Deployment Complete!")
    print("=" * 60)
    print(f"""
  Model:     {MODEL_NAME} (Qwen2.5-Coder-14B + LoRA merged)
  GGUF:      {gguf_path} ({gguf_size:.1f} GB)
  Quant:     {args.quant}

  To serve with llama-server:
    llama-server --model {gguf_path} \\
      --port 11435 --n-gpu-layers 999 --ctx-size 8192 \\
      --flash-attn on --cache-type-k q8_0 --cache-type-v q4_0

  To eval:
    python scripts/run_eval.py --model {MODEL_NAME} --base-url {LLAMA_SERVER_URL}

  Baselines:
    qwen3:14b (baseline):  0.741
    hiveai-v1 (14B LoRA):  0.853 (+15%)
""")
    print("=" * 60)


if __name__ == "__main__":
    main()
