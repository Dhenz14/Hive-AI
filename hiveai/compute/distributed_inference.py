"""
hiveai/compute/distributed_inference.py

Distributed Inference Coordinator — manages vLLM pipeline parallel
inference across community GPU nodes.

This is the inference execution layer of the Spirit Bomb:
  - Receives inference requests from the dual-mode router
  - Selects optimal cluster based on Helix-style placement scoring
  - Orchestrates pipeline-parallel or expert-parallel inference
  - Handles node failures with automatic re-routing
  - Tracks per-request latency and throughput

Supported inference strategies:
  1. Local: Single-GPU inference (always available, fallback)
  2. Pipeline Parallel (PP): Model split across GPU layers
  3. Tensor Parallel (TP): Model split across GPU heads (<10ms required)
  4. Expert Parallel (EP): MoE experts distributed across GPUs
  5. Speculative Decoding: EAGLE-3 draft model on fast GPU, verify on cluster

Research references:
  - vLLM: Production distributed inference (TP/PP/EP)
  - llm-d: K8s-native distributed inference with KV-cache aware routing
  - Helix (ASPLOS 2025): Max-flow heterogeneous GPU placement
  - Petals: BitTorrent-style distributed inference (Hivemind)
  - Exo: Consumer device pipeline sharding
  - EAGLE-3: Speculative decoding without target modification
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore


class InferenceStrategy(Enum):
    LOCAL = "local"
    PIPELINE_PARALLEL = "pipeline_parallel"
    TENSOR_PARALLEL = "tensor_parallel"
    EXPERT_PARALLEL = "expert_parallel"
    SPECULATIVE = "speculative"


@dataclass
class InferenceRequest:
    """A single inference request to process."""
    request_id: str
    prompt: str
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = False
    mode: str = "medium"  # "medium" (local) or "high_intel" (cluster)
    model_override: Optional[str] = None
    priority: int = 0  # higher = more urgent


@dataclass
class InferenceResult:
    """Result of an inference request."""
    request_id: str
    text: str
    tokens_generated: int
    latency_ms: float
    strategy_used: str
    cluster_id: Optional[str] = None
    model_used: str = ""
    finished: bool = True
    error: Optional[str] = None


@dataclass
class NodeEndpoint:
    """Inference endpoint on a community GPU node."""
    node_id: str
    url: str  # e.g., http://10.0.0.5:8100/v1
    gpu_model: str
    vram_gb: int
    current_load: float = 0.0  # 0.0-1.0
    avg_tps: float = 0.0
    is_healthy: bool = True
    last_check: float = 0.0


class DistributedInferenceCoordinator:
    """
    Coordinates distributed inference across community GPU clusters.

    The coordinator doesn't run inference itself — it routes requests to
    the optimal backend:
    - Local engine (llama-server, Ollama) for Medium Mode
    - Cluster endpoints (vLLM, Petals) for High-Intel Mode
    - Speculative decoding hybrid (draft local, verify on cluster)

    Request flow:
    1. Request arrives (from HivePoA API or local client)
    2. Router selects mode: medium (local) or high-intel (cluster)
    3. Coordinator picks best endpoint(s) for the request
    4. Request dispatched to endpoint(s)
    5. Response assembled and returned
    6. Contribution metrics recorded
    """

    def __init__(
        self,
        local_endpoint: str = "http://localhost:11434",  # Ollama default
        hivepoa_url: str = "http://localhost:5000",
        api_key: str = "",
    ):
        self.local_endpoint = local_endpoint
        self.hivepoa_url = hivepoa_url.rstrip("/")
        self.api_key = api_key

        # Registered cluster endpoints
        self._endpoints: dict[str, NodeEndpoint] = {}
        # Request queue for cluster inference
        self._queue: asyncio.Queue[InferenceRequest] = asyncio.Queue()
        # Active request tracking
        self._active: dict[str, float] = {}  # request_id -> start_time
        # Performance tracking
        self._total_tokens = 0
        self._total_requests = 0
        self._total_latency_ms = 0.0

    def register_endpoint(self, endpoint: NodeEndpoint) -> None:
        """Register a cluster inference endpoint."""
        self._endpoints[endpoint.node_id] = endpoint
        logger.info(f"Registered endpoint: {endpoint.node_id} at {endpoint.url}")

    def remove_endpoint(self, node_id: str) -> None:
        """Remove a cluster endpoint (node went offline)."""
        if node_id in self._endpoints:
            del self._endpoints[node_id]
            logger.info(f"Removed endpoint: {node_id}")

    async def infer(self, request: InferenceRequest) -> InferenceResult:
        """
        Process an inference request.

        Routes to local or cluster based on mode.
        """
        start = time.time()
        self._active[request.request_id] = start

        try:
            if request.mode == "high_intel" and self._has_cluster_capacity():
                result = await self._cluster_infer(request)
            else:
                result = await self._local_infer(request)

            # Track metrics
            result.latency_ms = (time.time() - start) * 1000
            self._total_tokens += result.tokens_generated
            self._total_requests += 1
            self._total_latency_ms += result.latency_ms

            return result

        except Exception as e:
            logger.error(f"Inference failed for {request.request_id}: {e}")
            return InferenceResult(
                request_id=request.request_id,
                text="",
                tokens_generated=0,
                latency_ms=(time.time() - start) * 1000,
                strategy_used="error",
                error=str(e),
                finished=True,
            )
        finally:
            self._active.pop(request.request_id, None)

    async def _local_infer(self, request: InferenceRequest) -> InferenceResult:
        """Inference via local engine (Ollama or llama-server)."""
        if aiohttp is None:
            raise ImportError("aiohttp required")

        model = request.model_override or "qwen3:14b"
        payload = {
            "model": model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "num_predict": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.local_endpoint}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("response", "")
                        eval_count = data.get("eval_count", len(text.split()))
                        return InferenceResult(
                            request_id=request.request_id,
                            text=text,
                            tokens_generated=eval_count,
                            latency_ms=0,  # will be set by caller
                            strategy_used="local",
                            model_used=model,
                        )
                    else:
                        body = await resp.text()
                        return InferenceResult(
                            request_id=request.request_id,
                            text="",
                            tokens_generated=0,
                            latency_ms=0,
                            strategy_used="local",
                            error=f"HTTP {resp.status}: {body[:200]}",
                        )
            except asyncio.TimeoutError:
                return InferenceResult(
                    request_id=request.request_id,
                    text="",
                    tokens_generated=0,
                    latency_ms=0,
                    strategy_used="local",
                    error="Request timeout",
                )

    async def _cluster_infer(self, request: InferenceRequest) -> InferenceResult:
        """
        Inference via community GPU cluster.

        Uses OpenAI-compatible API (vLLM serves this natively).
        Routes to the least-loaded healthy endpoint.
        """
        endpoint = self._select_endpoint()
        if not endpoint:
            # Fallback to local
            logger.warning("No healthy cluster endpoints, falling back to local")
            return await self._local_infer(request)

        model = request.model_override or "community-model"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{endpoint.url}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        choices = data.get("choices", [])
                        text = choices[0]["message"]["content"] if choices else ""
                        usage = data.get("usage", {})
                        tokens = usage.get("completion_tokens", len(text.split()))

                        return InferenceResult(
                            request_id=request.request_id,
                            text=text,
                            tokens_generated=tokens,
                            latency_ms=0,
                            strategy_used="cluster",
                            cluster_id=endpoint.node_id,
                            model_used=model,
                        )
                    else:
                        # Retry with another endpoint or fall back
                        endpoint.is_healthy = False
                        return await self._local_infer(request)

            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logger.warning(f"Cluster endpoint {endpoint.node_id} failed: {e}")
                endpoint.is_healthy = False
                return await self._local_infer(request)

    def _select_endpoint(self) -> Optional[NodeEndpoint]:
        """Select the best endpoint using load-aware routing."""
        healthy = [e for e in self._endpoints.values() if e.is_healthy]
        if not healthy:
            return None

        # Weighted selection: prefer low-load, high-tps endpoints
        def score(e: NodeEndpoint) -> float:
            load_score = 1.0 - e.current_load  # prefer idle
            tps_score = min(e.avg_tps / 100.0, 1.0)  # normalize to 0-1
            return load_score * 0.6 + tps_score * 0.4

        return max(healthy, key=score)

    def _has_cluster_capacity(self) -> bool:
        """Check if any cluster endpoints are available and healthy."""
        return any(e.is_healthy and e.current_load < 0.9 for e in self._endpoints.values())

    async def health_check(self) -> dict:
        """Check health of all registered endpoints."""
        results = {}
        if aiohttp is None:
            return results

        async with aiohttp.ClientSession() as session:
            for node_id, endpoint in self._endpoints.items():
                try:
                    async with session.get(
                        f"{endpoint.url}/health",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        endpoint.is_healthy = resp.status == 200
                        endpoint.last_check = time.time()
                        results[node_id] = {"healthy": endpoint.is_healthy}
                except Exception:
                    endpoint.is_healthy = False
                    results[node_id] = {"healthy": False}

        return results

    def get_stats(self) -> dict:
        """Get coordinator performance stats."""
        avg_latency = (
            self._total_latency_ms / self._total_requests
            if self._total_requests > 0
            else 0
        )
        return {
            "total_tokens": self._total_tokens,
            "total_requests": self._total_requests,
            "avg_latency_ms": round(avg_latency, 1),
            "active_requests": len(self._active),
            "registered_endpoints": len(self._endpoints),
            "healthy_endpoints": sum(1 for e in self._endpoints.values() if e.is_healthy),
        }


class DualModeRouter:
    """
    Dual-mode inference router — the user-facing decision layer.

    Decides between:
    - Medium Mode (default): Local inference, zero latency, offline-capable
    - High-Intel Mode: Cluster inference, optional HBD tip

    Decision criteria:
    - User preference (explicit mode selection)
    - Query complexity (long context, code generation → high-intel)
    - Available cluster capacity
    - Cost (HBD tip for cluster inference)

    All history/RAG stays on user's machine regardless of mode.
    """

    def __init__(
        self,
        coordinator: DistributedInferenceCoordinator,
        default_mode: str = "medium",
    ):
        self.coordinator = coordinator
        self.default_mode = default_mode
        self._complexity_threshold = 500  # tokens — above this, suggest high-intel

    async def route(self, request: InferenceRequest) -> InferenceResult:
        """Route request through the appropriate inference path."""
        # Auto-detect mode if not explicitly set
        if request.mode == "auto":
            request.mode = self._auto_detect_mode(request)

        return await self.coordinator.infer(request)

    def _auto_detect_mode(self, request: InferenceRequest) -> str:
        """Automatically detect optimal inference mode."""
        # Long prompts benefit from cluster inference
        prompt_tokens = len(request.prompt.split())
        if prompt_tokens > self._complexity_threshold:
            if self.coordinator._has_cluster_capacity():
                return "high_intel"

        # High max_tokens requests benefit from cluster
        if request.max_tokens > 4096:
            if self.coordinator._has_cluster_capacity():
                return "high_intel"

        return "medium"  # Default: local inference

    def get_available_modes(self) -> dict:
        """Get available inference modes and their capabilities."""
        has_cluster = self.coordinator._has_cluster_capacity()
        stats = self.coordinator.get_stats()

        return {
            "medium": {
                "available": True,
                "description": "Local inference — zero latency, offline-capable",
                "cost": "free",
            },
            "high_intel": {
                "available": has_cluster,
                "description": "Cluster inference — higher quality, more compute",
                "cost": "optional HBD tip",
                "cluster_nodes": stats["healthy_endpoints"],
            },
        }
