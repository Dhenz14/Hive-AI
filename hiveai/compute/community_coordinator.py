"""
hiveai/compute/community_coordinator.py

Spirit Bomb Community Coordinator — the brain of the community GPU cloud.

Responsibilities:
  1. Poll HivePoA for online compute nodes every POLL_INTERVAL seconds
  2. Group nodes into geo-aware clusters (latency-based affinity, <50ms target)
  3. Derive current community tier from total GPU count
  4. Publish tier manifests (HivePoA API + optionally Hive custom_json + IPFS)
  5. Manage auto-downgrade/upgrade as pool changes
  6. Configure inference routes based on cluster topology

Tier thresholds:
  Tier 1: <15 GPUs   → Base 14B model, 2 MoE experts, local-only
  Tier 2: 15-40 GPUs → Enhanced model, 4 experts, optional cluster inference
  Tier 3: 40+ GPUs   → Full brain, 8+ experts, geo-clustered inference

Usage:
    coordinator = CommunityCoordinator(hivepoa_url="http://localhost:5000")
    await coordinator.run()  # Blocks, polling every 15 min
"""

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

logger = logging.getLogger(__name__)

# ── Tier Configuration ──────────────────────────────────────────

TIER_THRESHOLDS = {
    1: {"min_gpus": 0, "max_gpus": 14},
    2: {"min_gpus": 15, "max_gpus": 39},
    3: {"min_gpus": 40, "max_gpus": float("inf")},
}

TIER_MODEL_CONFIG = {
    1: {
        "base_model": "Qwen3-14B",
        "active_experts": 2,
        "quantization": "awq",
        "max_context_length": 32768,
        "speculative_decoding_enabled": False,
    },
    2: {
        "base_model": "Qwen3-32B",
        "active_experts": 4,
        "quantization": "awq",
        "max_context_length": 65536,
        "speculative_decoding_enabled": True,
    },
    3: {
        "base_model": "Qwen3-Coder-80B-MoE",
        "active_experts": 8,
        "quantization": "fp16",
        "max_context_length": 131072,
        "speculative_decoding_enabled": True,
    },
}

# Clustering constraints
MAX_CLUSTER_LATENCY_MS = 50  # intra-cluster latency target
TP_LATENCY_THRESHOLD_MS = 10  # tensor parallel requires <10ms
MIN_CLUSTER_SIZE = 2  # minimum nodes for a cluster
POLL_INTERVAL_SECONDS = 900  # 15 minutes


@dataclass
class NodeInfo:
    """Compute node snapshot from HivePoA."""
    id: str
    gpu_model: str
    gpu_vram_gb: int
    status: str
    region: str = "unknown"
    geo_hash: str = ""
    bandwidth_gbps: float = 0.0
    reputation_score: int = 50


@dataclass
class ClusterCandidate:
    """A proposed or active GPU cluster."""
    id: str = ""
    region: str = "unknown"
    nodes: list[NodeInfo] = field(default_factory=list)
    total_vram_gb: int = 0
    avg_latency_ms: float = 0.0

    @property
    def total_gpus(self) -> int:
        return len(self.nodes)

    @property
    def can_tensor_parallel(self) -> bool:
        return self.avg_latency_ms < TP_LATENCY_THRESHOLD_MS and self.total_gpus >= 2


@dataclass
class TierManifest:
    """Published tier state snapshot."""
    tier: int
    total_gpus: int
    total_vram_gb: int
    active_clusters: int
    base_model: str
    active_experts: int
    quantization: str
    max_context_length: int
    speculative_decoding_enabled: bool
    estimated_tps: Optional[float] = None
    published_at: Optional[str] = None


class CommunityCoordinator:
    """
    Spirit Bomb coordinator — determines community tier and manages clusters.

    Architecture:
    - Stateless polling loop (15 min default)
    - Reads node state from HivePoA API
    - Writes cluster/tier state back to HivePoA API
    - Optionally publishes to Hive blockchain (custom_json)
    """

    def __init__(
        self,
        hivepoa_url: str = "http://localhost:5000",
        api_key: str = "",
        poll_interval: int = POLL_INTERVAL_SECONDS,
        hive_publisher: Optional[object] = None,  # Future: HiveClient for custom_json
    ):
        self.hivepoa_url = hivepoa_url.rstrip("/")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.hive_publisher = hive_publisher
        self._current_tier = 1
        self._last_manifest: Optional[TierManifest] = None

    async def run(self) -> None:
        """Main coordinator loop. Blocks, polling at the configured interval."""
        if aiohttp is None:
            raise ImportError("aiohttp is required: pip install aiohttp")

        logger.info(
            f"Community coordinator started — polling every {self.poll_interval}s, "
            f"HivePoA at {self.hivepoa_url}"
        )

        while True:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                logger.info("Coordinator cancelled, shutting down")
                break
            except Exception as e:
                logger.error(f"Coordinator poll cycle failed: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _poll_cycle(self) -> None:
        """Single poll cycle: fetch nodes → cluster → derive tier → publish."""
        async with aiohttp.ClientSession() as session:
            # 1. Fetch online compute nodes
            nodes = await self._fetch_online_nodes(session)
            if not nodes:
                logger.info("No online nodes found — tier remains at 1")
                return

            total_gpus = len(nodes)
            total_vram = sum(n.gpu_vram_gb for n in nodes)
            logger.info(f"Pool snapshot: {total_gpus} GPUs, {total_vram} GB total VRAM")

            # 2. Group nodes into geo-aware clusters
            clusters = self._build_clusters(nodes)
            active_clusters = [c for c in clusters if c.total_gpus >= MIN_CLUSTER_SIZE]
            logger.info(f"Formed {len(active_clusters)} active clusters from {len(clusters)} candidates")

            # 3. Derive community tier
            new_tier = self._derive_tier(total_gpus)
            if new_tier != self._current_tier:
                logger.info(f"Tier transition: {self._current_tier} → {new_tier} ({total_gpus} GPUs)")
                self._current_tier = new_tier

            # 4. Build and publish manifest
            config = TIER_MODEL_CONFIG[new_tier]
            manifest = TierManifest(
                tier=new_tier,
                total_gpus=total_gpus,
                total_vram_gb=total_vram,
                active_clusters=len(active_clusters),
                base_model=config["base_model"],
                active_experts=config["active_experts"],
                quantization=config["quantization"],
                max_context_length=config["max_context_length"],
                speculative_decoding_enabled=config["speculative_decoding_enabled"],
                estimated_tps=self._estimate_tps(new_tier, total_gpus),
                published_at=datetime.now(timezone.utc).isoformat(),
            )

            # 5. Push clusters to HivePoA
            for cluster in active_clusters:
                await self._sync_cluster(session, cluster)

            # 6. Publish tier manifest
            await self._publish_manifest(session, manifest)
            self._last_manifest = manifest

            # 7. Configure inference routes
            await self._update_inference_routes(session, active_clusters, manifest)

    async def _fetch_online_nodes(self, session: aiohttp.ClientSession) -> list[NodeInfo]:
        """Fetch all online compute nodes from HivePoA."""
        headers = self._auth_headers()
        try:
            async with session.get(
                f"{self.hivepoa_url}/api/compute/nodes",
                headers=headers,
                params={"status": "online"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch nodes: HTTP {resp.status}")
                    return []
                data = await resp.json()
                nodes_raw = data if isinstance(data, list) else data.get("nodes", [])
                return [
                    NodeInfo(
                        id=n.get("id", ""),
                        gpu_model=n.get("gpuModel", n.get("gpu_model", "unknown")),
                        gpu_vram_gb=int(n.get("gpuVramGb", n.get("gpu_vram_gb", 0))),
                        status=n.get("status", "unknown"),
                        reputation_score=int(n.get("reputationScore", n.get("reputation_score", 50))),
                    )
                    for n in nodes_raw
                    if n.get("status") == "online"
                ]
        except Exception as e:
            logger.error(f"Error fetching nodes: {e}")
            return []

    def _build_clusters(self, nodes: list[NodeInfo]) -> list[ClusterCandidate]:
        """
        Group nodes into geo-aware clusters.

        Current implementation: simple region-based grouping.
        Future: latency-probing mesh (Tailscale DERP, ICMP ping matrix).
        """
        by_region: dict[str, list[NodeInfo]] = {}
        for node in nodes:
            region = node.region or "default"
            by_region.setdefault(region, []).append(node)

        clusters = []
        for region, region_nodes in by_region.items():
            # For large regions, subdivide by VRAM tier for pipeline parallel compatibility
            vram_groups: dict[str, list[NodeInfo]] = {}
            for n in region_nodes:
                tier_key = f"{region}-{'high' if n.gpu_vram_gb >= 16 else 'mid' if n.gpu_vram_gb >= 8 else 'low'}"
                vram_groups.setdefault(tier_key, []).append(n)

            for group_key, group_nodes in vram_groups.items():
                cluster = ClusterCandidate(
                    region=region,
                    nodes=group_nodes,
                    total_vram_gb=sum(n.gpu_vram_gb for n in group_nodes),
                    avg_latency_ms=25.0,  # placeholder until latency probing
                )
                clusters.append(cluster)

        return clusters

    def _derive_tier(self, total_gpus: int) -> int:
        """Derive community tier from total GPU count."""
        for tier in (3, 2, 1):
            thresholds = TIER_THRESHOLDS[tier]
            if total_gpus >= thresholds["min_gpus"]:
                return tier
        return 1

    def _estimate_tps(self, tier: int, total_gpus: int) -> float:
        """
        Estimate aggregate tokens per second for the community tier.

        Based on vLLM benchmarks for different model sizes:
        - 14B AWQ: ~80 tok/s per GPU
        - 32B AWQ: ~40 tok/s per GPU (pipeline parallel)
        - 80B MoE fp16: ~25 tok/s per GPU (expert parallel)
        """
        base_tps = {1: 80.0, 2: 40.0, 3: 25.0}
        per_gpu = base_tps.get(tier, 40.0)
        # Pipeline parallel efficiency: ~85% for 2-4 GPUs, ~70% for 4+
        if total_gpus <= 4:
            efficiency = 0.85
        elif total_gpus <= 16:
            efficiency = 0.70
        else:
            efficiency = 0.55  # communication overhead at scale
        return round(per_gpu * total_gpus * efficiency, 1)

    async def _sync_cluster(
        self, session: aiohttp.ClientSession, cluster: ClusterCandidate
    ) -> None:
        """Push cluster state to HivePoA."""
        headers = self._auth_headers()
        payload = {
            "name": f"cluster-{cluster.region}-{len(cluster.nodes)}gpu",
            "region": cluster.region,
            "status": "active" if cluster.total_gpus >= MIN_CLUSTER_SIZE else "forming",
            "totalGpus": cluster.total_gpus,
            "totalVramGb": cluster.total_vram_gb,
            "avgLatencyMs": cluster.avg_latency_ms,
            "canTensorParallel": cluster.can_tensor_parallel,
            "canPipelineParallel": True,
        }
        try:
            async with session.post(
                f"{self.hivepoa_url}/api/community/clusters",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    cluster.id = data.get("id", "")
                    logger.debug(f"Synced cluster {cluster.id} ({cluster.region}, {cluster.total_gpus} GPUs)")
                else:
                    body = await resp.text()
                    logger.warning(f"Failed to sync cluster: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Error syncing cluster: {e}")

    async def _publish_manifest(
        self, session: aiohttp.ClientSession, manifest: TierManifest
    ) -> None:
        """Publish tier manifest to HivePoA + optionally Hive blockchain."""
        headers = self._auth_headers()
        payload = asdict(manifest)
        try:
            async with session.post(
                f"{self.hivepoa_url}/api/community/tier",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(
                        f"Published tier {manifest.tier} manifest: "
                        f"{manifest.total_gpus} GPUs, {manifest.active_clusters} clusters, "
                        f"model={manifest.base_model}, experts={manifest.active_experts}"
                    )
                else:
                    body = await resp.text()
                    logger.warning(f"Failed to publish manifest: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Error publishing manifest: {e}")

        # Future: publish to Hive blockchain as custom_json
        if self.hive_publisher:
            try:
                await self._publish_to_hive(manifest)
            except Exception as e:
                logger.error(f"Hive publish failed: {e}")

    async def _publish_to_hive(self, manifest: TierManifest) -> None:
        """Publish manifest to Hive blockchain via custom_json operation.

        Format: custom_json with id='spiritbomb_manifest', required_posting_auths.
        """
        # Placeholder — requires hive-py or beem integration
        manifest_json = json.dumps(asdict(manifest), separators=(",", ":"))
        manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()[:16]
        logger.info(f"Would publish to Hive: spiritbomb_manifest #{manifest_hash}")

    async def _update_inference_routes(
        self,
        session: aiohttp.ClientSession,
        clusters: list[ClusterCandidate],
        manifest: TierManifest,
    ) -> None:
        """Configure inference routes based on current cluster topology."""
        headers = self._auth_headers()

        # Always maintain a local inference route
        local_route = {
            "mode": "local",
            "modelName": manifest.base_model,
            "pipelineStages": 1,
            "tensorParallelSize": 1,
            "status": "active",
            "priority": 10,  # local always has base priority
        }
        await self._post_route(session, headers, local_route)

        # For each cluster with 2+ GPUs, create a cluster inference route
        for cluster in clusters:
            if cluster.total_gpus < 2:
                continue

            # Determine parallelism strategy based on cluster capabilities
            if cluster.can_tensor_parallel and cluster.total_gpus <= 8:
                # TP within cluster: requires <10ms latency
                tp_size = min(cluster.total_gpus, 8)
                pp_stages = 1
            else:
                # PP across cluster: works with <50ms latency
                tp_size = 1
                pp_stages = min(cluster.total_gpus, 8)

            route = {
                "clusterId": cluster.id,
                "mode": "cluster",
                "modelName": manifest.base_model,
                "pipelineStages": pp_stages,
                "tensorParallelSize": tp_size,
                "status": "active",
                "priority": 20 + cluster.total_gpus,  # more GPUs = higher priority
            }
            await self._post_route(session, headers, route)

    async def _post_route(
        self, session: aiohttp.ClientSession, headers: dict, route: dict
    ) -> None:
        """Post a single inference route to HivePoA."""
        try:
            async with session.post(
                f"{self.hivepoa_url}/api/community/inference/routes",
                headers=headers,
                json=route,
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(f"Failed to post route: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Error posting route: {e}")

    def _auth_headers(self) -> dict:
        """Build auth headers for HivePoA API calls.

        Uses ApiKey scheme for agent authentication (compatible with
        HivePoA's requireAnyAuth middleware on community routes).
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers

    @property
    def current_tier(self) -> int:
        return self._current_tier

    @property
    def last_manifest(self) -> Optional[TierManifest]:
        return self._last_manifest


# ── CLI Entry Point ─────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Spirit Bomb Community Coordinator")
    parser.add_argument("--hivepoa-url", default="http://localhost:5000", help="HivePoA server URL")
    parser.add_argument("--api-key", default="", help="Bearer token for HivePoA API")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SECONDS, help="Poll interval in seconds")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    coordinator = CommunityCoordinator(
        hivepoa_url=args.hivepoa_url,
        api_key=args.api_key,
        poll_interval=args.poll_interval,
    )
    await coordinator.run()


if __name__ == "__main__":
    asyncio.run(main())
