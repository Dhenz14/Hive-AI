#!/usr/bin/env python3
"""
scripts/start_spiritbomb.py

ONE-COMMAND Spirit Bomb Launcher — starts everything needed for
GPU sharing and community inference.

Starts:
  1. Community Coordinator (tier monitoring, manifest publishing)
  2. GPU Worker with --inference flag (compute jobs + inference serving)
  3. Verifies Ollama is running (local inference backend)

Usage:
    # Minimal (uses defaults):
    python scripts/start_spiritbomb.py --api-key <key>

    # Full:
    python scripts/start_spiritbomb.py \\
        --hivepoa-url http://localhost:5000 \\
        --api-key <key> \\
        --gpu-model "RTX 4070 Ti SUPER" \\
        --gpu-vram 16

    # Coordinator only (no GPU worker):
    python scripts/start_spiritbomb.py --api-key <key> --coordinator-only
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("spiritbomb")


def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def detect_gpu() -> tuple[str, int]:
    """Auto-detect GPU model and VRAM."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 2:
                name = parts[0].replace("NVIDIA ", "").replace("GeForce ", "")
                vram = round(float(parts[1]) / 1024)
                return name, vram
    except Exception:
        pass
    return "unknown", 16


async def main():
    parser = argparse.ArgumentParser(
        description="Spirit Bomb Launcher — one command to start GPU sharing + inference"
    )
    parser.add_argument("--hivepoa-url", default=os.environ.get("HIVEPOA_URL", "http://localhost:5000"))
    parser.add_argument("--api-key", default=os.environ.get("SPIRITBOMB_API_KEY", ""),
                        help="HivePoA API key (also reads SPIRITBOMB_API_KEY env)")
    parser.add_argument("--gpu-model", default="", help="GPU model (auto-detected if empty)")
    parser.add_argument("--gpu-vram", type=int, default=0, help="GPU VRAM in GB (auto-detected if 0)")
    parser.add_argument("--coordinator-only", action="store_true",
                        help="Only run coordinator, no GPU worker")
    parser.add_argument("--inference-allocation", type=float, default=0.3,
                        help="Fraction of GPU for inference (0.0-0.8)")
    args = parser.parse_args()

    # Auto-detect GPU
    if not args.gpu_model or not args.gpu_vram:
        detected_model, detected_vram = detect_gpu()
        if not args.gpu_model:
            args.gpu_model = detected_model
        if not args.gpu_vram:
            args.gpu_vram = detected_vram

    logger.info("=" * 60)
    logger.info("  SPIRIT BOMB — Community GPU Cloud Launcher")
    logger.info("=" * 60)
    logger.info(f"  HivePoA:  {args.hivepoa_url}")
    logger.info(f"  GPU:      {args.gpu_model} ({args.gpu_vram}GB)")
    logger.info(f"  Auth:     {'ApiKey configured' if args.api_key else 'NO API KEY (limited functionality)'}")

    # Check Ollama
    ollama_ok = check_ollama()
    logger.info(f"  Ollama:   {'RUNNING' if ollama_ok else 'NOT RUNNING (start with: ollama serve)'}")

    if not ollama_ok:
        logger.warning("Local inference requires Ollama. Install: https://ollama.ai")

    logger.info("=" * 60)

    processes = []
    try:
        # 1. Start coordinator
        logger.info("Starting Community Coordinator...")
        coord_cmd = [
            sys.executable, str(PROJECT_ROOT / "scripts" / "run_coordinator.py"),
            "--hivepoa-url", args.hivepoa_url,
            "--api-key", args.api_key,
            "--poll-interval", "900",
        ]
        coord_proc = subprocess.Popen(coord_cmd, cwd=str(PROJECT_ROOT))
        processes.append(("Coordinator", coord_proc))
        logger.info(f"  Coordinator started (PID={coord_proc.pid})")

        # 2. Start GPU worker with inference
        if not args.coordinator_only:
            logger.info("Starting GPU Worker (+ inference mode)...")
            worker_cmd = [
                sys.executable, str(PROJECT_ROOT / "scripts" / "gpu_worker.py"),
                "--hivepoa-url", args.hivepoa_url,
                "--api-key", args.api_key,
                "--gpu-model", args.gpu_model,
                "--gpu-vram", str(args.gpu_vram),
                "--inference",
                "--inference-allocation", str(args.inference_allocation),
            ]
            worker_proc = subprocess.Popen(worker_cmd, cwd=str(PROJECT_ROOT))
            processes.append(("GPU Worker", worker_proc))
            logger.info(f"  GPU Worker started (PID={worker_proc.pid})")

        logger.info("")
        logger.info("Spirit Bomb is LIVE. Press Ctrl+C to stop.")
        logger.info(f"  Dashboard: {args.hivepoa_url}/community-cloud")
        logger.info(f"  Inference: {args.hivepoa_url}/inference")
        logger.info("")

        # Wait for processes
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    logger.warning(f"{name} exited with code {ret}")
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("\nShutting down Spirit Bomb...")
    finally:
        for name, proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=10)
                logger.info(f"  {name} stopped")
            except Exception:
                proc.kill()
                logger.info(f"  {name} killed")

    logger.info("Spirit Bomb stopped.")


if __name__ == "__main__":
    asyncio.run(main())
