"""
hiveai/compute/community_coordinator.py

Spirit Bomb Community Coordinator — the brain of the community GPU cloud.

Responsibilities:
  1. Poll HivePoA for online compute nodes every POLL_INTERVAL seconds
  2. Group nodes into geo-aware clusters (latency-based affinity, <50ms target)
  3. Derive current community tier from pool state
  4. Publish tier manifests (HivePoA API + optionally Hive custom_json + IPFS)
  5. Manage auto-downgrade/upgrade as pool changes
  6. Configure inference routes based on cluster topology

Tier system (additive — more GPUs = more options, never removes what works):
  Solo (1):    0-1 GPUs — Hive-AI's own stack (v5-think + smart_call) unchanged
  Pool (2):    2+ GPUs — each serves independent requests (throughput scaling)
  Cluster (3): 2+ GPUs with <50ms latency + 24GB+ VRAM (combine via vLLM PP)

IMPORTANT: Tier configs must stay in sync with spirit-bomb-service.ts (HivePoA).

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

TIER_MODEL_CONFIG = {
    1: {
        "mode": "solo",
        "base_model": "hiveai-v5-think",
        "description": "Local Hive-AI stack (llama-server + smart routing + MoLoRA)",
        "active_experts": 0,
        "quantization": "gguf",
        "max_context_length": 32768,
        "speculative_decoding_enabled": False,
    },
    2: {
        "mode": "pool",
        "base_model": "hiveai-v5-think",
        "description": "Independent GPUs serving parallel requests — throughput scaling",
        "active_experts": 0,
        "quantization": "gguf",
        "max_context_length": 32768,
        "speculative_decoding_enabled": False,
    },
    3: {
        "mode": "cluster",
        "base_model": "Qwen3-32B",
        "description": "Pipeline-parallel larger model via vLLM + local smart routing",
        "active_experts": 4,
        "quantization": "awq",
        "max_context_length": 65536,
        "speculative_decoding_enabled": True,
    },
}

# Cluster qualification thresholds
MIN_CLUSTER_VRAM_GB = 24  # minimum combined VRAM for pipeline parallel

# Clustering constraints
MAX_CLUSTER_LATENCY_MS = 50  # intra-cluster latency target
TP_LATENCY_THRESHOLD_MS = 10  # tensor parallel requires <10ms
MIN_CLUSTER_SIZE = 2  # minimum nodes for a cluster
POLL_INTERVAL_SECONDS = 90  # 90 seconds — fast enough for real-time tier changes


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
    mode: str  # "solo", "pool", "cluster"
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
        self._settlement_counter = 0  # runs settlement every 4th cycle (~1 hour)

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

            # 3. Derive community tier (passes clusters for latency qualification)
            new_tier = self._derive_tier(total_gpus, active_clusters)
            if new_tier != self._current_tier:
                logger.info(f"Tier transition: {self._current_tier} → {new_tier} ({total_gpus} GPUs)")
                self._current_tier = new_tier

            # 4. Build and publish manifest
            config = TIER_MODEL_CONFIG[new_tier]
            manifest = TierManifest(
                tier=new_tier,
                mode=config["mode"],
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

            # 8. Run reward settlement every ~4 cycles (~1 hour with 15min polling)
            self._settlement_counter += 1
            if self._settlement_counter >= 4:
                self._settlement_counter = 0
                await self._run_settlement(session, new_tier)

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

    def _derive_tier(self, total_gpus: int, clusters: list = None) -> int:
        """Derive community tier from pool state (not just GPU count).

        Solo (1): 0-1 GPUs
        Pool (2): 2+ GPUs serving independently
        Cluster (3): 2+ GPUs with low latency + enough VRAM for pipeline parallel
        """
        if total_gpus <= 1:
            return 1

        # Check if any cluster qualifies for pipeline parallel
        if clusters:
            for cluster in clusters:
                c_gpus = getattr(cluster, "total_gpus", 0)
                c_vram = getattr(cluster, "total_vram_gb", 0)
                c_latency = getattr(cluster, "avg_latency_ms", 999) or 999
                if (c_gpus >= 2
                        and c_latency < MAX_CLUSTER_LATENCY_MS
                        and c_vram >= MIN_CLUSTER_VRAM_GB):
                    return 3

        # 2+ GPUs but no qualified cluster = Pool
        return 2

    def _estimate_tps(self, tier: int, total_gpus: int) -> float:
        """
        Estimate aggregate tokens per second for the community tier.

        Solo: single GPU serving v5-think (~80 tok/s)
        Pool: N GPUs each serving independently (~80 × N × 0.95)
        Cluster: pipeline parallel with bubble overhead (~40 × N × 0.50-0.65)
        """
        tier_mode = TIER_MODEL_CONFIG[tier]["mode"]

        if tier_mode == "solo":
            return 80.0  # single v5-think on one GPU

        if tier_mode == "pool":
            # Each GPU serves independently — near-linear scaling
            return round(80.0 * total_gpus * 0.95, 1)

        # Cluster: pipeline parallel has bubble overhead
        per_gpu = 40.0  # 32B model is slower per GPU than 14B
        if total_gpus <= 4:
            efficiency = 0.65  # PP bubble ~35% for 2-4 stages
        else:
            efficiency = 0.50  # higher bubble for more stages
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
        """Publish manifest to Hive blockchain via HivePoA's publish-hive endpoint.

        Delegates to HivePoA's SpiritBombService.publishManifestToHive() which
        handles the actual custom_json broadcast + reconciliation.
        """
        headers = self._auth_headers()
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.hivepoa_url}/api/community/tier/publish-hive",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("published"):
                            logger.info(f"Published to Hive blockchain: tx={data.get('hiveTxId')}")
                        else:
                            logger.debug(f"Hive publish skipped: {data.get('reason')}")
                    else:
                        body = await resp.text()
                        logger.warning(f"Hive publish failed: HTTP {resp.status}: {body[:200]}")
            except asyncio.TimeoutError:
                logger.warning("Hive publish timed out")
            except Exception as e:
                logger.error(f"Hive publish error: {e}")

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

    async def _run_settlement(self, session: aiohttp.ClientSession, tier: int) -> None:
        """Run reward settlement cycle for inference contributions."""
        try:
            from hiveai.compute.reward_settlement import RewardSettlementService
            settler = RewardSettlementService(
                hivepoa_url=self.hivepoa_url,
                api_key=self.api_key,
                current_tier=tier,
            )
            result = await settler.run_settlement_cycle()
            if result.payouts_submitted > 0:
                logger.info(
                    f"Settlement: {result.payouts_submitted} payouts, "
                    f"{result.total_hbd:.4f} HBD total"
                )
        except ImportError:
            logger.debug("Reward settlement not available (missing module)")
        except Exception as e:
            logger.error(f"Settlement failed: {e}")

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
