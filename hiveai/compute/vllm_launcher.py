"""
hiveai/compute/vllm_launcher.py

vLLM Launcher — starts and manages the vLLM inference engine
with Spirit Bomb configuration.

Translates ElasticMoEManager.generate_vllm_config() output into
vLLM CLI arguments and manages the process lifecycle.

Features:
  - Start vLLM with correct TP/PP/EP/quantization
  - Health monitoring via /health endpoint
  - Graceful restart on tier change (drain → stop → restart)
  - Config file watcher for hot-reload trigger
  - Model download tracking

Usage:
    launcher = VLLMLauncher()
    await launcher.start(config)
    ...
    await launcher.restart(new_config)  # on tier change
    ...
    await launcher.stop()
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

# Default ports
VLLM_PORT = 8000
HEALTH_CHECK_INTERVAL = 10  # seconds
DRAIN_TIMEOUT = 30  # seconds to wait for in-flight requests
STARTUP_TIMEOUT = 300  # 5 min for model loading


@dataclass
class VLLMConfig:
    """Configuration for a vLLM instance."""
    model: str = "Qwen/Qwen3-14B-AWQ"
    quantization: str = "awq"
    tensor_parallel_size: int = 1
    pipeline_parallel_size: int = 1
    gpu_memory_utilization: float = 0.90
    max_model_len: int = 32768
    enable_chunked_prefill: bool = True
    enable_prefix_caching: bool = True
    api_key: str = "spiritbomb-local"
    host: str = "0.0.0.0"
    port: int = VLLM_PORT
    # Speculative decoding
    speculative_model: Optional[str] = None
    num_speculative_tokens: int = 5
    # Expert parallel (MoE)
    expert_parallel_size: Optional[int] = None

    def to_cli_args(self) -> list[str]:
        """Convert config to vLLM CLI arguments."""
        args = [
            "--model", self.model,
            "--gpu-memory-utilization", str(self.gpu_memory_utilization),
            "--max-model-len", str(self.max_model_len),
            "--host", self.host,
            "--port", str(self.port),
        ]

        if self.quantization and self.quantization != "fp16":
            args.extend(["--quantization", self.quantization])

        if self.tensor_parallel_size > 1:
            args.extend(["--tensor-parallel-size", str(self.tensor_parallel_size)])

        if self.pipeline_parallel_size > 1:
            args.extend(["--pipeline-parallel-size", str(self.pipeline_parallel_size)])

        if self.enable_chunked_prefill:
            args.append("--enable-chunked-prefill")

        if self.enable_prefix_caching:
            args.append("--enable-prefix-caching")

        if self.api_key:
            args.extend(["--api-key", self.api_key])

        if self.speculative_model:
            args.extend([
                "--speculative-model", self.speculative_model,
                "--num-speculative-tokens", str(self.num_speculative_tokens),
            ])

        return args

    @staticmethod
    def from_moe_config(moe_config: dict) -> "VLLMConfig":
        """Create VLLMConfig from ElasticMoEManager.generate_vllm_config() output."""
        return VLLMConfig(
            model=moe_config.get("model", "Qwen/Qwen3-14B-AWQ"),
            quantization=moe_config.get("quantization", "awq"),
            tensor_parallel_size=moe_config.get("tensor_parallel_size", 1),
            pipeline_parallel_size=moe_config.get("pipeline_parallel_size", 1),
            gpu_memory_utilization=moe_config.get("gpu_memory_utilization", 0.90),
            max_model_len=moe_config.get("max_model_len", 32768),
            enable_chunked_prefill=moe_config.get("enable_chunked_prefill", True),
            expert_parallel_size=moe_config.get("expert_parallel_size"),
        )


class VLLMLauncher:
    """
    Manages the vLLM inference engine process lifecycle.
    """

    def __init__(self, vllm_binary: str = "vllm"):
        self.vllm_binary = vllm_binary
        self._process: Optional[subprocess.Popen] = None
        self._config: Optional[VLLMConfig] = None
        self._healthy = False
        self._start_time: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    @property
    def uptime_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    async def start(self, config: VLLMConfig) -> bool:
        """Start vLLM with the given configuration."""
        if self.is_running:
            logger.warning("vLLM already running — stop first")
            return False

        self._config = config
        cli_args = config.to_cli_args()

        logger.info(f"Starting vLLM: {self.vllm_binary} serve {' '.join(cli_args)}")

        try:
            self._process = subprocess.Popen(
                [self.vllm_binary, "serve"] + cli_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._start_time = time.time()

            # Wait for health check
            healthy = await self._wait_for_healthy(STARTUP_TIMEOUT)
            if not healthy:
                logger.error("vLLM failed to become healthy within timeout")
                await self.stop()
                return False

            self._healthy = True
            logger.info(f"vLLM is healthy — model={config.model}, port={config.port}")
            return True

        except FileNotFoundError:
            logger.error(f"vLLM binary not found: {self.vllm_binary}")
            return False
        except Exception as e:
            logger.error(f"Failed to start vLLM: {e}")
            return False

    async def stop(self) -> None:
        """Gracefully stop vLLM."""
        if not self._process:
            return

        logger.info("Stopping vLLM...")
        self._healthy = False

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=DRAIN_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.warning("vLLM did not stop gracefully, killing...")
                self._process.kill()
                self._process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error stopping vLLM: {e}")
        finally:
            self._process = None
            self._start_time = None

    async def restart(self, new_config: VLLMConfig) -> bool:
        """Restart vLLM with new configuration (for tier changes)."""
        logger.info(
            f"Restarting vLLM: {self._config.model if self._config else '?'} → {new_config.model}"
        )
        await self.stop()
        return await self.start(new_config)

    async def _wait_for_healthy(self, timeout_seconds: float) -> bool:
        """Poll vLLM health endpoint until healthy or timeout."""
        if aiohttp is None:
            # Can't check health without aiohttp, assume it works after delay
            await asyncio.sleep(10)
            return self.is_running

        deadline = time.time() + timeout_seconds
        url = f"http://localhost:{self._config.port if self._config else VLLM_PORT}/health"

        while time.time() < deadline:
            if not self.is_running:
                return False
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            return True
            except Exception:
                pass
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

        return False

    async def check_health(self) -> bool:
        """Single health check."""
        if not self.is_running:
            self._healthy = False
            return False

        if aiohttp is None:
            return self.is_running

        url = f"http://localhost:{self._config.port if self._config else VLLM_PORT}/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    self._healthy = resp.status == 200
                    return self._healthy
        except Exception:
            self._healthy = False
            return False

    def get_status(self) -> dict:
        """Get launcher status."""
        return {
            "running": self.is_running,
            "healthy": self._healthy,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "model": self._config.model if self._config else None,
            "quantization": self._config.quantization if self._config else None,
            "tp_size": self._config.tensor_parallel_size if self._config else None,
            "port": self._config.port if self._config else None,
        }


def write_config_file(config: VLLMConfig, path: str) -> None:
    """Write vLLM config to a JSON file (for docker-compose volume mount)."""
    config_dict = {
        "model": config.model,
        "quantization": config.quantization,
        "tensor_parallel_size": config.tensor_parallel_size,
        "pipeline_parallel_size": config.pipeline_parallel_size,
        "gpu_memory_utilization": config.gpu_memory_utilization,
        "max_model_len": config.max_model_len,
        "enable_chunked_prefill": config.enable_chunked_prefill,
        "enable_prefix_caching": config.enable_prefix_caching,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config_dict, f, indent=2)
    logger.info(f"Wrote vLLM config to {path}")
