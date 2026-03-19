"""
hiveai/compute/elastic_moe.py

Elastic Mixture-of-Experts wrapper — tier-aware expert activation.

The core scaling mechanism of the Spirit Bomb: as more GPUs join the
community pool, more MoE experts become active, increasing the effective
model intelligence without changing the base architecture.

Architecture:
  - Wraps any MoE model (DeepSeek-V3, Qwen3-MoE, Mixtral)
  - Dynamically activates/deactivates expert replicas based on current tier
  - Experts distributed across community GPU cluster via Hivemind DHT
  - Router selects top-K experts per token, K scales with tier

Key design decisions:
  - Based on Hivemind's DecentralizedMixtureOfExperts module
  - Expert weights stored on IPFS, loaded on demand
  - Router weights are lightweight (<1MB), cached on every node
  - Expert activation is gradual: new GPUs host expert replicas
  - Graceful degradation: if experts go offline, router falls back

Tier → Expert mapping:
  Tier 1 (<15 GPUs):  2 experts active (base intelligence)
  Tier 2 (15-40):     4 experts active (enhanced)
  Tier 3 (40+):       8+ experts active (full brain)

Research references:
  - DeepSeek-V3: MoE with 256 experts, top-8 routing
  - Hivemind DecentralizedMixtureOfExperts: fault-tolerant distributed experts
  - Switch Transformer: simplified top-1 expert routing
  - GShard: group-level expert sharding
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    BASE = 1
    ENHANCED = 2
    FULL = 3


# Expert activation configuration per tier
TIER_EXPERT_CONFIG = {
    Tier.BASE: {
        "active_experts": 2,
        "top_k": 2,  # top-K routing
        "expert_capacity_factor": 1.25,
        "load_balance_loss_weight": 0.01,
    },
    Tier.ENHANCED: {
        "active_experts": 4,
        "top_k": 2,
        "expert_capacity_factor": 1.5,
        "load_balance_loss_weight": 0.01,
    },
    Tier.FULL: {
        "active_experts": 8,
        "top_k": 2,
        "expert_capacity_factor": 2.0,
        "load_balance_loss_weight": 0.005,
    },
}

# Model-specific expert counts (total available, not active)
MODEL_EXPERT_COUNTS = {
    "Qwen3-Coder-80B-MoE": {"total_experts": 64, "hidden_size": 5120, "expert_size_mb": 320},
    "DeepSeek-V3": {"total_experts": 256, "hidden_size": 7168, "expert_size_mb": 200},
    "Mixtral-8x7B": {"total_experts": 8, "hidden_size": 4096, "expert_size_mb": 1400},
    "Mixtral-8x22B": {"total_experts": 8, "hidden_size": 6144, "expert_size_mb": 4400},
}


@dataclass
class ExpertReplica:
    """Represents a single expert replica hosted on a community GPU."""
    expert_id: int  # which expert in the MoE
    node_id: str  # which community node hosts it
    gpu_model: str
    vram_gb: int
    status: str = "loading"  # loading, ready, busy, offline
    load_factor: float = 0.0  # 0.0 (idle) to 1.0 (at capacity)
    ipfs_cid: Optional[str] = None  # weight shard CID
    last_heartbeat: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.status in ("ready", "busy") and time.time() - self.last_heartbeat < 60


@dataclass
class ExpertPool:
    """Pool of expert replicas for a single expert ID."""
    expert_id: int
    replicas: list[ExpertReplica] = field(default_factory=list)

    @property
    def healthy_replicas(self) -> list[ExpertReplica]:
        return [r for r in self.replicas if r.is_healthy]

    @property
    def is_available(self) -> bool:
        return len(self.healthy_replicas) > 0

    def least_loaded_replica(self) -> Optional[ExpertReplica]:
        """Get the least loaded healthy replica for load balancing."""
        healthy = self.healthy_replicas
        if not healthy:
            return None
        return min(healthy, key=lambda r: r.load_factor)


class ElasticMoEManager:
    """
    Manages elastic expert activation based on community tier.

    This is the brain behind dynamic scaling — it decides:
    - Which experts are active
    - Where expert replicas are hosted
    - How to route tokens to experts
    - How to gracefully handle expert failures

    The manager doesn't run inference itself — it configures the
    inference runtime (vLLM, Hivemind, or local engine) with the
    correct expert topology.
    """

    def __init__(self, model_name: str = "Qwen3-Coder-80B-MoE"):
        self.model_name = model_name
        self.model_config = MODEL_EXPERT_COUNTS.get(model_name, {
            "total_experts": 8,
            "hidden_size": 4096,
            "expert_size_mb": 500,
        })
        self.expert_pools: dict[int, ExpertPool] = {}
        self._current_tier = Tier.BASE
        self._active_expert_ids: list[int] = []

    def set_tier(self, tier: int) -> dict:
        """
        Update the active tier and reconfigure expert activation.

        Returns a config dict that can be passed to the inference engine.
        """
        new_tier = Tier(tier)
        old_tier = self._current_tier
        self._current_tier = new_tier

        config = TIER_EXPERT_CONFIG[new_tier]
        target_experts = config["active_experts"]
        total_available = self.model_config["total_experts"]

        # Select which experts to activate
        # Strategy: keep currently active experts + add more, or trim
        if len(self._active_expert_ids) < target_experts:
            # Scale up: add experts
            needed = target_experts - len(self._active_expert_ids)
            all_ids = set(range(total_available))
            available = sorted(all_ids - set(self._active_expert_ids))
            # Prefer experts that already have replicas
            prioritized = sorted(
                available,
                key=lambda eid: len(self.expert_pools.get(eid, ExpertPool(eid)).healthy_replicas),
                reverse=True,
            )
            self._active_expert_ids.extend(prioritized[:needed])
        elif len(self._active_expert_ids) > target_experts:
            # Scale down: deactivate least-used experts
            usage = {
                eid: sum(r.load_factor for r in self.expert_pools.get(eid, ExpertPool(eid)).replicas)
                for eid in self._active_expert_ids
            }
            sorted_by_usage = sorted(self._active_expert_ids, key=lambda eid: usage.get(eid, 0))
            excess = len(self._active_expert_ids) - target_experts
            for eid in sorted_by_usage[:excess]:
                self._active_expert_ids.remove(eid)

        tier_changed = old_tier != new_tier
        if tier_changed:
            logger.info(
                f"MoE tier transition: {old_tier.name} → {new_tier.name}, "
                f"experts: {len(self._active_expert_ids)}/{total_available} active"
            )

        return {
            "tier": new_tier.value,
            "tier_name": new_tier.name,
            "model_name": self.model_name,
            "active_experts": self._active_expert_ids[:],
            "num_active_experts": len(self._active_expert_ids),
            "total_experts": total_available,
            "top_k": config["top_k"],
            "expert_capacity_factor": config["expert_capacity_factor"],
            "load_balance_loss_weight": config["load_balance_loss_weight"],
            "tier_changed": tier_changed,
        }

    def register_expert_replica(
        self,
        expert_id: int,
        node_id: str,
        gpu_model: str,
        vram_gb: int,
        ipfs_cid: Optional[str] = None,
    ) -> ExpertReplica:
        """Register a new expert replica hosted on a community node."""
        if expert_id not in self.expert_pools:
            self.expert_pools[expert_id] = ExpertPool(expert_id=expert_id)

        replica = ExpertReplica(
            expert_id=expert_id,
            node_id=node_id,
            gpu_model=gpu_model,
            vram_gb=vram_gb,
            status="ready",
            ipfs_cid=ipfs_cid,
            last_heartbeat=time.time(),
        )
        self.expert_pools[expert_id].replicas.append(replica)

        logger.info(
            f"Registered expert {expert_id} replica on node {node_id} "
            f"({gpu_model}, {vram_gb}GB)"
        )
        return replica

    def remove_node(self, node_id: str) -> int:
        """Remove all expert replicas for a node (node went offline)."""
        removed = 0
        for pool in self.expert_pools.values():
            before = len(pool.replicas)
            pool.replicas = [r for r in pool.replicas if r.node_id != node_id]
            removed += before - len(pool.replicas)

        if removed > 0:
            logger.info(f"Removed {removed} expert replicas for offline node {node_id}")
        return removed

    def route_token(self, router_scores: list[float]) -> list[dict]:
        """
        Route a token to top-K active experts based on router scores.

        Args:
            router_scores: Softmax scores from the MoE router, one per expert

        Returns:
            List of dicts with {expert_id, node_id, weight} for the selected experts
        """
        config = TIER_EXPERT_CONFIG[self._current_tier]
        top_k = config["top_k"]

        # Filter to active experts only
        active_scores = [
            (eid, router_scores[eid] if eid < len(router_scores) else 0.0)
            for eid in self._active_expert_ids
        ]
        active_scores.sort(key=lambda x: x[1], reverse=True)

        # Select top-K
        selected = active_scores[:top_k]

        # Normalize weights
        total_weight = sum(s for _, s in selected)
        if total_weight == 0:
            total_weight = 1.0

        routes = []
        for expert_id, score in selected:
            pool = self.expert_pools.get(expert_id)
            if pool and pool.is_available:
                replica = pool.least_loaded_replica()
                routes.append({
                    "expert_id": expert_id,
                    "node_id": replica.node_id if replica else "local",
                    "weight": score / total_weight,
                    "is_remote": replica is not None and replica.node_id != "local",
                })
            else:
                # Expert unavailable — fallback to local computation
                routes.append({
                    "expert_id": expert_id,
                    "node_id": "local",
                    "weight": score / total_weight,
                    "is_remote": False,
                })

        return routes

    def get_expert_distribution(self) -> dict:
        """Get current expert distribution summary for monitoring."""
        distribution = {}
        for eid in self._active_expert_ids:
            pool = self.expert_pools.get(eid, ExpertPool(eid))
            distribution[eid] = {
                "total_replicas": len(pool.replicas),
                "healthy_replicas": len(pool.healthy_replicas),
                "is_available": pool.is_available,
                "nodes": [r.node_id for r in pool.healthy_replicas],
            }

        total_replicas = sum(d["total_replicas"] for d in distribution.values())
        healthy_replicas = sum(d["healthy_replicas"] for d in distribution.values())

        return {
            "model": self.model_name,
            "tier": self._current_tier.value,
            "tier_name": self._current_tier.name,
            "active_experts": len(self._active_expert_ids),
            "total_replicas": total_replicas,
            "healthy_replicas": healthy_replicas,
            "expert_pools": distribution,
        }

    def compute_placement_plan(
        self, available_nodes: list[dict]
    ) -> list[dict]:
        """
        Compute optimal expert placement across available nodes.

        Uses a greedy bin-packing algorithm:
        1. Sort experts by replica deficit (least replicated first)
        2. Sort nodes by available VRAM descending
        3. Place experts on nodes until VRAM is full

        Args:
            available_nodes: List of {node_id, gpu_model, vram_gb, current_experts}

        Returns:
            List of placement actions: {action, expert_id, node_id}
        """
        expert_size_mb = self.model_config["expert_size_mb"]
        expert_size_gb = expert_size_mb / 1024

        # Calculate replica deficit for each active expert
        deficits = []
        for eid in self._active_expert_ids:
            pool = self.expert_pools.get(eid, ExpertPool(eid))
            healthy = len(pool.healthy_replicas)
            # Target: at least 2 replicas per expert for redundancy
            target = 2
            deficit = target - healthy
            if deficit > 0:
                deficits.append((eid, deficit))

        deficits.sort(key=lambda x: x[1], reverse=True)

        # Sort nodes by available VRAM
        nodes_sorted = sorted(available_nodes, key=lambda n: n.get("vram_gb", 0), reverse=True)

        placements = []
        for expert_id, _ in deficits:
            for node in nodes_sorted:
                # Check if node has enough VRAM
                current_load = len(node.get("current_experts", []))
                available_vram = node["vram_gb"] - (current_load * expert_size_gb)

                if available_vram >= expert_size_gb:
                    placements.append({
                        "action": "place",
                        "expert_id": expert_id,
                        "node_id": node["node_id"],
                        "estimated_vram_gb": expert_size_gb,
                    })
                    node.setdefault("current_experts", []).append(expert_id)
                    break

        return placements

    def generate_vllm_config(self, cluster_nodes: list[dict]) -> dict:
        """
        Generate vLLM serving configuration for the current tier.

        Produces a config dict compatible with vLLM's distributed serving:
        - tensor_parallel_size
        - pipeline_parallel_size
        - expert_parallel_size (for MoE models)
        - gpu_memory_utilization
        """
        config = TIER_EXPERT_CONFIG[self._current_tier]
        total_gpus = len(cluster_nodes)

        if total_gpus == 0:
            return self._local_vllm_config()

        if total_gpus == 1:
            return self._local_vllm_config()

        total_vram = sum(n.get("vram_gb", 0) for n in cluster_nodes)
        model_vram_needed = self.model_config.get("hidden_size", 4096) * 2 / 1024  # rough estimate

        # For MoE models, prefer expert parallelism
        total_experts = self.model_config["total_experts"]
        if total_experts > 8 and total_gpus >= 2:
            # Expert parallel: distribute experts across GPUs
            ep_size = min(total_gpus, config["active_experts"])
            return {
                "model": self.model_name,
                "tensor_parallel_size": 1,
                "pipeline_parallel_size": 1,
                "expert_parallel_size": ep_size,
                "num_experts_per_gpu": max(1, config["active_experts"] // ep_size),
                "gpu_memory_utilization": 0.90,
                "max_model_len": self._context_for_tier(),
                "quantization": self._quant_for_tier(),
                "enable_chunked_prefill": True,
            }

        # For non-MoE or small expert count, use PP/TP
        if total_gpus <= 4:
            return {
                "model": self.model_name,
                "tensor_parallel_size": total_gpus,
                "pipeline_parallel_size": 1,
                "gpu_memory_utilization": 0.90,
                "max_model_len": self._context_for_tier(),
                "quantization": self._quant_for_tier(),
                "enable_chunked_prefill": True,
            }

        # Large cluster: TP within 4-GPU groups, PP across groups
        tp_size = min(4, total_gpus)
        pp_size = total_gpus // tp_size
        return {
            "model": self.model_name,
            "tensor_parallel_size": tp_size,
            "pipeline_parallel_size": pp_size,
            "gpu_memory_utilization": 0.90,
            "max_model_len": self._context_for_tier(),
            "quantization": self._quant_for_tier(),
            "enable_chunked_prefill": True,
        }

    def _local_vllm_config(self) -> dict:
        return {
            "model": self.model_name,
            "tensor_parallel_size": 1,
            "pipeline_parallel_size": 1,
            "gpu_memory_utilization": 0.90,
            "max_model_len": self._context_for_tier(),
            "quantization": self._quant_for_tier(),
            "enable_chunked_prefill": True,
        }

    def _context_for_tier(self) -> int:
        config = TIER_EXPERT_CONFIG[self._current_tier]
        return {Tier.BASE: 32768, Tier.ENHANCED: 65536, Tier.FULL: 131072}[self._current_tier]

    def _quant_for_tier(self) -> str:
        return {Tier.BASE: "awq", Tier.ENHANCED: "awq", Tier.FULL: "fp16"}[self._current_tier]
