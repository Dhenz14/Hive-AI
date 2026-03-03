"""
Post-training deployment script for HiveAI LoRA v2 (Qwen3.5-35B-A3B).

Run this in a separate terminal once training is complete (or let it
watch the log and fire automatically):

    python scripts/deploy_v2.py           # watch mode: waits for training
    python scripts/deploy_v2.py --now     # deploy immediately (training assumed done)
    python scripts/deploy_v2.py --eval    # deploy + run eval

What it does:
    1. Waits for training_meta.json to appear (confirms training done)
    2. Verifies the adapter files are present
    3. Converts adapter to GGUF via llama.cpp
    4. Stops any existing llama-server
    5. Starts llama-server with v2 adapter + Qwen3.5-35B-A3B base
    6. Updates .env  LLAMA_SERVER_MODEL=hiveai-v2
    7. Updates lora_versions DB row to 'ready'
    8. Optionally runs eval (--eval flag)
    9. Prints next steps
"""
import argparse
import json
import logging
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_DIR  = os.path.join(PROJECT_ROOT, "loras", "v2")
META_FILE    = os.path.join(ADAPTER_DIR, "training_meta.json")
ADAPTER_GGUF = os.path.join(ADAPTER_DIR, "hiveai-v2-lora.gguf")
ENV_FILE     = os.path.join(PROJECT_ROOT, ".env")
DB_FILE      = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")

# --- v2 uses Qwen3.5-35B-A3B base (not Qwen3-14B) ---
BASE_GGUF       = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "Qwen3.5-35B-A3B-Q4_K_M.gguf")
BASE_MODEL_ID   = "unsloth/Qwen3.5-35B-A3B"
CONVERT_SCRIPT  = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
LLAMA_SERVER    = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"
LLAMA_PORT      = 11435

MODEL_NAME      = "hiveai-v2"
VERSION_TAG     = "v2.0"


# ---------------------------------------------------------------------------
# Step 1: Wait for training to finish
# ---------------------------------------------------------------------------

def wait_for_training(poll_seconds=30):
    logger.info("Watching for training completion...")
    while not os.path.exists(META_FILE):
        logger.info(f"  training_meta.json not found yet, checking again in {poll_seconds}s")
        time.sleep(poll_seconds)
    logger.info("training_meta.json found -- training complete!")
    with open(META_FILE) as f:
        meta = json.load(f)
    logger.info(f"  loss={meta.get('loss')}  time={meta.get('training_time_s')}s  pairs={meta.get('pair_count')}")
    return meta


# ---------------------------------------------------------------------------
# Step 2: Verify adapter files
# ---------------------------------------------------------------------------

def verify_adapter():
    required = ["adapter_config.json", "adapter_model.safetensors"]
    missing = [f for f in required if not os.path.exists(os.path.join(ADAPTER_DIR, f))]
    if missing:
        logger.error(f"Missing adapter files: {missing}")
        sys.exit(1)
    logger.info("Adapter files verified OK")
    for f in required:
        path = os.path.join(ADAPTER_DIR, f)
        size_mb = os.path.getsize(path) / 1024 / 1024
        logger.info(f"  {f}: {size_mb:.1f} MB")


# ---------------------------------------------------------------------------
# Step 3: GGUF conversion
# ---------------------------------------------------------------------------

def convert_gguf():
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"GGUF already exists: {ADAPTER_GGUF} ({size_mb:.0f} MB) -- skipping conversion")
        return True

    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning(f"convert_lora_to_gguf.py not found at {CONVERT_SCRIPT} -- skipping GGUF")
        logger.warning(f"Manual: python convert_lora_to_gguf.py --base-model-id {BASE_MODEL_ID} {ADAPTER_DIR}")
        return False

    logger.info("Converting LoRA adapter to GGUF...")
    cmd = [sys.executable, CONVERT_SCRIPT, "--base-model-id", BASE_MODEL_ID, ADAPTER_DIR]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error(f"GGUF conversion failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[:1000])
        return False

    # Rename whatever .gguf was produced
    for fname in os.listdir(ADAPTER_DIR):
        if fname.endswith(".gguf") and fname != "hiveai-v2-lora.gguf":
            src = os.path.join(ADAPTER_DIR, fname)
            os.rename(src, ADAPTER_GGUF)
            logger.info(f"  Renamed {fname} -> hiveai-v2-lora.gguf")
            break

    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"GGUF created: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        return True

    logger.error("Conversion succeeded but no .gguf file found")
    return False


# ---------------------------------------------------------------------------
# Step 4: Kill existing llama-server
# ---------------------------------------------------------------------------

def stop_llama_server():
    result = subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        capture_output=True, text=True
    )
    if "SUCCESS" in result.stdout or "success" in result.stdout.lower():
        logger.info("Stopped existing llama-server")
        time.sleep(3)
    else:
        logger.info("No existing llama-server to stop")


# ---------------------------------------------------------------------------
# Step 5: Start llama-server with v2 adapter
# ---------------------------------------------------------------------------

def start_llama_server():
    if not os.path.exists(ADAPTER_GGUF):
        logger.warning("GGUF not available -- cannot start llama-server with adapter")
        logger.warning(f"Start manually:\n  {LLAMA_SERVER} -m \"{BASE_GGUF}\" --lora \"{ADAPTER_GGUF}\" --port {LLAMA_PORT} --n-gpu-layers 999 --ctx-size 16384 --threads 2 -b 4096 -fa --cache-type-k q8_0 --cache-type-v q4_0 --no-mmap --mlock")
        return False

    if not os.path.exists(BASE_GGUF):
        logger.error(f"Base GGUF not found: {BASE_GGUF}")
        logger.error("Download with: huggingface-cli download unsloth/Qwen3.5-35B-A3B-GGUF Qwen3.5-35B-A3B-Q4_K_M.gguf --local-dir models/qwen3.5-35b-a3b/")
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "llama_server_v2.log")

    cmd = [
        LLAMA_SERVER,
        "-m", BASE_GGUF,
        "--lora", ADAPTER_GGUF,
        "--port", str(LLAMA_PORT),
        "--n-gpu-layers", "999",
        # --- Optimized for MoE on 16GB VRAM ---
        "--ctx-size", "16384",          # doubled context for longer code generation
        "--threads", "2",               # MoE expert dispatch is GPU-bound, fewer CPU threads
        "-b", "4096",                   # larger batch for prompt processing throughput
        "-fa",                          # flash attention: 30-40% faster attention, less VRAM
        "--cache-type-k", "q8_0",       # quantized KV cache keys (~50% VRAM savings)
        "--cache-type-v", "q4_0",       # quantized KV cache values (~75% VRAM savings)
        "--no-mmap",                    # load model fully into RAM, avoid page faults
        "--mlock",                      # pin model memory, prevent swapping
    ]
    logger.info(f"Starting llama-server v2 on port {LLAMA_PORT}...")
    logger.info(f"  Base:    {BASE_GGUF}")
    logger.info(f"  Adapter: {ADAPTER_GGUF}")

    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        )

    logger.info(f"llama-server started (PID {proc.pid}), log: {log_path}")

    # Wait up to 240s for server to be ready (19.7GB model with --no-mmap --mlock
    # needs to be fully paged in before responding, typically 90-120s on NVMe)
    import urllib.request
    for i in range(240):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{LLAMA_PORT}/health", timeout=2)
            logger.info(f"llama-server ready after {i+1}s")
            return True
        except Exception:
            if (i + 1) % 30 == 0:
                logger.info(f"Still waiting for llama-server... ({i+1}s)")
    logger.warning("llama-server didn't respond within 240s -- check log")
    return False


# ---------------------------------------------------------------------------
# Step 6: Update .env
# ---------------------------------------------------------------------------

def update_env():
    if not os.path.exists(ENV_FILE):
        logger.warning(f".env file not found at {ENV_FILE} -- skipping")
        return

    with open(ENV_FILE, "r") as f:
        content = f.read()

    # Update LLAMA_SERVER_MODEL
    if "LLAMA_SERVER_MODEL=" in content:
        content = re.sub(r"^LLAMA_SERVER_MODEL=.*$", f"LLAMA_SERVER_MODEL={MODEL_NAME}", content, flags=re.MULTILINE)
    else:
        content += f"\nLLAMA_SERVER_MODEL={MODEL_NAME}\n"

    # Ensure hiveai-v2 is in LLAMA_SERVER_MODELS list
    models_match = re.search(r"^LLAMA_SERVER_MODELS=(.*)$", content, re.MULTILINE)
    if models_match:
        current_models = models_match.group(1)
        if MODEL_NAME not in current_models:
            new_models = current_models.rstrip() + f",{MODEL_NAME}"
            content = re.sub(r"^LLAMA_SERVER_MODELS=.*$", f"LLAMA_SERVER_MODELS={new_models}", content, flags=re.MULTILINE)
    else:
        content += f"LLAMA_SERVER_MODELS=hiveai-v1,hiveai-v1.5,{MODEL_NAME}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)
    logger.info(f".env updated: LLAMA_SERVER_MODEL={MODEL_NAME}")


# ---------------------------------------------------------------------------
# Step 7: Update DB
# ---------------------------------------------------------------------------

def update_db(meta):
    if not os.path.exists(DB_FILE):
        logger.warning(f"Database not found at {DB_FILE} -- skipping DB update")
        return

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        "UPDATE lora_versions SET status=?, benchmark_score=?, adapter_path=? WHERE version=? AND status='training'",
        ('ready', meta.get('loss'), ADAPTER_DIR, VERSION_TAG)
    )
    if cur.rowcount == 0:
        # Row might not exist; insert it
        cur.execute(
            "INSERT INTO lora_versions (version, base_model, pair_count, benchmark_score, adapter_path, status, created_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (VERSION_TAG, BASE_MODEL_ID, meta.get('pair_count', 0),
             meta.get('loss'), ADAPTER_DIR, 'ready')
        )
    con.commit()
    con.close()
    logger.info(f"DB updated: {VERSION_TAG} -> ready (loss={meta.get('loss')})")


# ---------------------------------------------------------------------------
# Step 8: Run eval
# ---------------------------------------------------------------------------

def run_eval():
    eval_script = os.path.join(PROJECT_ROOT, "scripts", "run_eval.py")
    if not os.path.exists(eval_script):
        logger.warning("run_eval.py not found -- skipping eval")
        return None

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "eval_v2.log")
    logger.info(f"Running eval for {MODEL_NAME} -> {log_path}")
    logger.info(f"  This evaluates against all 115 challenges (100 general + 15 Hive)")

    cmd = [
        sys.executable, eval_script,
        "--model", MODEL_NAME,
        "--base-url", f"http://localhost:{LLAMA_PORT}",
    ]
    logger.info(f"  {' '.join(cmd)}")
    with open(log_path, "w") as log_f:
        result = subprocess.run(cmd, stdout=log_f, stderr=log_f, timeout=7200)

    score = None
    if result.returncode == 0:
        with open(log_path) as f:
            eval_out = f.read()
        score_match = re.search(r"Overall.*?(0\.\d+)", eval_out)
        if score_match:
            score = float(score_match.group(1))
            logger.info(f"Eval complete: score={score:.3f}")
            # Update DB with benchmark score
            if os.path.exists(DB_FILE):
                con = sqlite3.connect(DB_FILE)
                con.execute(f"UPDATE lora_versions SET benchmark_score=? WHERE version='{VERSION_TAG}'", (score,))
                con.commit()
                con.close()
        else:
            logger.info("Eval complete (score not parsed from output)")
    else:
        logger.warning(f"Eval exited with code {result.returncode}")

    return score


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deploy HiveAI LoRA v2 (Qwen3.5-35B-A3B)")
    parser.add_argument("--now", action="store_true", help="Skip waiting, deploy immediately")
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--skip-server", action="store_true", help="Skip llama-server start (GGUF convert only)")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI LoRA v2 -- Post-Training Deployment")
    print(f"  Base: Qwen3.5-35B-A3B (MoE, 256 experts, 3B active)")
    print(f"  Adapter: {ADAPTER_DIR}")
    print("=" * 60)

    # 1. Wait / check
    if args.now and os.path.exists(META_FILE):
        logger.info("--now flag: loading existing training_meta.json")
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"  loss={meta.get('loss')}  pairs={meta.get('pair_count')}")
    elif os.path.exists(META_FILE):
        logger.info("training_meta.json already exists")
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"  loss={meta.get('loss')}  pairs={meta.get('pair_count')}")
    else:
        meta = wait_for_training()

    # 2. Verify adapter
    verify_adapter()

    # 3. GGUF conversion
    gguf_ok = convert_gguf()

    if args.skip_server:
        logger.info("--skip-server flag: skipping llama-server steps")
        print("\n" + "=" * 60)
        print("  GGUF Conversion Complete!")
        print("=" * 60)
        if gguf_ok:
            size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
            print(f"\n  GGUF:     {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        print(f"\n  To start llama-server manually:")
        print(f'    "{LLAMA_SERVER}" -m "{BASE_GGUF}" --lora "{ADAPTER_GGUF}" --port {LLAMA_PORT} --n-gpu-layers 999 --ctx-size 16384 --threads 2 -b 4096 -fa --cache-type-k q8_0 --cache-type-v q4_0 --no-mmap --mlock')
        print("=" * 60)
        return

    # 4. Kill old llama-server
    stop_llama_server()

    # 5. Start new llama-server
    server_ok = False
    if gguf_ok:
        server_ok = start_llama_server()

    if not server_ok and gguf_ok:
        logger.error("v2 server failed to start! NOT updating .env or DB to prevent broken state.")
        logger.error("Fix the issue and re-run with --now, or manually start llama-server.")
        print("\n  DEPLOYMENT FAILED: server did not start. System state unchanged.")
        sys.exit(1)

    # 6. Update .env (only if server is healthy)
    update_env()

    # 7. Update DB
    update_db(meta)

    # 8. Eval (optional)
    score = None
    if args.eval and server_ok:
        score = run_eval()

    # Summary
    print("\n" + "=" * 60)
    print("  v2 Deployment Complete!")
    print("=" * 60)
    print(f"\n  Model:    {MODEL_NAME} (Qwen3.5-35B-A3B + LoRA)")
    print(f"  Adapter:  {ADAPTER_DIR}")
    if gguf_ok:
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  GGUF:     {ADAPTER_GGUF} ({size_mb:.0f} MB)")
    if server_ok:
        print(f"\n  llama-server: http://localhost:{LLAMA_PORT}")
    print(f"  Active model: {MODEL_NAME}")
    if score is not None:
        print(f"  Eval score:   {score:.3f}")
    print(f"\n  Baselines for comparison:")
    print(f"    qwen3:14b (baseline):  0.741")
    print(f"    hiveai-v1 (Qwen3-14B): 0.853 (+15%)")
    print(f"\n  To run eval manually:")
    print(f"    python scripts/run_eval.py --model {MODEL_NAME} --base-url http://localhost:{LLAMA_PORT}")
    print(f"\n  To test chat:")
    print(f"    curl -X POST http://localhost:{LLAMA_PORT}/v1/chat/completions \\")
    print(f'      -H "Content-Type: application/json" \\')
    print(f'      -d \'{{"model": "{MODEL_NAME}", "messages": [{{"role": "user", "content": "Write a Python function to post to Hive"}}]}}\'')
    print("=" * 60)


if __name__ == "__main__":
    main()
