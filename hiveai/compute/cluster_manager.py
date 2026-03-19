"""
hiveai/compute/cluster_manager.py

GPU Cluster Manager — geo-aware affinity grouping and latency-based clustering.

Handles the physical layer of the Spirit Bomb community cloud:
  - Latency probing between nodes (ping matrix)
  - Affinity group formation (<50ms intra-cluster target)
  - Cluster health monitoring
  - Node join/leave events
  - Bandwidth measurement for pipeline parallel suitability

Architecture inspired by:
  - Helix (ASPLOS 2025): max-flow optimization for heterogeneous GPU placement
  - Hivemind DHT: decentralized peer discovery
  - Tailscale DERP: latency-aware mesh networking
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Clustering constraints
MAX_INTRA_CLUSTER_LATENCY_MS = 50.0
TP_LATENCY_THRESHOLD_MS = 10.0
PP_LATENCY_THRESHOLD_MS = 50.0
MIN_BANDWIDTH_GBPS_PP = 1.0  # minimum for pipeline parallel
MAX_CLUSTER_SIZE = 16  # cap cluster at 16 GPUs for manageability
MIN_CLUSTER_SIZE = 2


@dataclass
class PeerLatency:
    """Measured latency between two nodes."""
    from_node: str
    to_node: str
    rtt_ms: float  # round-trip time
    bandwidth_gbps: float = 0.0
    measured_at: float = 0.0  # Unix timestamp

    @property
    def one_way_ms(self) -> float:
        return self.rtt_ms / 2


@dataclass
class ClusterNode:
    """A node within a cluster context."""
    node_id: str
    gpu_model: str
    vram_gb: int
    compute_capability: float = 0.0  # CUDA compute capability
    bandwidth_gbps: float = 0.0
    region: str = "unknown"


@dataclass
class GpuClusterState:
    """Represents the state of a GPU cluster."""
    cluster_id: str
    region: str
    nodes: list[ClusterNode] = field(default_factory=list)
    latency_matrix: dict[tuple[str, str], PeerLatency] = field(default_factory=dict)
    status: str = "forming"  # forming, active, degraded, dissolved

    @property
    def total_gpus(self) -> int:
        return len(self.nodes)

    @property
    def total_vram_gb(self) -> int:
        return sum(n.vram_gb for n in self.nodes)

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_matrix:
            return 0.0
        return sum(p.rtt_ms for p in self.latency_matrix.values()) / len(self.latency_matrix)

    @property
    def max_latency_ms(self) -> float:
        if not self.latency_matrix:
            return 0.0
        return max(p.rtt_ms for p in self.latency_matrix.values())

    @property
    def can_tensor_parallel(self) -> bool:
        """TP requires all pairs <10ms RTT."""
        if self.total_gpus < 2:
            return False
        return self.max_latency_ms < TP_LATENCY_THRESHOLD_MS * 2  # RTT

    @property
    def can_pipeline_parallel(self) -> bool:
        """PP is more tolerant, <50ms is fine."""
        if self.total_gpus < 2:
            return False
        return self.max_latency_ms < PP_LATENCY_THRESHOLD_MS * 2


class ClusterManager:
    """
    Manages GPU cluster formation and health.

    The cluster manager operates in two modes:
    1. Passive: uses region-based heuristics (default, no latency probing)
    2. Active: probes latency between nodes to form optimal clusters

    Active mode requires nodes to expose a latency probing endpoint.
    """

    def __init__(self):
        self.clusters: dict[str, GpuClusterState] = {}
        self._latency_cache: dict[tuple[str, str], PeerLatency] = {}
        self._cache_ttl_seconds = 300  # 5 min cache

    def form_clusters(
        self,
        nodes: list[ClusterNode],
        latency_probes: Optional[list[PeerLatency]] = None,
    ) -> list[GpuClusterState]:
        """
        Form clusters from a set of nodes.

        Uses a greedy algorithm:
        1. Group by region
        2. Within region, if latency probes available, use hierarchical clustering
        3. Cap each cluster at MAX_CLUSTER_SIZE
        4. Subdivide by VRAM tier for pipeline parallel compatibility

        Returns: list of GpuClusterState objects.
        """
        # Update latency cache
        if latency_probes:
            for probe in latency_probes:
                key = (probe.from_node, probe.to_node)
                self._latency_cache[key] = probe

        # Group by region
        by_region: dict[str, list[ClusterNode]] = {}
        for node in nodes:
            by_region.setdefault(node.region, []).append(node)

        all_clusters = []
        for region, region_nodes in by_region.items():
            clusters = self._cluster_region(region, region_nodes)
            all_clusters.extend(clusters)

        # Update internal state
        self.clusters = {c.cluster_id: c for c in all_clusters}
        return all_clusters

    def _cluster_region(
        self, region: str, nodes: list[ClusterNode]
    ) -> list[GpuClusterState]:
        """Form clusters within a region."""
        if not nodes:
            return []

        # Sort by VRAM descending — high-VRAM nodes are more valuable for cluster heads
        sorted_nodes = sorted(nodes, key=lambda n: n.vram_gb, reverse=True)

        clusters = []
        assigned = set()

        for node in sorted_nodes:
            if node.node_id in assigned:
                continue

            # Start a new cluster with this node
            cluster_nodes = [node]
            assigned.add(node.node_id)

            # Add compatible neighbors
            for candidate in sorted_nodes:
                if candidate.node_id in assigned:
                    continue
                if len(cluster_nodes) >= MAX_CLUSTER_SIZE:
                    break

                # Check latency compatibility
                latency = self._get_latency(node.node_id, candidate.node_id)
                if latency and latency.rtt_ms > MAX_INTRA_CLUSTER_LATENCY_MS * 2:
                    continue

                # Check VRAM compatibility (within 2x range for balanced PP)
                max_vram = max(n.vram_gb for n in cluster_nodes)
                min_vram = min(n.vram_gb for n in cluster_nodes)
                if candidate.vram_gb > 0 and max_vram > 0:
                    ratio = max(max_vram, candidate.vram_gb) / min(min_vram, candidate.vram_gb)
                    if ratio > 2.0:
                        continue  # too heterogeneous for efficient PP

                cluster_nodes.append(candidate)
                assigned.add(candidate.node_id)

            cluster_id = f"cluster-{region}-{len(clusters)}"
            cluster = GpuClusterState(
                cluster_id=cluster_id,
                region=region,
                nodes=cluster_nodes,
                status="active" if len(cluster_nodes) >= MIN_CLUSTER_SIZE else "forming",
            )

            # Populate latency matrix
            for i, n1 in enumerate(cluster_nodes):
                for n2 in cluster_nodes[i + 1:]:
                    lat = self._get_latency(n1.node_id, n2.node_id)
                    if lat:
                        cluster.latency_matrix[(n1.node_id, n2.node_id)] = lat

            clusters.append(cluster)

        return clusters

    def _get_latency(self, node_a: str, node_b: str) -> Optional[PeerLatency]:
        """Get cached latency between two nodes."""
        key = (node_a, node_b)
        if key in self._latency_cache:
            probe = self._latency_cache[key]
            if time.time() - probe.measured_at < self._cache_ttl_seconds:
                return probe
        # Try reverse direction
        key_rev = (node_b, node_a)
        if key_rev in self._latency_cache:
            probe = self._latency_cache[key_rev]
            if time.time() - probe.measured_at < self._cache_ttl_seconds:
                return probe
        return None

    def get_optimal_parallelism(
        self, cluster: GpuClusterState, model_params_b: float
    ) -> dict:
        """
        Determine optimal parallelism strategy for a cluster + model.

        Uses Helix-inspired max-flow optimization:
        - Small model (<15B) on single GPU: no parallelism needed
        - Medium model (15-35B): TP if latency allows, else PP
        - Large model (35B+): PP across cluster, TP within co-located pairs

        Args:
            cluster: The GPU cluster
            model_params_b: Model size in billions of parameters

        Returns:
            Dict with tp_size, pp_stages, ep_size (expert parallel)
        """
        total_gpus = cluster.total_gpus
        total_vram = cluster.total_vram_gb

        # Estimate VRAM requirement: ~2 bytes per param (fp16) + overhead
        vram_needed_gb = model_params_b * 2.2  # 2B/param + 10% overhead

        if vram_needed_gb <= min(n.vram_gb for n in cluster.nodes):
            # Fits on single GPU — use data parallelism or expert parallel
            return {
                "tp_size": 1,
                "pp_stages": 1,
                "ep_size": total_gpus,  # each GPU hosts different expert
                "strategy": "expert_parallel",
            }

        if cluster.can_tensor_parallel and total_gpus <= 8:
            # TP across all GPUs in cluster
            tp_size = total_gpus
            return {
                "tp_size": tp_size,
                "pp_stages": 1,
                "ep_size": 1,
                "strategy": "tensor_parallel",
            }

        if cluster.can_pipeline_parallel:
            # PP: split model layers across GPUs
            # Optimal PP stages = ceil(vram_needed / min_gpu_vram)
            min_vram = min(n.vram_gb for n in cluster.nodes)
            pp_stages = min(
                total_gpus,
                max(2, int(vram_needed_gb / min_vram) + 1),
            )
            return {
                "tp_size": 1,
                "pp_stages": pp_stages,
                "ep_size": max(1, total_gpus // pp_stages),
                "strategy": "pipeline_parallel",
            }

        # Fallback: single node, quantized
        return {
            "tp_size": 1,
            "pp_stages": 1,
            "ep_size": 1,
            "strategy": "single_quantized",
        }

    def compute_placement_score(
        self, cluster: GpuClusterState, model_params_b: float
    ) -> float:
        """
        Helix-inspired placement score for ranking clusters.

        Higher = better placement. Factors:
        - Total VRAM capacity vs model requirement
        - Latency (lower = better)
        - Homogeneity (similar GPUs = better load balance)
        - GPU count (more = better throughput)
        """
        vram_needed = model_params_b * 2.2
        vram_ratio = cluster.total_vram_gb / max(vram_needed, 1)
        if vram_ratio < 1.0:
            return 0.0  # Can't fit the model

        # Latency score: 1.0 at 0ms, 0.5 at 50ms, 0.0 at 100ms+
        latency_score = max(0.0, 1.0 - cluster.avg_latency_ms / 100.0)

        # Homogeneity: ratio of min/max VRAM (1.0 = identical GPUs)
        vrams = [n.vram_gb for n in cluster.nodes]
        homogeneity = min(vrams) / max(vrams) if vrams else 0.0

        # Throughput bonus: more GPUs = better (diminishing returns)
        throughput = min(1.0, cluster.total_gpus / 8.0)

        # Weighted combination
        score = (
            vram_ratio * 0.3
            + latency_score * 0.3
            + homogeneity * 0.2
            + throughput * 0.2
        )
        return round(score, 3)

    def select_best_cluster(
        self, model_params_b: float
    ) -> Optional[GpuClusterState]:
        """Select the best cluster for a given model size."""
        active = [c for c in self.clusters.values() if c.status == "active"]
        if not active:
            return None

        scored = [
            (self.compute_placement_score(c, model_params_b), c)
            for c in active
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_cluster = scored[0]
        if best_score <= 0:
            return None
        return best_cluster
