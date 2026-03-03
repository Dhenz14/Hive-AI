"""
Post-training deployment script for HiveAI LoRA v4 (MoE-Aware).

Run this once v4 training is complete:

    python scripts/deploy_v4.py           # watch mode: waits for training
    python scripts/deploy_v4.py --now     # deploy immediately
    python scripts/deploy_v4.py --eval    # deploy + run eval
    python scripts/deploy_v4.py --steer   # also generate SteerMoE config

What it does:
    1. Waits for training_meta.json (confirms training done)
    2. Verifies adapter files
    3. Converts adapter to GGUF via llama.cpp
    4. Stops any existing llama-server
    5. Starts llama-server with v4 adapter + Qwen3.5-35B-A3B base
    6. Updates .env LLAMA_SERVER_MODEL=hiveai-v4
    7. Updates lora_versions DB row to 'ready'
    8. Optionally generates SteerMoE gate bias config (--steer)
    9. Optionally runs eval (--eval)

v4 additions over v2:
    - SteerMoE gate bias config generation for Python inference
    - ESFT metadata in DB
    - KL anchoring stats logged
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
ADAPTER_DIR = os.path.join(PROJECT_ROOT, "loras", "v4")
META_FILE = os.path.join(ADAPTER_DIR, "training_meta.json")
ADAPTER_GGUF = os.path.join(ADAPTER_DIR, "hiveai-v4-lora.gguf")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
DB_FILE = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

BASE_GGUF = os.path.join(
    PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "Qwen3.5-35B-A3B-Q4_K_M.gguf"
)
PRUNED_MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")
CONVERT_SCRIPT = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
LLAMA_SERVER = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"
LLAMA_PORT = 11435

MODEL_NAME = "hiveai-v4"
VERSION_TAG = "v4.0"


def wait_for_training(poll_seconds=30):
    """Wait for training_meta.json to appear."""
    logger.info("Watching for training completion...")
    while not os.path.exists(META_FILE):
        logger.info(f"  training_meta.json not found, checking in {poll_seconds}s")
        time.sleep(poll_seconds)
    logger.info("training_meta.json found — training complete!")
    with open(META_FILE) as f:
        meta = json.load(f)
    logger.info(
        f"  loss={meta.get('loss')}  time={meta.get('training_time_s')}s  "
        f"pairs={meta.get('pair_count')}  esft={meta.get('esft_config', 'none')}"
    )
    kl = meta.get("kl_config", {})
    if kl.get("lambda", 0) > 0:
        logger.info(f"  KL anchoring: lambda={kl['lambda']}, temp={kl.get('temperature')}")
    return meta


def verify_adapter():
    """Check adapter files exist."""
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


def convert_gguf():
    """Convert LoRA adapter to GGUF for llama-server."""
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"GGUF exists: {ADAPTER_GGUF} ({size_mb:.0f} MB) — skipping")
        return True

    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning(f"convert_lora_to_gguf.py not found: {CONVERT_SCRIPT}")
        return False

    logger.info("Converting LoRA adapter to GGUF...")
    cmd = [
        sys.executable, CONVERT_SCRIPT,
        "--base", PRUNED_MODEL_DIR,
        "--outfile", ADAPTER_GGUF,
        "--outtype", "f16",
        ADAPTER_DIR,
    ]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error(f"GGUF conversion failed:\n{result.stderr[:1000]}")
        return False

    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"GGUF created: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        return True

    # Check for auto-named GGUF
    for fname in os.listdir(ADAPTER_DIR):
        if fname.endswith(".gguf") and fname != os.path.basename(ADAPTER_GGUF):
            src = os.path.join(ADAPTER_DIR, fname)
            os.rename(src, ADAPTER_GGUF)
            size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
            logger.info(f"Renamed {fname} -> {os.path.basename(ADAPTER_GGUF)} ({size_mb:.0f} MB)")
            return True

    logger.error("Conversion produced no .gguf file")
    return False


def stop_llama_server():
    """Kill existing llama-server process."""
    result = subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        capture_output=True, text=True,
    )
    if "SUCCESS" in (result.stdout or "").upper():
        logger.info("Stopped existing llama-server")
        time.sleep(3)
    else:
        logger.info("No existing llama-server to stop")


def start_llama_server():
    """Start llama-server with v4 adapter."""
    if not os.path.exists(ADAPTER_GGUF):
        logger.warning("GGUF not available — cannot start llama-server")
        return False

    if not os.path.exists(BASE_GGUF):
        logger.error(f"Base GGUF not found: {BASE_GGUF}")
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "llama_server_v4.log")

    cmd = [
        LLAMA_SERVER,
        "-m", BASE_GGUF,
        "--lora", ADAPTER_GGUF,
        "--port", str(LLAMA_PORT),
        "--n-gpu-layers", "999",
        "--ctx-size", "16384",
        "--threads", "2",
        "-b", "4096",
        "-fa",
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q4_0",
        "--no-mmap",
        "--mlock",
    ]

    logger.info(f"Starting llama-server v4 on port {LLAMA_PORT}...")
    logger.info(f"  Base:    {BASE_GGUF}")
    logger.info(f"  Adapter: {ADAPTER_GGUF}")

    with open(log_path, "w") as log_f:
        subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
        )

    logger.info(f"llama-server started, log: {log_path}")

    import urllib.request
    for i in range(240):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{LLAMA_PORT}/health", timeout=2)
            logger.info(f"llama-server ready after {i + 1}s")
            return True
        except Exception:
            if (i + 1) % 30 == 0:
                logger.info(f"Still waiting... ({i + 1}s)")

    logger.warning("llama-server didn't respond within 240s")
    return False


def update_env():
    """Update .env with v4 model name."""
    if not os.path.exists(ENV_FILE):
        logger.warning(f".env not found: {ENV_FILE}")
        return

    with open(ENV_FILE, "r") as f:
        content = f.read()

    if "LLAMA_SERVER_MODEL=" in content:
        content = re.sub(
            r"^LLAMA_SERVER_MODEL=.*$",
            f"LLAMA_SERVER_MODEL={MODEL_NAME}",
            content, flags=re.MULTILINE,
        )
    else:
        content += f"\nLLAMA_SERVER_MODEL={MODEL_NAME}\n"

    # Add to models list
    models_match = re.search(r"^LLAMA_SERVER_MODELS=(.*)$", content, re.MULTILINE)
    if models_match:
        current = models_match.group(1)
        if MODEL_NAME not in current:
            content = re.sub(
                r"^LLAMA_SERVER_MODELS=.*$",
                f"LLAMA_SERVER_MODELS={current.rstrip()},{MODEL_NAME}",
                content, flags=re.MULTILINE,
            )
    else:
        content += f"LLAMA_SERVER_MODELS=hiveai-v1,{MODEL_NAME}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)
    logger.info(f".env updated: LLAMA_SERVER_MODEL={MODEL_NAME}")


def update_db(meta):
    """Update lora_versions in DB."""
    if not os.path.exists(DB_FILE):
        logger.warning(f"DB not found: {DB_FILE}")
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
            (
                VERSION_TAG,
                "Qwen3.5-35B-A3B-pruned",
                meta.get("pair_count", 0),
                meta.get("loss"),
                ADAPTER_DIR,
                "ready",
            ),
        )
    con.commit()
    con.close()
    logger.info(f"DB updated: {VERSION_TAG} -> ready")


def generate_steer_config():
    """Generate SteerMoE gate bias config for Python inference."""
    steer_script = os.path.join(PROJECT_ROOT, "scripts", "steer_moe.py")
    if not os.path.exists(steer_script):
        logger.warning("steer_moe.py not found — skipping SteerMoE config")
        return None

    output = os.path.join(ADAPTER_DIR, "steer_moe_config.json")
    logger.info("Generating SteerMoE gate bias config...")

    cmd = [
        sys.executable, steer_script,
        "--model-dir", PRUNED_MODEL_DIR,
        "--output", output,
        "--boost", "0.3",
    ]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode == 0 and os.path.exists(output):
        logger.info(f"SteerMoE config saved: {output}")
        logger.info(
            "  Apply via gate hooks in Python inference for additional coding boost."
        )
        logger.info(
            "  Note: not applicable to llama-server (native GGUF inference)."
        )
        return output

    logger.warning(f"SteerMoE generation failed:\n{result.stderr[:500]}")
    return None


def run_eval():
    """Run evaluation against the deployed model."""
    eval_script = os.path.join(PROJECT_ROOT, "scripts", "run_eval.py")
    if not os.path.exists(eval_script):
        logger.warning("run_eval.py not found")
        return None

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "eval_v4.log")
    logger.info(f"Running eval for {MODEL_NAME}...")

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
            if os.path.exists(DB_FILE):
                con = sqlite3.connect(DB_FILE)
                con.execute(
                    "UPDATE lora_versions SET benchmark_score=? WHERE version=?",
                    (score, VERSION_TAG),
                )
                con.commit()
                con.close()
        else:
            logger.info("Eval complete (score not parsed)")
    else:
        logger.warning(f"Eval failed (exit {result.returncode}), log: {log_path}")

    return score


def main():
    parser = argparse.ArgumentParser(description="Deploy HiveAI LoRA v4")
    parser.add_argument("--now", action="store_true", help="Deploy immediately")
    parser.add_argument("--eval", action="store_true", help="Run eval after deploy")
    parser.add_argument("--steer", action="store_true", help="Generate SteerMoE config")
    parser.add_argument("--skip-server", action="store_true", help="GGUF only, no server")
    args = parser.parse_args()

    print("=" * 60)
    print("  HiveAI LoRA v4 — Post-Training Deployment")
    print("  MoE-Aware: ESFT + KL-Anchored SFT")
    print(f"  Adapter: {ADAPTER_DIR}")
    print("=" * 60)

    # 1. Wait / check
    if args.now and os.path.exists(META_FILE):
        logger.info("--now: loading existing meta")
        with open(META_FILE) as f:
            meta = json.load(f)
    elif os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
    else:
        meta = wait_for_training()

    # 2. Verify
    verify_adapter()

    # 3. GGUF
    gguf_ok = convert_gguf()

    # SteerMoE (can run anytime)
    steer_config = None
    if args.steer:
        steer_config = generate_steer_config()

    if args.skip_server:
        logger.info("--skip-server: done after GGUF conversion")
        return

    # 4-5. Server
    stop_llama_server()
    server_ok = start_llama_server() if gguf_ok else False

    if not server_ok and gguf_ok:
        logger.error("Server failed to start — system state NOT updated")
        sys.exit(1)

    # 6-7. Env + DB
    update_env()
    update_db(meta)

    # 8. Eval
    score = run_eval() if args.eval and server_ok else None

    # Summary
    print("\n" + "=" * 60)
    print("  v4 Deployment Complete!")
    print("=" * 60)
    print(f"\n  Model:    {MODEL_NAME} (ESFT + KL-Anchored)")
    print(f"  Adapter:  {ADAPTER_DIR}")
    if gguf_ok:
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  GGUF:     {ADAPTER_GGUF} ({size_mb:.0f} MB)")
    if steer_config:
        print(f"  SteerMoE: {steer_config}")
    if server_ok:
        print(f"\n  llama-server: http://localhost:{LLAMA_PORT}")
    if score is not None:
        print(f"  Eval score:   {score:.3f}")
    print(f"\n  Baselines:")
    print(f"    qwen3:14b (baseline):  0.741")
    print(f"    hiveai-v1 (14B LoRA):  0.853 (+15%)")
    print(f"    hiveai-v3 (35B pruned): TBD")
    print(f"\n  Run eval:")
    print(f"    python scripts/run_eval.py --model {MODEL_NAME} "
          f"--base-url http://localhost:{LLAMA_PORT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
