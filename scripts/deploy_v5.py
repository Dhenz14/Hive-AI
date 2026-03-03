"""
Post-training deployment for HiveAI LoRA v5 (Qwen3.5-9B Dense).

    python scripts/deploy_v5.py           # watch for training completion
    python scripts/deploy_v5.py --now     # deploy immediately
    python scripts/deploy_v5.py --eval    # deploy + run eval

What it does:
    1. Waits for training_meta.json (confirms training done)
    2. Verifies adapter files
    3. Merges LoRA into base weights (PEFT merge_and_unload)
    4. Exports merged model to GGUF (Q8_0 for max quality, ~12GB)
    5. Creates Ollama Modelfile + registers model
    6. Quick sanity test (generate one response)
    7. Updates .env (OLLAMA_MODEL_REASONING=hiveai-v5)
    8. Updates lora_versions DB row
    9. Optionally runs full eval (--eval)

Dense advantage: Ollama supports Qwen3.5-9B natively — no llama-server needed!
"""
import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hiveai.lora.merge_cycle import (
    merge_model,
    verify_adapter_files,
    verify_merged_model,
    export_gguf as _export_gguf,
    create_ollama_model as _create_ollama_model,
    run_eval as _run_eval,
    DEFAULT_SYSTEM_PROMPT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_DIR = os.path.join(PROJECT_ROOT, "loras", "v5")
META_FILE = os.path.join(ADAPTER_DIR, "training_meta.json")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
DB_FILE = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
MERGED_DIR = os.path.join(PROJECT_ROOT, "models", "hiveai-v5-merged")
GGUF_FILE = os.path.join(PROJECT_ROOT, "models", "hiveai-v5-merged", "hiveai-v5.gguf")
MODELFILE = os.path.join(PROJECT_ROOT, "models", "hiveai-v5-merged", "Modelfile")

BASE_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "qwen3.5-9b")
MODEL_NAME = "hiveai-v5"
VERSION_TAG = "v5.0"

OLLAMA_URL = "http://localhost:11434"

# System prompt baked into the Modelfile
SYSTEM_PROMPT = (
    "You are HiveAI, an expert coding assistant specialized in Python, JavaScript, "
    "blockchain development (especially Hive), and software engineering best practices. "
    "Write clean, correct, well-documented code. Include practical examples with "
    "complete, runnable code. Explain your reasoning and trade-offs."
)


# ---------------------------------------------------------------------------
# Step 1: Wait for training
# ---------------------------------------------------------------------------
def wait_for_training(poll_seconds=30):
    logger.info("Watching for training completion...")
    while not os.path.exists(META_FILE):
        logger.info(f"  training_meta.json not found, checking in {poll_seconds}s")
        time.sleep(poll_seconds)
    logger.info("training_meta.json found -- training complete!")
    with open(META_FILE) as f:
        meta = json.load(f)
    logger.info(f"  loss={meta.get('loss')}  time={meta.get('training_time_s')}s  "
                f"pairs={meta.get('pair_count')}")
    return meta


# ---------------------------------------------------------------------------
# Step 2: Verify adapter files
# ---------------------------------------------------------------------------
def verify_adapter():
    if not verify_adapter_files(ADAPTER_DIR):
        sys.exit(1)
    logger.info("Adapter files verified OK")


# ---------------------------------------------------------------------------
# Step 3: Merge LoRA into base weights (delegates to merge_cycle)
# ---------------------------------------------------------------------------
def merge_adapter():
    return merge_model(BASE_MODEL_PATH, ADAPTER_DIR, MERGED_DIR)


# ---------------------------------------------------------------------------
# Step 4: Export to GGUF (delegates to merge_cycle)
# ---------------------------------------------------------------------------
def export_gguf(quant="Q8_0"):
    return _export_gguf(MERGED_DIR, GGUF_FILE, quant=quant)


# ---------------------------------------------------------------------------
# Step 5: Create Ollama model (delegates to merge_cycle)
# ---------------------------------------------------------------------------
def create_ollama_model():
    return _create_ollama_model(GGUF_FILE, MODEL_NAME, system_prompt=SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Step 6: Sanity test
# ---------------------------------------------------------------------------
def sanity_test():
    """Quick test: generate one response to verify model works."""
    logger.info("Running sanity test...")
    prompt = "Write a Python function to calculate the fibonacci sequence."

    data = json.dumps({
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 256},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        t0 = time.time()
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode())
        elapsed = time.time() - t0
        content = result["message"]["content"]

        has_code = "def " in content or "```" in content
        has_fib = "fib" in content.lower()
        word_count = len(content.split())

        logger.info(f"  Response: {word_count} words, {elapsed:.1f}s")
        logger.info(f"  Has code: {has_code}, has 'fib': {has_fib}")

        if has_code and has_fib:
            logger.info("  SANITY TEST PASSED")
            return True
        else:
            logger.warning("  SANITY TEST: response didn't contain expected code")
            logger.info(f"  First 300 chars: {content[:300]}")
            return False
    except Exception as e:
        logger.error(f"  SANITY TEST FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 7: Update .env
# ---------------------------------------------------------------------------
def update_env():
    if not os.path.exists(ENV_FILE):
        logger.warning(f".env not found at {ENV_FILE} -- skipping")
        return

    with open(ENV_FILE, "r") as f:
        content = f.read()

    # Update reasoning model
    if "OLLAMA_MODEL_REASONING=" in content:
        content = re.sub(
            r"^OLLAMA_MODEL_REASONING=.*$",
            f"OLLAMA_MODEL_REASONING={MODEL_NAME}",
            content, flags=re.MULTILINE,
        )
    else:
        content += f"\nOLLAMA_MODEL_REASONING={MODEL_NAME}\n"

    # Keep fast model as raw base for simple queries
    if "OLLAMA_MODEL_FAST=" not in content:
        content += "OLLAMA_MODEL_FAST=qwen3.5:9b\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)
    logger.info(f".env updated: OLLAMA_MODEL_REASONING={MODEL_NAME}")


# ---------------------------------------------------------------------------
# Step 8: Update DB
# ---------------------------------------------------------------------------
def update_db(meta):
    if not os.path.exists(DB_FILE):
        logger.warning(f"Database not found at {DB_FILE} -- skipping")
        return

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        "UPDATE lora_versions SET status=?, benchmark_score=?, adapter_path=? "
        "WHERE version=? AND status='training'",
        ("ready", meta.get("loss"), ADAPTER_DIR, VERSION_TAG),
    )
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO lora_versions "
            "(version, base_model, pair_count, benchmark_score, adapter_path, status, created_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (VERSION_TAG, "Qwen/Qwen3.5-9B", meta.get("pair_count", 0),
             meta.get("loss"), ADAPTER_DIR, "ready"),
        )
    con.commit()
    con.close()
    logger.info(f"DB updated: {VERSION_TAG} -> ready")


# ---------------------------------------------------------------------------
# Step 9: Run eval (delegates to merge_cycle, plus DB update)
# ---------------------------------------------------------------------------
def run_eval():
    score = _run_eval(MODEL_NAME)
    if score is not None and os.path.exists(DB_FILE):
        con = sqlite3.connect(DB_FILE)
        con.execute(
            "UPDATE lora_versions SET benchmark_score=? WHERE version=?",
            (score, VERSION_TAG),
        )
        con.commit()
        con.close()
    return score


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Deploy HiveAI LoRA v5 (Qwen3.5-9B Dense)")
    parser.add_argument("--now", action="store_true", help="Skip waiting, deploy immediately")
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--skip-merge", action="store_true", help="Skip merge (GGUF already exists)")
    parser.add_argument("--quant", default="Q8_0", help="GGUF quantization (default: Q8_0)")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI LoRA v5 -- Post-Training Deployment")
    print(f"  Base: Qwen3.5-9B (Dense, 9B active params)")
    print(f"  Adapter: {ADAPTER_DIR}")
    print(f"  Target: Ollama native (no llama-server needed!)")
    print("=" * 60)

    # 1. Wait / check
    if args.now and os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"Training meta: loss={meta.get('loss')}  pairs={meta.get('pair_count')}")
    elif os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"Training meta: loss={meta.get('loss')}  pairs={meta.get('pair_count')}")
    else:
        meta = wait_for_training()

    # 2. Verify adapter
    verify_adapter()

    # 3. Merge LoRA into base
    if not args.skip_merge:
        merge_ok = merge_adapter()
        if not merge_ok:
            logger.error("Merge failed! Cannot proceed to GGUF export.")
            logger.error("Fix the issue and re-run, or use --skip-merge if GGUF exists")
            sys.exit(1)

    # 4. Export to GGUF
    gguf_ok = export_gguf(quant=args.quant)
    if not gguf_ok:
        logger.error("GGUF export failed!")
        logger.error("Manual: python convert_hf_to_gguf.py models/hiveai-v5-merged "
                      f"--outfile {GGUF_FILE} --outtype {args.quant.lower()}")
        sys.exit(1)

    # 5. Create Ollama model
    ollama_ok = create_ollama_model()
    if not ollama_ok:
        logger.error("Ollama model creation failed!")
        logger.error(f"Manual: ollama create {MODEL_NAME} -f {MODELFILE}")
        sys.exit(1)

    # 6. Sanity test
    sanity_ok = sanity_test()

    # 7. Update .env
    update_env()

    # 8. Update DB
    update_db(meta)

    # 9. Eval (optional)
    score = None
    if args.eval:
        score = run_eval()

    # Summary
    print("\n" + "=" * 60)
    print("  v5 Deployment Complete!")
    print("=" * 60)
    print(f"\n  Model:     {MODEL_NAME} (Qwen3.5-9B Dense + LoRA merged)")
    print(f"  Adapter:   {ADAPTER_DIR}")
    gguf_size = os.path.getsize(GGUF_FILE) / 1024**3 if os.path.exists(GGUF_FILE) else 0
    print(f"  GGUF:      {GGUF_FILE} ({gguf_size:.1f} GB)")
    print(f"  Quant:     {args.quant}")
    print(f"  Ollama:    {MODEL_NAME}")
    if sanity_ok:
        print(f"  Sanity:    PASSED")
    if score is not None:
        print(f"  Eval:      {score:.3f}")
    print(f"\n  Routing:   OLLAMA_MODEL_REASONING={MODEL_NAME}")
    print(f"             OLLAMA_MODEL_FAST=qwen3.5:9b")
    print(f"\n  Baselines:")
    print(f"    qwen3:14b (baseline):  0.741")
    print(f"    hiveai-v1 (14B LoRA):  0.853 (+15%)")
    print(f"\n  Run eval:  python scripts/run_eval.py --model {MODEL_NAME}")
    print(f"  Anchors:   python scripts/calibrate_eval.py --model {MODEL_NAME}")
    print(f"  Chat test: curl {OLLAMA_URL}/api/chat -d '{{\"model\":\"{MODEL_NAME}\","
          f"\"messages\":[{{\"role\":\"user\",\"content\":\"Write a Hive API call\"}}]}}'")
    print("=" * 60)


if __name__ == "__main__":
    main()
