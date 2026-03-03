"""
Rollback to a previous LoRA version if a deployment regresses.

Usage:
    python scripts/rollback_lora.py              # rollback to previous version (auto-detect)
    python scripts/rollback_lora.py --to v2.0    # rollback to specific version
    python scripts/rollback_lora.py --list       # list all known versions

What it does:
    1. Reads current LLAMA_SERVER_MODEL from .env
    2. Finds the target version's adapter and base model
    3. Stops current llama-server
    4. Starts llama-server with the rollback version
    5. Updates .env to point to the rolled-back version
    6. Verifies the server responds

This is the safety net for deploy_v3.py (and future deploys).
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
DB_FILE = os.path.join(PROJECT_ROOT, "hiveai.db")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LLAMA_SERVER = r"C:\Users\theyc\llama.cpp\bin\llama-server.exe"
LLAMA_PORT = 11435

# Known version configurations
# Each maps version_tag -> (base_gguf, lora_gguf, model_name)
VERSION_REGISTRY = {
    "v1.0": {
        "model_name": "hiveai-v1",
        "base_gguf": r"C:\Users\theyc\.ollama\models\blobs\sha256-a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e",
        "lora_gguf": os.path.join(PROJECT_ROOT, "loras", "v1", "hiveai-v1-lora.gguf"),
        "extra_flags": ["--ctx-size", "8192", "--threads", "8"],
    },
    "v2.0": {
        "model_name": "hiveai-v2",
        "base_gguf": os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "Qwen3.5-35B-A3B-Q4_K_M.gguf"),
        "lora_gguf": os.path.join(PROJECT_ROOT, "loras", "v2", "hiveai-v2-lora.gguf"),
        "extra_flags": [
            "--ctx-size", "16384", "--threads", "2", "-b", "4096", "-fa",
            "--cache-type-k", "q8_0", "--cache-type-v", "q4_0", "--no-mmap", "--mlock",
        ],
    },
    "v3.0": {
        "model_name": "hiveai-v3",
        "base_gguf": os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned", "Qwen3.5-35B-A3B-pruned-Q4_K_M.gguf"),
        "lora_gguf": os.path.join(PROJECT_ROOT, "loras", "v3", "hiveai-v3-lora.gguf"),
        "extra_flags": [
            "--ctx-size", "16384", "--threads", "2", "-b", "4096", "-fa",
            "--cache-type-k", "q8_0", "--cache-type-v", "q4_0", "--no-mmap", "--mlock",
        ],
    },
}


def get_current_version() -> str | None:
    """Read current LLAMA_SERVER_MODEL from .env."""
    if not os.path.exists(ENV_FILE):
        return None
    with open(ENV_FILE) as f:
        for line in f:
            if line.strip().startswith("LLAMA_SERVER_MODEL="):
                return line.strip().split("=", 1)[1].strip()
    return None


def find_version_for_model(model_name: str) -> str | None:
    """Find version tag for a given model name."""
    for version, info in VERSION_REGISTRY.items():
        if info["model_name"] == model_name:
            return version
    return None


def get_previous_version(current_version: str) -> str | None:
    """Get the version immediately before the current one."""
    versions = sorted(VERSION_REGISTRY.keys())
    try:
        idx = versions.index(current_version)
        if idx > 0:
            return versions[idx - 1]
    except ValueError:
        pass
    return None


def list_versions():
    """Print all known versions with their status."""
    current_model = get_current_version()
    current_version = find_version_for_model(current_model) if current_model else None

    # Try to get DB scores
    db_scores = {}
    if os.path.exists(DB_FILE):
        try:
            con = sqlite3.connect(DB_FILE)
            for row in con.execute("SELECT version, benchmark_score, status FROM lora_versions"):
                db_scores[row[0]] = {"score": row[1], "status": row[2]}
            con.close()
        except Exception:
            pass

    print("\n  Known LoRA Versions:")
    print("  " + "-" * 70)
    for version in sorted(VERSION_REGISTRY.keys()):
        info = VERSION_REGISTRY[version]
        active = " <<< ACTIVE" if version == current_version else ""
        base_exists = os.path.exists(info["base_gguf"]) if info["base_gguf"] else False
        lora_exists = os.path.exists(info["lora_gguf"]) if info["lora_gguf"] else False
        files_ok = "OK" if (base_exists and lora_exists) else "MISSING"

        db_info = db_scores.get(version, {})
        score = f"score={db_info['score']:.3f}" if db_info.get("score") else "no score"
        status = db_info.get("status", "unknown")

        print(f"  {version:6s}  {info['model_name']:12s}  files={files_ok:7s}  {score:12s}  status={status}{active}")
    print()


def stop_llama_server():
    """Kill any running llama-server."""
    result = subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        capture_output=True, text=True
    )
    if "SUCCESS" in result.stdout.upper():
        logger.info("Stopped existing llama-server")
        time.sleep(3)
    else:
        logger.info("No existing llama-server running")


def start_llama_server(version: str) -> bool:
    """Start llama-server with the specified version."""
    info = VERSION_REGISTRY[version]

    if not os.path.exists(info["base_gguf"]):
        logger.error(f"Base GGUF not found: {info['base_gguf']}")
        return False
    if not os.path.exists(info["lora_gguf"]):
        logger.error(f"LoRA GGUF not found: {info['lora_gguf']}")
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"llama_server_rollback_{version}.log")

    cmd = [
        LLAMA_SERVER,
        "-m", info["base_gguf"],
        "--lora", info["lora_gguf"],
        "--port", str(LLAMA_PORT),
        "--n-gpu-layers", "999",
    ] + info.get("extra_flags", [])

    logger.info(f"Starting llama-server {version} ({info['model_name']}) on port {LLAMA_PORT}...")
    with open(log_path, "w") as log_f:
        subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f,
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        )

    # Wait for server health
    import urllib.request
    for i in range(180):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://localhost:{LLAMA_PORT}/health", timeout=2)
            logger.info(f"llama-server ready after {i+1}s")
            return True
        except Exception:
            if (i + 1) % 30 == 0:
                logger.info(f"Still waiting... ({i+1}s)")

    logger.error("llama-server didn't respond within 180s")
    return False


def update_env(model_name: str):
    """Update .env to point to the rollback model."""
    if not os.path.exists(ENV_FILE):
        logger.warning(f".env not found at {ENV_FILE}")
        return

    with open(ENV_FILE) as f:
        content = f.read()

    if "LLAMA_SERVER_MODEL=" in content:
        content = re.sub(
            r"^LLAMA_SERVER_MODEL=.*$",
            f"LLAMA_SERVER_MODEL={model_name}",
            content, flags=re.MULTILINE
        )
    else:
        content += f"\nLLAMA_SERVER_MODEL={model_name}\n"

    with open(ENV_FILE, "w") as f:
        f.write(content)
    logger.info(f".env updated: LLAMA_SERVER_MODEL={model_name}")


def main():
    parser = argparse.ArgumentParser(description="Rollback to a previous LoRA version")
    parser.add_argument("--to", type=str, help="Target version to rollback to (e.g., v2.0)")
    parser.add_argument("--list", action="store_true", help="List all known versions")
    args = parser.parse_args()

    if args.list:
        list_versions()
        return

    # Determine current and target versions
    current_model = get_current_version()
    current_version = find_version_for_model(current_model) if current_model else None

    if args.to:
        target_version = args.to
    elif current_version:
        target_version = get_previous_version(current_version)
        if not target_version:
            logger.error(f"Current version {current_version} is already the oldest known version")
            sys.exit(1)
    else:
        logger.error("Cannot determine current version. Use --to to specify target.")
        sys.exit(1)

    if target_version not in VERSION_REGISTRY:
        logger.error(f"Unknown version '{target_version}'. Known: {list(VERSION_REGISTRY.keys())}")
        sys.exit(1)

    target_info = VERSION_REGISTRY[target_version]
    logger.info(f"Rolling back: {current_model or 'unknown'} -> {target_info['model_name']} ({target_version})")

    # Verify files exist before touching anything
    if not os.path.exists(target_info["base_gguf"]):
        logger.error(f"Base GGUF missing: {target_info['base_gguf']}")
        sys.exit(1)
    if not os.path.exists(target_info["lora_gguf"]):
        logger.error(f"LoRA GGUF missing: {target_info['lora_gguf']}")
        sys.exit(1)

    # Execute rollback
    stop_llama_server()

    if not start_llama_server(target_version):
        logger.error("Rollback FAILED — llama-server didn't start")
        logger.error("Manual intervention required")
        sys.exit(1)

    update_env(target_info["model_name"])

    logger.info(f"Rollback complete: now running {target_info['model_name']} ({target_version})")
    logger.info(f"To verify: curl http://localhost:{LLAMA_PORT}/health")


if __name__ == "__main__":
    main()
