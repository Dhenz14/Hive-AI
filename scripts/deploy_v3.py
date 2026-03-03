"""
Post-training deployment script for HiveAI LoRA v3 (Qwen3.5-35B-A3B pruned).

Run this in a separate terminal once training is complete (or let it
watch the log and fire automatically):

    python scripts/deploy_v3.py           # watch mode: waits for training
    python scripts/deploy_v3.py --now     # deploy immediately (training assumed done)
    python scripts/deploy_v3.py --eval    # deploy + run eval

What it does:
    1. Waits for training_meta.json to appear (confirms training done)
    2. Verifies the adapter files are present
    3. Converts LoRA adapter to GGUF (handles DoRA, local base path)
    4. Converts pruned base model to GGUF Q4_K_M (~12GB vs 19.7GB non-pruned)
    5. Stops any existing llama-server
    6. Starts llama-server with pruned base GGUF + v3 LoRA adapter
    7. Updates .env  LLAMA_SERVER_MODEL=hiveai-v3
    8. Updates lora_versions DB row to 'ready'
    9. Optionally runs eval (--eval flag)

Notes:
    - v3 LoRA was trained on the PRUNED model (128/256 experts, 55% routing).
    - We convert the pruned model to its own GGUF (~12GB Q4_K_M) for inference.
    - Falls back to non-pruned GGUF (19.7GB) if pruned conversion fails.
    - DoRA magnitude vectors are stripped during LoRA GGUF conversion (llama.cpp
      doesn't support DoRA at runtime). Loses ~1-4% of DoRA quality bonus but
      lora_A/lora_B matrices still function as standard LoRA.
"""
import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_DIR  = os.path.join(PROJECT_ROOT, "loras", "v3")
META_FILE    = os.path.join(ADAPTER_DIR, "training_meta.json")
ADAPTER_GGUF = os.path.join(ADAPTER_DIR, "hiveai-v3-lora.gguf")
ENV_FILE     = os.path.join(PROJECT_ROOT, ".env")
DB_FILE      = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")

# --- Pruned GGUF is preferred (smaller, matches training); non-pruned is fallback ---
PRUNED_BASE_GGUF = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned", "Qwen3.5-35B-A3B-pruned-Q4_K_M.gguf")
FALLBACK_GGUF    = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "Qwen3.5-35B-A3B-Q4_K_M.gguf")
# --- Pruned HF model (source for both LoRA GGUF conversion and base GGUF conversion) ---
BASE_HF_DIR      = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")
CONVERT_LORA_SCRIPT = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
CONVERT_HF_SCRIPT   = r"C:\Users\theyc\llama.cpp\convert_hf_to_gguf.py"
LLAMA_QUANTIZE       = r"C:\Users\theyc\llama.cpp\bin\llama-quantize.exe"
LLAMA_SERVER         = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"
LLAMA_PORT           = 11435

MODEL_NAME      = "hiveai-v3"
VERSION_TAG     = "v3.0"


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
# Step 3a: Convert LoRA adapter to GGUF (uses --base for local path, handles DoRA)
# ---------------------------------------------------------------------------

def convert_lora_gguf():
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"LoRA GGUF already exists: {ADAPTER_GGUF} ({size_mb:.0f} MB) -- skipping")
        return True

    if not os.path.exists(CONVERT_LORA_SCRIPT):
        logger.warning(f"convert_lora_to_gguf.py not found at {CONVERT_LORA_SCRIPT}")
        return False

    if not os.path.exists(BASE_HF_DIR):
        logger.error(f"Base model directory not found: {BASE_HF_DIR}")
        return False

    logger.info("Converting LoRA adapter to GGUF...")
    logger.info("  (DoRA magnitude vectors will be stripped -- llama.cpp only supports lora_A/lora_B)")
    cmd = [
        sys.executable, CONVERT_LORA_SCRIPT,
        "--base", BASE_HF_DIR,
        "--outfile", ADAPTER_GGUF,
        "--outtype", "f16",
        ADAPTER_DIR,
    ]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error(f"LoRA GGUF conversion failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[:1000])
        return False

    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"LoRA GGUF created: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        return True

    logger.error("LoRA conversion succeeded but no .gguf file found")
    return False


# ---------------------------------------------------------------------------
# Step 3b: Convert pruned base model to GGUF Q4_K_M (~12GB vs 19.7GB)
# ---------------------------------------------------------------------------

def convert_base_gguf():
    """Convert pruned HF model to GGUF with Q4_K_M quantization.

    Two-step process:
      1. convert_hf_to_gguf.py: HF safetensors -> F16 GGUF (~37GB temp file)
      2. llama-quantize: F16 GGUF -> Q4_K_M GGUF (~12GB final)
    """
    if os.path.exists(PRUNED_BASE_GGUF):
        size_mb = os.path.getsize(PRUNED_BASE_GGUF) / 1024 / 1024
        logger.info(f"Pruned base GGUF already exists: {PRUNED_BASE_GGUF} ({size_mb/1024:.1f} GB) -- skipping")
        return PRUNED_BASE_GGUF

    if not os.path.exists(CONVERT_HF_SCRIPT):
        logger.warning(f"convert_hf_to_gguf.py not found at {CONVERT_HF_SCRIPT}")
        logger.warning(f"Falling back to non-pruned GGUF: {FALLBACK_GGUF}")
        return FALLBACK_GGUF if os.path.exists(FALLBACK_GGUF) else None

    if not os.path.exists(BASE_HF_DIR):
        logger.error(f"Pruned model directory not found: {BASE_HF_DIR}")
        return FALLBACK_GGUF if os.path.exists(FALLBACK_GGUF) else None

    # Step 1: HF -> F16 GGUF
    f16_gguf = os.path.join(BASE_HF_DIR, "Qwen3.5-35B-A3B-pruned-F16.gguf")
    if not os.path.exists(f16_gguf):
        logger.info("Step 1/2: Converting pruned model HF -> F16 GGUF (~20-30 min)...")
        cmd = [
            sys.executable, CONVERT_HF_SCRIPT,
            "--outfile", f16_gguf,
            "--outtype", "f16",
            BASE_HF_DIR,
        ]
        logger.info(f"  {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            logger.error(f"F16 conversion failed (exit {result.returncode})")
            if result.stderr:
                # Show last 1000 chars of stderr (most useful error info is at end)
                logger.error(result.stderr[-1000:])
            logger.warning(f"Falling back to non-pruned GGUF")
            return FALLBACK_GGUF if os.path.exists(FALLBACK_GGUF) else None
        size_gb = os.path.getsize(f16_gguf) / 1024 / 1024 / 1024
        logger.info(f"  F16 GGUF created: {size_gb:.1f} GB")
    else:
        size_gb = os.path.getsize(f16_gguf) / 1024 / 1024 / 1024
        logger.info(f"  F16 GGUF already exists ({size_gb:.1f} GB) -- skipping step 1")

    # Step 2: F16 -> Q4_K_M quantization
    if not os.path.exists(LLAMA_QUANTIZE):
        logger.warning(f"llama-quantize not found at {LLAMA_QUANTIZE}")
        logger.warning(f"Using F16 GGUF directly (larger but works)")
        return f16_gguf

    logger.info("Step 2/2: Quantizing F16 -> Q4_K_M (~5-10 min)...")
    cmd = [LLAMA_QUANTIZE, f16_gguf, PRUNED_BASE_GGUF, "Q4_K_M"]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.error(f"Quantization failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[-1000:])
        logger.warning(f"Using F16 GGUF as fallback")
        return f16_gguf

    if os.path.exists(PRUNED_BASE_GGUF):
        size_gb = os.path.getsize(PRUNED_BASE_GGUF) / 1024 / 1024 / 1024
        logger.info(f"Pruned Q4_K_M GGUF created: {PRUNED_BASE_GGUF} ({size_gb:.1f} GB)")
        # Clean up the large F16 intermediate
        logger.info(f"Cleaning up F16 intermediate ({os.path.getsize(f16_gguf)/1024/1024/1024:.1f} GB)...")
        os.remove(f16_gguf)
        return PRUNED_BASE_GGUF

    logger.error("Quantization produced no output file")
    return f16_gguf if os.path.exists(f16_gguf) else None


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
# Step 5: Start llama-server with v3 adapter
# ---------------------------------------------------------------------------

def start_llama_server(base_gguf_path):
    if not os.path.exists(ADAPTER_GGUF):
        logger.warning("LoRA GGUF not available -- cannot start llama-server with adapter")
        return False

    if not base_gguf_path or not os.path.exists(base_gguf_path):
        logger.error(f"Base GGUF not found: {base_gguf_path}")
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "llama_server_v3.log")

    base_size_gb = os.path.getsize(base_gguf_path) / 1024 / 1024 / 1024
    cmd = [
        LLAMA_SERVER,
        "-m", base_gguf_path,
        "--lora", ADAPTER_GGUF,
        "--port", str(LLAMA_PORT),
        "--n-gpu-layers", "999",
        # --- Optimized for MoE on 16GB VRAM ---
        "--ctx-size", "16384",          # 16K context for longer code generation
        "--threads", "2",               # MoE expert dispatch is GPU-bound
        "-b", "4096",                   # larger batch for prompt processing
        "-fa",                          # flash attention: 30-40% faster, less VRAM
        "--cache-type-k", "q8_0",       # quantized KV cache keys (~50% VRAM savings)
        "--cache-type-v", "q4_0",       # quantized KV cache values (~75% VRAM savings)
        "--no-mmap",                    # load model fully into RAM
        "--mlock",                      # pin model memory, prevent swapping
    ]
    logger.info(f"Starting llama-server v3 on port {LLAMA_PORT}...")
    logger.info(f"  Base:    {base_gguf_path} ({base_size_gb:.1f} GB)")
    logger.info(f"  Adapter: {ADAPTER_GGUF}")

    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        )

    logger.info(f"llama-server started (PID {proc.pid}), log: {log_path}")

    # Wait up to 240s for server to be ready
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

    # Ensure hiveai-v3 is in LLAMA_SERVER_MODELS list
    models_match = re.search(r"^LLAMA_SERVER_MODELS=(.*)$", content, re.MULTILINE)
    if models_match:
        current_models = models_match.group(1)
        if MODEL_NAME not in current_models:
            new_models = current_models.rstrip() + f",{MODEL_NAME}"
            content = re.sub(r"^LLAMA_SERVER_MODELS=.*$", f"LLAMA_SERVER_MODELS={new_models}", content, flags=re.MULTILINE)
    else:
        content += f"LLAMA_SERVER_MODELS=hiveai-v1,hiveai-v1.5,hiveai-v2,{MODEL_NAME}\n"

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
            (VERSION_TAG, "qwen3.5-35b-a3b-pruned", meta.get('pair_count', 0),
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
    log_path = os.path.join(LOG_DIR, "eval_v3.log")
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
    parser = argparse.ArgumentParser(description="Deploy HiveAI LoRA v3 (Qwen3.5-35B-A3B pruned)")
    parser.add_argument("--now", action="store_true", help="Skip waiting, deploy immediately")
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--skip-server", action="store_true", help="Skip llama-server start (GGUF convert only)")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI LoRA v3 -- Post-Training Deployment")
    print(f"  Base: Qwen3.5-35B-A3B (MoE, 256 experts, 3B active)")
    print(f"  LoRA: trained on pruned model (128 experts), attention-only")
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

    # 3a. Convert LoRA adapter to GGUF
    lora_ok = convert_lora_gguf()

    # 3b. Convert pruned base model to GGUF (or fall back to non-pruned)
    base_gguf_path = convert_base_gguf()
    if not base_gguf_path:
        logger.error("No base GGUF available (neither pruned nor non-pruned)")
        sys.exit(1)

    is_pruned = base_gguf_path == PRUNED_BASE_GGUF
    base_size_gb = os.path.getsize(base_gguf_path) / 1024 / 1024 / 1024
    logger.info(f"Using {'pruned' if is_pruned else 'non-pruned (fallback)'} base: {base_size_gb:.1f} GB")

    if args.skip_server:
        logger.info("--skip-server flag: skipping llama-server steps")
        print("\n" + "=" * 60)
        print("  GGUF Conversion Complete!")
        print("=" * 60)
        if lora_ok:
            size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
            print(f"\n  LoRA GGUF:  {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        print(f"  Base GGUF:  {base_gguf_path} ({base_size_gb:.1f} GB)")
        print(f"\n  To start llama-server manually:")
        print(f'    "{LLAMA_SERVER}" -m "{base_gguf_path}" --lora "{ADAPTER_GGUF}" --port {LLAMA_PORT} --n-gpu-layers 999 --ctx-size 16384 --threads 2 -b 4096 -fa --cache-type-k q8_0 --cache-type-v q4_0 --no-mmap --mlock')
        print("=" * 60)
        return

    # 4. Kill old llama-server
    stop_llama_server()

    # 5. Start new llama-server with resolved base GGUF
    server_ok = False
    if lora_ok:
        server_ok = start_llama_server(base_gguf_path)

    if not server_ok and lora_ok:
        logger.error("v3 server failed to start! NOT updating .env or DB to prevent broken state.")
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
    print("  v3 Deployment Complete!")
    print("=" * 60)
    print(f"\n  Model:    {MODEL_NAME} (Qwen3.5-35B-A3B + LoRA v3)")
    print(f"  Adapter:  {ADAPTER_DIR}")
    print(f"  Base:     {'pruned' if is_pruned else 'non-pruned'} ({base_size_gb:.1f} GB)")
    if lora_ok:
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  LoRA:     {ADAPTER_GGUF} ({size_mb:.0f} MB)")
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
    print(f'      -d \'{{"model": "{MODEL_NAME}", "messages": [{{"role": "user", "content": "Write a Python function to post to Hive"}}], "chat_template_kwargs": {{"enable_thinking": false}}}}\'')
    print("=" * 60)


if __name__ == "__main__":
    main()
