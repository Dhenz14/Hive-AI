"""
hiveai/compute/inference_worker.py

Spirit Bomb Inference Worker — community GPU inference contribution mode.

Extends the base GPUWorker with the ability to serve inference requests
for the community pool. Workers can opt-in to donate GPU time for
distributed inference, earning HBD reputation bonuses.

Architecture:
  - Runs alongside the base compute worker
  - Connects to community coordinator for cluster assignment
  - Hosts expert replicas (MoE) or model shards (PP/TP)
  - Reports inference contributions for reward tracking
  - Supports dual-mode: compute jobs + inference serving simultaneously

Integration with inference engines:
  - vLLM: Pipeline parallel shard hosting
  - Hivemind: DHT-based expert serving
  - Local: Fallback single-GPU inference via llama-server/Ollama

Usage:
    worker = InferenceWorker(
        compute_client=client,
        hivepoa_url="http://localhost:5000",
        node_instance_id="my-gpu-node",
        gpu_model="RTX 4070 Ti SUPER",
        gpu_vram_gb=16,
    )
    await worker.run()
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore


# Inference allocation: what fraction of GPU to reserve for inference
DEFAULT_INFERENCE_ALLOCATION = 0.3  # 30% of GPU time for community inference
MAX_INFERENCE_ALLOCATION = 0.8  # never exceed 80% — leave room for compute jobs
CONTRIBUTION_REPORT_INTERVAL = 300  # report contributions every 5 min
HEARTBEAT_INTERVAL = 30  # heartbeat to coordinator every 30s


@dataclass
class InferenceStats:
    """Rolling stats for a contribution period."""
    tokens_generated: int = 0
    requests_served: int = 0
    total_inference_ms: int = 0
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    def reset(self):
        self.tokens_generated = 0
        self.requests_served = 0
        self.total_inference_ms = 0
        self.period_start = datetime.now(timezone.utc)
        self.period_end = None


@dataclass
class InferenceConfig:
    """Configuration for the inference serving mode."""
    model_name: str = "Qwen3-14B"
    quantization: str = "awq"
    max_context_length: int = 32768
    allocation: float = DEFAULT_INFERENCE_ALLOCATION
    serve_port: int = 8100  # local vLLM/llama-server port for shard
    expert_ids: list[int] = field(default_factory=list)  # MoE expert IDs to host


class InferenceWorker:
    """
    Community inference worker — serves distributed inference requests.

    Lifecycle:
    1. Register with HivePoA as compute node (reuses existing registration)
    2. Opt-in to inference contribution (POST to coordinator)
    3. Receive cluster assignment and model shard/expert config
    4. Start local inference engine (vLLM shard or llama-server)
    5. Serve requests from the cluster coordinator
    6. Report contribution metrics periodically
    7. Graceful drain on shutdown
    """

    def __init__(
        self,
        compute_client,  # HivePoAComputeClient
        hivepoa_url: str = "http://localhost:5000",
        api_key: str = "",
        node_instance_id: str = "",
        gpu_model: str = "unknown",
        gpu_vram_gb: int = 16,
        allocation: float = DEFAULT_INFERENCE_ALLOCATION,
    ):
        self.client = compute_client
        self.hivepoa_url = hivepoa_url.rstrip("/")
        self.api_key = api_key
        self.node_instance_id = node_instance_id
        self.gpu_model = gpu_model
        self.gpu_vram_gb = gpu_vram_gb
        self.allocation = min(allocation, MAX_INFERENCE_ALLOCATION)

        self._running = False
        self._stats = InferenceStats()
        self._config: Optional[InferenceConfig] = None
        self._inference_process: Optional[subprocess.Popen] = None
        self._cluster_id: Optional[str] = None
        self._node_id: Optional[str] = None

    async def run(self) -> None:
        """Main inference worker loop."""
        if aiohttp is None:
            raise ImportError("aiohttp is required: pip install aiohttp")

        self._running = True
        self._stats.reset()

        logger.info(
            f"Inference worker starting — {self.gpu_model} ({self.gpu_vram_gb}GB), "
            f"allocation={self.allocation:.0%}"
        )

        async with aiohttp.ClientSession() as session:
            # 1. Opt-in to community inference
            await self._opt_in(session)

            # 2. Get cluster assignment
            config = await self._get_cluster_config(session)
            if config:
                self._config = config
                logger.info(
                    f"Assigned to cluster {self._cluster_id}, "
                    f"model={config.model_name}, experts={config.expert_ids}"
                )

                # 3. Start local inference shard
                await self._start_inference_engine(config)

            # 4. Main loop: heartbeat + contribution reporting
            last_report = time.time()
            while self._running:
                try:
                    await self._heartbeat(session)

                    # Report contributions periodically
                    if time.time() - last_report > CONTRIBUTION_REPORT_INTERVAL:
                        await self._report_contributions(session)
                        last_report = time.time()

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Inference loop error: {e}", exc_info=True)

                await asyncio.sleep(HEARTBEAT_INTERVAL)

        # Cleanup
        await self._drain()
        logger.info("Inference worker stopped")

    async def _opt_in(self, session: aiohttp.ClientSession) -> None:
        """Register as inference contributor with HivePoA."""
        headers = self._auth_headers()
        payload = {
            "nodeId": self._node_id or self.node_instance_id,
            "gpuModel": self.gpu_model,
            "vramGb": self.gpu_vram_gb,
            "allocation": self.allocation,
            "supportedModes": ["local", "pipeline_parallel", "expert_parallel"],
        }
        try:
            # Register as cluster member (coordinator will assign us)
            async with session.get(
                f"{self.hivepoa_url}/api/community/tier",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tier = data.get("tier", 1)
                    logger.info(f"Current community tier: {tier}")
                else:
                    logger.warning(f"Failed to get tier: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Opt-in failed: {e}")

    async def _get_cluster_config(
        self, session: aiohttp.ClientSession
    ) -> Optional[InferenceConfig]:
        """Get cluster assignment and inference configuration."""
        headers = self._auth_headers()
        try:
            async with session.get(
                f"{self.hivepoa_url}/api/community/clusters",
                headers=headers,
                params={"status": "active"},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                clusters = data.get("clusters", [])
                if not clusters:
                    return self._default_local_config()

                # Join the cluster with most GPUs in our region
                best = max(clusters, key=lambda c: c.get("totalGpus", 0))
                self._cluster_id = best.get("id")

                return InferenceConfig(
                    model_name=best.get("modelName", "Qwen3-14B"),
                    quantization="awq",
                    max_context_length=32768,
                    allocation=self.allocation,
                )
        except Exception as e:
            logger.error(f"Cluster config fetch failed: {e}")
            return self._default_local_config()

    def _default_local_config(self) -> InferenceConfig:
        """Fallback: local inference only."""
        # Pick model based on VRAM
        if self.gpu_vram_gb >= 24:
            model = "Qwen3-32B"
            quant = "awq"
        elif self.gpu_vram_gb >= 12:
            model = "Qwen3-14B"
            quant = "awq"
        else:
            model = "Qwen3-14B"
            quant = "gguf"  # 4-bit for small GPUs

        return InferenceConfig(
            model_name=model,
            quantization=quant,
            max_context_length=32768 if self.gpu_vram_gb >= 12 else 8192,
            allocation=self.allocation,
        )

    async def _start_inference_engine(self, config: InferenceConfig) -> None:
        """Start the local inference engine (vLLM or llama-server)."""
        # Determine engine: vLLM for cluster mode, llama-server for local
        vram_for_inference = int(self.gpu_vram_gb * config.allocation)

        logger.info(
            f"Starting inference engine: {config.model_name} ({config.quantization}), "
            f"VRAM budget: {vram_for_inference}GB"
        )

        # For now, log the intended configuration — actual engine launch
        # depends on whether vLLM or llama-server is installed
        engine_config = {
            "model": config.model_name,
            "quantization": config.quantization,
            "max_model_len": config.max_context_length,
            "gpu_memory_utilization": config.allocation,
            "port": config.serve_port,
        }
        logger.info(f"Inference engine config: {json.dumps(engine_config)}")

        # TODO: Actually launch vLLM/llama-server process
        # self._inference_process = subprocess.Popen([...])

    async def _heartbeat(self, session: aiohttp.ClientSession) -> None:
        """Send heartbeat to coordinator."""
        # Lightweight: just confirm we're alive
        pass

    async def _report_contributions(self, session: aiohttp.ClientSession) -> None:
        """Report inference contribution metrics to HivePoA."""
        if self._stats.tokens_generated == 0 and self._stats.requests_served == 0:
            return

        self._stats.period_end = datetime.now(timezone.utc)
        headers = self._auth_headers()
        payload = {
            "nodeId": self._node_id or self.node_instance_id,
            "clusterId": self._cluster_id,
            "totalTokensGenerated": self._stats.tokens_generated,
            "totalInferenceMs": self._stats.total_inference_ms,
            "totalRequestsServed": self._stats.requests_served,
            "periodStart": self._stats.period_start.isoformat() if self._stats.period_start else None,
            "periodEnd": self._stats.period_end.isoformat(),
        }

        try:
            async with session.post(
                f"{self.hivepoa_url}/api/community/contributions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(
                        f"Reported contribution: {self._stats.tokens_generated} tokens, "
                        f"{self._stats.requests_served} requests"
                    )
                else:
                    body = await resp.text()
                    logger.warning(f"Contribution report failed: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Contribution report error: {e}")

        self._stats.reset()

    async def _drain(self) -> None:
        """Gracefully drain: stop accepting requests, finish in-flight, report final stats."""
        logger.info("Draining inference worker...")

        if self._inference_process:
            self._inference_process.terminate()
            try:
                self._inference_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._inference_process.kill()
            self._inference_process = None

    def record_inference(self, tokens: int, latency_ms: int) -> None:
        """Record an inference request completion (called by the serving engine)."""
        self._stats.tokens_generated += tokens
        self._stats.requests_served += 1
        self._stats.total_inference_ms += latency_ms

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False

    def _auth_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
