#!/usr/bin/env python3
"""
scripts/start_spiritbomb.py

ONE-COMMAND Spirit Bomb Launcher — handles ALL runtime dependencies.

What this script does:
  1. Auto-detects GPU (model, VRAM, UUID) via nvidia-smi
  2. Checks for Ollama — starts it if installed but not running
  3. Bootstraps API key from Hive credentials (no manual key needed)
  4. Registers GPU node with HivePoA (auto-registration)
  5. Starts Community Coordinator (tier monitoring)
  6. Starts GPU Worker with inference mode (GPU sharing)
  7. Optionally starts vLLM container for cluster inference

Usage:
    # Minimal — uses Hive credentials file:
    python scripts/start_spiritbomb.py

    # With explicit credentials:
    python scripts/start_spiritbomb.py --username dandandan123

    # With existing API key (skip bootstrap):
    python scripts/start_spiritbomb.py --api-key <existing-key>

    # Coordinator only (monitoring, no GPU contribution):
    python scripts/start_spiritbomb.py --coordinator-only

    # Include vLLM cluster container:
    python scripts/start_spiritbomb.py --cluster
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("spiritbomb")

# Defaults
DEFAULT_HIVEPOA_URL = "http://localhost:5000"
DEFAULT_HIVE_CREDENTIALS = Path.home() / ".hive-credentials" / "dandandan123.json"
OLLAMA_URL = "http://localhost:11434"


# ── GPU Detection ────────────────────────────────────────────────

def detect_gpu() -> dict:
    """Auto-detect GPU info via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,uuid,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split("\n")[0].split(",")]
            if len(parts) >= 4:
                name = parts[0].replace("NVIDIA ", "").replace("GeForce ", "")
                return {
                    "model": name,
                    "vram_gb": round(float(parts[1]) / 1024),
                    "uuid": parts[2],
                    "driver": parts[3],
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"model": "unknown", "vram_gb": 16, "uuid": "", "driver": ""}


# ── Ollama Management ────────────────────────────────────────────

def is_ollama_running() -> bool:
    """Check if Ollama API is responding."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_ollama() -> subprocess.Popen | None:
    """Start Ollama if installed but not running."""
    if is_ollama_running():
        logger.info("  Ollama: already running")
        return None

    # Try to find ollama binary
    ollama_path = "ollama"
    try:
        subprocess.run([ollama_path, "--version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        # Check common install locations
        candidates = [
            "/usr/local/bin/ollama",
            os.path.expanduser("~/ollama"),
            "C:\\Users\\{}\\AppData\\Local\\Programs\\Ollama\\ollama.exe".format(os.environ.get("USERNAME", "")),
        ]
        for c in candidates:
            if os.path.exists(c):
                ollama_path = c
                break
        else:
            logger.warning("  Ollama: NOT INSTALLED — local inference will be unavailable")
            logger.warning("  Install: https://ollama.ai")
            return None

    logger.info("  Ollama: starting...")
    proc = subprocess.Popen(
        [ollama_path, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 15s for Ollama to become ready
    for _ in range(30):
        if is_ollama_running():
            logger.info(f"  Ollama: started (PID={proc.pid})")
            return proc
        time.sleep(0.5)

    logger.warning("  Ollama: started but not responding after 15s")
    return proc


# ── API Key Bootstrap ────────────────────────────────────────────

def load_hive_credentials(path: Path) -> dict:
    """Load Hive credentials from JSON file."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def bootstrap_api_key(hivepoa_url: str, username: str, posting_key: str, gpu: dict) -> str | None:
    """Bootstrap an API key by calling the worker bootstrap endpoint."""
    payload = json.dumps({
        "username": username,
        "postingKey": posting_key,
        "gpuModel": gpu.get("model", "unknown"),
        "gpuVramGb": gpu.get("vram_gb", 16),
        "deviceUuid": gpu.get("uuid", ""),
        "label": f"spirit-bomb-{platform.node()}",
    }).encode()

    try:
        req = urllib.request.Request(
            f"{hivepoa_url}/api/auth/bootstrap-worker",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                data = json.loads(resp.read())
                if data.get("success"):
                    return data.get("apiKey")
    except Exception as e:
        logger.error(f"  Bootstrap failed: {e}")
    return None


def save_api_key(key: str):
    """Save API key to local config file."""
    config_dir = Path.home() / ".spiritbomb"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.json"

    config = {}
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)

    config["api_key"] = key
    config["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"  API key saved to {config_file}")


def load_saved_api_key() -> str:
    """Load previously saved API key."""
    config_file = Path.home() / ".spiritbomb" / "config.json"
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
            return config.get("api_key", "")
    return ""


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Spirit Bomb — One Command to Join the Community GPU Cloud",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/start_spiritbomb.py                     # Auto everything
  python scripts/start_spiritbomb.py --username myuser   # Specific Hive user
  python scripts/start_spiritbomb.py --api-key abc123    # Skip bootstrap
  python scripts/start_spiritbomb.py --coordinator-only  # No GPU contribution
  python scripts/start_spiritbomb.py --cluster           # Include vLLM container
""",
    )
    parser.add_argument("--hivepoa-url", default=os.environ.get("HIVEPOA_URL", DEFAULT_HIVEPOA_URL))
    parser.add_argument("--username", default="", help="Hive username (reads from credentials if empty)")
    parser.add_argument("--api-key", default=os.environ.get("SPIRITBOMB_API_KEY", ""),
                        help="Existing API key (auto-bootstraps if empty)")
    parser.add_argument("--credentials", default=str(DEFAULT_HIVE_CREDENTIALS),
                        help="Path to Hive credentials JSON")
    parser.add_argument("--gpu-model", default="", help="GPU model (auto-detected)")
    parser.add_argument("--gpu-vram", type=int, default=0, help="GPU VRAM GB (auto-detected)")
    parser.add_argument("--coordinator-only", action="store_true",
                        help="Only run coordinator, no GPU worker")
    parser.add_argument("--cluster", action="store_true",
                        help="Start vLLM container for cluster inference")
    parser.add_argument("--inference-allocation", type=float, default=0.3,
                        help="Fraction of GPU for inference (0.0-0.8)")
    parser.add_argument("--no-ollama", action="store_true",
                        help="Don't auto-start Ollama")
    args = parser.parse_args()

    logger.info("")
    logger.info("=" * 60)
    logger.info("  SPIRIT BOMB — Community GPU Cloud")
    logger.info("  One command. Share GPU. Pull intelligence.")
    logger.info("=" * 60)
    logger.info("")

    # ── Step 1: Detect GPU ──────────────────────────────────────
    logger.info("[1/5] Detecting GPU...")
    gpu = detect_gpu()
    if args.gpu_model:
        gpu["model"] = args.gpu_model
    if args.gpu_vram:
        gpu["vram_gb"] = args.gpu_vram
    logger.info(f"  GPU: {gpu['model']} ({gpu['vram_gb']}GB)")
    if gpu.get("uuid"):
        logger.info(f"  UUID: {gpu['uuid'][:20]}...")

    # ── Step 2: Start Ollama ────────────────────────────────────
    ollama_proc = None
    if not args.no_ollama:
        logger.info("[2/5] Checking Ollama (local inference backend)...")
        ollama_proc = start_ollama()
    else:
        logger.info("[2/5] Ollama: skipped (--no-ollama)")

    # ── Step 3: Get API key ─────────────────────────────────────
    logger.info("[3/5] Authenticating with HivePoA...")
    api_key = args.api_key or load_saved_api_key()

    if not api_key:
        # Try bootstrap from credentials file
        creds = load_hive_credentials(Path(args.credentials))
        username = args.username or creds.get("username", "")
        posting_key = creds.get("posting_key", creds.get("postingKey", ""))

        if username and posting_key:
            logger.info(f"  Bootstrapping API key for @{username}...")
            api_key = bootstrap_api_key(args.hivepoa_url, username, posting_key, gpu) or ""
            if api_key:
                save_api_key(api_key)
                logger.info(f"  API key created and saved")
            else:
                logger.warning("  Bootstrap failed — running without auth (limited)")
        else:
            logger.warning("  No credentials found — running without auth")
            logger.warning(f"  Create credentials at: {DEFAULT_HIVE_CREDENTIALS}")
    else:
        logger.info(f"  Using {'saved' if not args.api_key else 'provided'} API key")

    # ── Step 4: Start services ──────────────────────────────────
    logger.info("[4/5] Starting services...")
    processes: list[tuple[str, subprocess.Popen]] = []

    # Coordinator
    coord_cmd = [
        sys.executable, str(PROJECT_ROOT / "scripts" / "run_coordinator.py"),
        "--hivepoa-url", args.hivepoa_url,
        "--api-key", api_key,
    ]
    coord_proc = subprocess.Popen(coord_cmd, cwd=str(PROJECT_ROOT))
    processes.append(("Coordinator", coord_proc))
    logger.info(f"  Coordinator started (PID={coord_proc.pid})")

    # GPU Worker with inference
    if not args.coordinator_only:
        worker_cmd = [
            sys.executable, str(PROJECT_ROOT / "scripts" / "gpu_worker.py"),
            "--hivepoa-url", args.hivepoa_url,
            "--api-key", api_key,
            "--gpu-model", gpu["model"],
            "--gpu-vram", str(gpu["vram_gb"]),
            "--inference",
            "--inference-allocation", str(args.inference_allocation),
        ]
        worker_proc = subprocess.Popen(worker_cmd, cwd=str(PROJECT_ROOT))
        processes.append(("GPU Worker", worker_proc))
        logger.info(f"  GPU Worker started with inference mode (PID={worker_proc.pid})")

    # vLLM cluster container
    if args.cluster:
        compose_file = PROJECT_ROOT / "docker-compose.spiritbomb.yml"
        if compose_file.exists():
            vllm_cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d", "vllm"]
            try:
                subprocess.run(vllm_cmd, cwd=str(PROJECT_ROOT), timeout=120)
                logger.info("  vLLM container started")
            except Exception as e:
                logger.warning(f"  vLLM container failed: {e}")
        else:
            logger.warning("  docker-compose.spiritbomb.yml not found — skipping vLLM")

    # ── Step 5: Ready ───────────────────────────────────────────
    logger.info("")
    logger.info("[5/5] Spirit Bomb is LIVE!")
    logger.info("")
    logger.info("  What's running:")
    for name, proc in processes:
        logger.info(f"    {name}: PID {proc.pid}")
    if ollama_proc:
        logger.info(f"    Ollama: PID {ollama_proc.pid}")
    logger.info("")
    logger.info(f"  Dashboard:  {args.hivepoa_url}/community-cloud")
    logger.info(f"  Inference:  {args.hivepoa_url}/inference")
    logger.info(f"  Quick Start: {args.hivepoa_url}/quick-start")
    logger.info("")
    logger.info("  GPU Sharing: {'ACTIVE' if not args.coordinator_only else 'DISABLED (--coordinator-only)'}")
    logger.info(f"  Local AI:   {'READY' if is_ollama_running() else 'UNAVAILABLE (install Ollama)'}")
    logger.info(f"  Cluster:    {'STARTING' if args.cluster else 'OFF (use --cluster to enable)'}")
    logger.info("")
    logger.info("  Press Ctrl+C to stop everything.")
    logger.info("=" * 60)

    # Wait for shutdown
    try:
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    logger.warning(f"  {name} exited (code={ret}), restarting...")
                    # Restart crashed processes
                    idx = next(i for i, (n, _) in enumerate(processes) if n == name)
                    new_proc = subprocess.Popen(proc.args, cwd=str(PROJECT_ROOT))
                    processes[idx] = (name, new_proc)
                    logger.info(f"  {name} restarted (PID={new_proc.pid})")
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("\nShutting down Spirit Bomb...")

    # Cleanup
    for name, proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        logger.info(f"  {name} stopped")

    if ollama_proc:
        ollama_proc.terminate()
        logger.info("  Ollama stopped")

    if args.cluster:
        try:
            subprocess.run(
                ["docker", "compose", "-f", str(PROJECT_ROOT / "docker-compose.spiritbomb.yml"), "down"],
                cwd=str(PROJECT_ROOT), timeout=30,
            )
            logger.info("  vLLM container stopped")
        except Exception:
            pass

    logger.info("Spirit Bomb stopped. See you next time!")


if __name__ == "__main__":
    main()
