"""
scripts/gpu_worker.py

Entry point for the HivePoA GPU compute worker.

Registers this machine as a GPU node, polls for eval_sweep and
benchmark_run jobs, executes them using Hive-AI's eval harness,
and reports structured results back to HivePoA.

Usage:
    python scripts/gpu_worker.py \\
        --hivepoa-url http://localhost:3000 \\
        --api-key <your-agent-api-key> \\
        --gpu-model "RTX 4090" \\
        --gpu-vram 24

    # With cached models declared:
    python scripts/gpu_worker.py \\
        --hivepoa-url http://localhost:3000 \\
        --api-key <key> \\
        --gpu-model "RTX 4070 Ti SUPER" \\
        --gpu-vram 16 \\
        --cached-models "Qwen2.5-Coder-14B-Instruct,qwen3:14b"
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.dbc.compute_client import HivePoAComputeClient
from hiveai.compute.worker import GPUWorker, generate_instance_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gpu_worker")


def main():
    parser = argparse.ArgumentParser(
        description="HivePoA GPU Compute Worker — earns HBD by running AI workloads"
    )
    parser.add_argument("--hivepoa-url", type=str, required=True,
                        help="HivePoA server URL (e.g. http://localhost:3000)")
    parser.add_argument("--api-key", type=str, required=True,
                        help="Agent API key from HivePoA")
    parser.add_argument("--gpu-model", type=str, default="unknown",
                        help="GPU model name (e.g. 'RTX 4090')")
    parser.add_argument("--gpu-vram", type=int, default=16,
                        help="GPU VRAM in GB")
    parser.add_argument("--cuda-version", type=str, default=None,
                        help="CUDA version (e.g. '12.4')")
    parser.add_argument("--workloads", type=str, default="eval_sweep,benchmark_run",
                        help="Comma-separated workload types to accept")
    parser.add_argument("--cached-models", type=str, default="",
                        help="Comma-separated model IDs already cached locally")
    parser.add_argument("--poll-interval", type=int, default=30,
                        help="Seconds between job polls (default 30)")
    parser.add_argument("--max-concurrent", type=int, default=1,
                        help="Max concurrent jobs (default 1)")
    parser.add_argument("--price", type=str, default="0.50",
                        help="Price per hour in HBD (default 0.50)")
    parser.add_argument("--inference", action="store_true",
                        help="Enable Spirit Bomb inference contribution mode (shares GPU for community inference)")
    parser.add_argument("--inference-allocation", type=float, default=0.3,
                        help="Fraction of GPU time for inference (0.0-0.8, default 0.3)")

    args = parser.parse_args()

    # Generate or load stable node instance ID
    instance_id = generate_instance_id()
    logger.info(f"Node instance ID: {instance_id}")

    # Create HivePoA client
    client = HivePoAComputeClient(
        base_url=args.hivepoa_url,
        api_key=args.api_key,
    )

    # Auto-detect CUDA version if not provided
    cuda_version = args.cuda_version
    if not cuda_version:
        try:
            import torch
            if torch.cuda.is_available():
                cuda_version = torch.version.cuda
                logger.info(f"Auto-detected CUDA {cuda_version}")
        except ImportError:
            pass

    # Create and run worker
    worker = GPUWorker(
        compute_client=client,
        node_instance_id=instance_id,
        gpu_model=args.gpu_model,
        gpu_vram_gb=args.gpu_vram,
        supported_workloads=args.workloads,
        cached_models=args.cached_models,
        cuda_version=cuda_version,
        poll_interval=args.poll_interval,
    )

    logger.info(f"Starting GPU worker — HivePoA: {args.hivepoa_url}")
    logger.info(f"  GPU: {args.gpu_model} ({args.gpu_vram}GB)")
    logger.info(f"  Workloads: {args.workloads}")
    logger.info(f"  Price: {args.price} HBD/hr")

    # Start inference contribution mode in background if --inference flag
    inference_task = None
    if args.inference:
        import asyncio
        import threading
        from hiveai.compute.inference_worker import InferenceWorker

        logger.info(f"  Inference mode: ENABLED (allocation={args.inference_allocation:.0%})")

        inference_worker = InferenceWorker(
            compute_client=client,
            hivepoa_url=args.hivepoa_url,
            api_key=args.api_key,
            node_instance_id=instance_id,
            gpu_model=args.gpu_model,
            gpu_vram_gb=args.gpu_vram,
            allocation=args.inference_allocation,
        )

        def run_inference():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(inference_worker.run())
            except Exception as e:
                logger.error(f"Inference worker crashed: {e}")
            finally:
                loop.close()

        inference_thread = threading.Thread(target=run_inference, daemon=True, name="inference-worker")
        inference_thread.start()
        logger.info("  Inference worker started in background thread")

    worker.run()


if __name__ == "__main__":
    main()
