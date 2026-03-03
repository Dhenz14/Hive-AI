"""
Post-training deployment script for HiveAI LoRA v1.5.

Run this in a separate terminal once training is complete (or let it
watch the log and fire automatically):

    python scripts/deploy_v1_5.py           # watch mode: waits for training
    python scripts/deploy_v1_5.py --now     # deploy immediately (training assumed done)
    python scripts/deploy_v1_5.py --eval    # deploy + run eval

What it does:
    1. Waits for training_meta.json to appear (confirms training done)
    2. Verifies the adapter files are present
    3. Converts adapter to GGUF if not already done
    4. Stops any existing llama-server
    5. Starts llama-server with v1.5 adapter
    6. Updates .env  LLAMA_SERVER_MODEL=hiveai-v1.5
    7. Updates lora_versions DB row to 'ready'
    8. Optionally runs eval (--eval flag)
    9. Restarts the distillation supervisor
"""
import argparse
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_DIR  = os.path.join(PROJECT_ROOT, "loras", "v1.5")
META_FILE    = os.path.join(ADAPTER_DIR, "training_meta.json")
ADAPTER_GGUF = os.path.join(ADAPTER_DIR, "hiveai-v1.5-lora.gguf")
ENV_FILE     = os.path.join(PROJECT_ROOT, ".env")
DB_FILE      = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")

BASE_GGUF       = r"C:\Users\theyc\.ollama\models\blobs\sha256-a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e"
CONVERT_SCRIPT  = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
LLAMA_SERVER    = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"
LLAMA_PORT      = 11435


# ---------------------------------------------------------------------------
# Step 1: Wait for training to finish
# ---------------------------------------------------------------------------

def wait_for_training(poll_seconds=30):
    logger.info("Watching for training completion…")
    while not os.path.exists(META_FILE):
        logger.info(f"  training_meta.json not found yet, checking again in {poll_seconds}s")
        time.sleep(poll_seconds)
    logger.info(f"training_meta.json found — training complete!")
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


# ---------------------------------------------------------------------------
# Step 3: GGUF conversion
# ---------------------------------------------------------------------------

def convert_gguf():
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"GGUF already exists: {ADAPTER_GGUF} ({size_mb:.0f} MB) — skipping conversion")
        return True

    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning(f"convert_lora_to_gguf.py not found at {CONVERT_SCRIPT} — skipping GGUF")
        logger.warning("Manual: python convert_lora_to_gguf.py --base-model-id unsloth/Qwen3-14B loras/v1.5/")
        return False

    logger.info("Converting LoRA adapter to GGUF…")
    cmd = [sys.executable, CONVERT_SCRIPT, "--base-model-id", "unsloth/Qwen3-14B", ADAPTER_DIR]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error(f"GGUF conversion failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[:500])
        return False

    # Rename whatever .gguf was produced
    for fname in os.listdir(ADAPTER_DIR):
        if fname.endswith(".gguf") and fname != "hiveai-v1.5-lora.gguf":
            src = os.path.join(ADAPTER_DIR, fname)
            os.rename(src, ADAPTER_GGUF)
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
# Step 5: Start llama-server with v1.5
# ---------------------------------------------------------------------------

def start_llama_server():
    if not os.path.exists(ADAPTER_GGUF):
        logger.warning("GGUF not available — cannot start llama-server with adapter")
        logger.warning(f"Start manually:\n  {LLAMA_SERVER} -m \"{BASE_GGUF}\" --lora \"{ADAPTER_GGUF}\" --port {LLAMA_PORT} --n-gpu-layers 999 --ctx-size 8192 --threads 8")
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "llama_server_v1_5.log")

    cmd = [
        LLAMA_SERVER,
        "-m", BASE_GGUF,
        "--lora", ADAPTER_GGUF,
        "--port", str(LLAMA_PORT),
        "--n-gpu-layers", "999",
        "--ctx-size", "8192",
        "--threads", "8",
    ]
    logger.info(f"Starting llama-server v1.5 on port {LLAMA_PORT}…")
    logger.info(f"  {' '.join(cmd)}")

    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(cmd, stdout=log_f, stderr=log_f, creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0)

    logger.info(f"llama-server started (PID {proc.pid}), log: {log_path}")

    # Wait up to 30s for server to be ready
    import urllib.request
    for i in range(30):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{LLAMA_PORT}/health", timeout=2)
            logger.info(f"llama-server ready after {i+1}s")
            return True
        except Exception:
            pass
    logger.warning("llama-server didn't respond within 30s — check log")
    return False


# ---------------------------------------------------------------------------
# Step 6: Update .env
# ---------------------------------------------------------------------------

def update_env():
    with open(ENV_FILE, "r") as f:
        content = f.read()

    # Replace or insert LLAMA_SERVER_MODEL
    import re
    if "LLAMA_SERVER_MODEL=" in content:
        content = re.sub(r"^LLAMA_SERVER_MODEL=.*$", "LLAMA_SERVER_MODEL=hiveai-v1.5", content, flags=re.MULTILINE)
    else:
        content += "\nLLAMA_SERVER_MODEL=hiveai-v1.5\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)
    logger.info(".env updated: LLAMA_SERVER_MODEL=hiveai-v1.5")


# ---------------------------------------------------------------------------
# Step 7: Update DB
# ---------------------------------------------------------------------------

def update_db(meta):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        "UPDATE lora_versions SET status=?, benchmark_score=?, adapter_path=? WHERE version=? AND status='training'",
        ('ready', meta.get('loss'), ADAPTER_DIR, 'v1.5')
    )
    if cur.rowcount == 0:
        # Row might not exist; insert it
        cur.execute(
            "INSERT INTO lora_versions (version, base_model, pair_count, benchmark_score, adapter_path, status, created_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            ('v1.5', meta.get('base_model', 'unsloth/Qwen3-14B'), meta.get('pair_count', 1999),
             meta.get('loss'), ADAPTER_DIR, 'ready')
        )
    con.commit()
    con.close()
    logger.info(f"DB updated: v1.5 → ready (loss={meta.get('loss')})")


# ---------------------------------------------------------------------------
# Step 8: Run eval
# ---------------------------------------------------------------------------

def run_eval():
    eval_script = os.path.join(PROJECT_ROOT, "scripts", "run_eval.py")
    if not os.path.exists(eval_script):
        logger.warning("run_eval.py not found — skipping eval")
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "eval_v1_5.log")
    logger.info(f"Running eval for hiveai-v1.5 → {log_path}")

    cmd = [
        sys.executable, eval_script,
        "--model", "hiveai-v1.5",
        "--base-url", f"http://localhost:{LLAMA_PORT}",
    ]
    logger.info(f"  {' '.join(cmd)}")
    with open(log_path, "w") as log_f:
        result = subprocess.run(cmd, stdout=log_f, stderr=log_f, timeout=3600)

    if result.returncode == 0:
        # Try to read score from eval output
        with open(log_path) as f:
            eval_out = f.read()
        import re
        score_match = re.search(r"Overall.*?(0\.\d+)", eval_out)
        if score_match:
            score = float(score_match.group(1))
            logger.info(f"Eval complete: score={score:.3f}")
            # Update DB with benchmark score
            con = sqlite3.connect(DB_FILE)
            con.execute("UPDATE lora_versions SET benchmark_score=? WHERE version='v1.5'", (score,))
            con.commit()
            con.close()
        else:
            logger.info("Eval complete (score not parsed from output)")
    else:
        logger.warning(f"Eval exited with code {result.returncode}")


# ---------------------------------------------------------------------------
# Step 9: Restart supervisor
# ---------------------------------------------------------------------------

def restart_supervisor():
    log_path = os.path.join(LOG_DIR, "supervisor_post_v1_5.log")
    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "scripts", "distill_supervisor.py"),
        "--hours", "14",
        "--workers", "4",
    ]
    logger.info(f"Restarting supervisor → {log_path}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f, env=env,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        )
    logger.info(f"Supervisor restarted (PID {proc.pid})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deploy HiveAI LoRA v1.5")
    parser.add_argument("--now", action="store_true", help="Skip waiting, deploy immediately")
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--no-supervisor", action="store_true", help="Don't restart supervisor")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI LoRA v1.5 — Post-Training Deployment")
    print("=" * 60)

    # 1. Wait / check
    if args.now and os.path.exists(META_FILE):
        logger.info("--now flag: loading existing training_meta.json")
        with open(META_FILE) as f:
            meta = json.load(f)
        logger.info(f"  loss={meta.get('loss')}  pairs={meta.get('pair_count')}")
    else:
        meta = wait_for_training()

    # 2. Verify adapter
    verify_adapter()

    # 3. GGUF conversion
    gguf_ok = convert_gguf()

    # 4. Kill old llama-server
    stop_llama_server()

    # 5. Start new llama-server
    server_ok = False
    if gguf_ok:
        server_ok = start_llama_server()

    # 6. Update .env
    update_env()

    # 7. Update DB
    update_db(meta)

    # 8. Eval (optional)
    if args.eval and server_ok:
        run_eval()

    # 9. Restart supervisor
    if not args.no_supervisor:
        restart_supervisor()

    print("\n" + "=" * 60)
    print("  v1.5 Deployment Complete!")
    print("=" * 60)
    print(f"\n  Adapter:  {ADAPTER_DIR}")
    if gguf_ok:
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  GGUF:     {ADAPTER_GGUF} ({size_mb:.0f} MB)")
    print(f"\n  llama-server: http://localhost:{LLAMA_PORT}")
    print(f"  Active model: hiveai-v1.5")
    print(f"\n  To run eval manually:")
    print(f"    python scripts/run_eval.py --model hiveai-v1.5 --base-url http://localhost:{LLAMA_PORT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
