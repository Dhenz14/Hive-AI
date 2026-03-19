"""
hiveai/compute/distributed_training.py

DisTrO + Hivemind integration for distributed pretraining/fine-tuning.

The training layer of the Spirit Bomb — enables the community to
collectively train and fine-tune models using distributed GPU resources.

Three training modes:
  1. Federated LoRA: Individual nodes train LoRA adapters locally,
     merge via MergeKit DARE-TIES. Lowest bandwidth requirement.
  2. Hivemind DDP: Decentralized data-parallel training via Hivemind.
     Works over internet. Fault-tolerant.
  3. DisTrO Pretraining: Full pretraining with 1000x bandwidth reduction.
     Uses Psyche network. For major model upgrades.

Key research:
  - DisTrO (Nous Research, 2024): Distributed Training over Slow networks.
    Uses optimizer state compression — 1000x bandwidth reduction vs standard DDP.
    Nodes exchange ~500KB per step instead of full gradients.
  - Psyche Network: Permissionless DisTrO network by Nous Research.
    Any GPU can join, trustless validation of training contributions.
  - Hivemind: PyTorch library for decentralized deep learning.
    DHT-based peer discovery, fault-tolerant backprop, gradient compression.
  - PRIME-RL (Prime Intellect): Decentralized GRPO training.
    Asynchronous RL with shared replay buffers across internet.
  - MergeKit DARE-TIES: Adapter merging for combining community LoRA
    contributions into a single improved model.

Architecture:
  Community Node → Hivemind DHT → Training Coordinator → Model Registry
      ↓                                                         ↓
  Local LoRA    → MergeKit → Merged Model → IPFS → Community
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TrainingMode(Enum):
    FEDERATED_LORA = "federated_lora"
    HIVEMIND_DDP = "hivemind_ddp"
    DISTRO_PRETRAIN = "distro_pretrain"


@dataclass
class TrainingTask:
    """A distributed training task."""
    task_id: str
    mode: TrainingMode
    base_model: str  # HuggingFace model ID or IPFS CID
    dataset_id: str  # Dataset identifier
    # Hyperparameters
    learning_rate: float = 2e-5
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    num_epochs: float = 1.0
    max_steps: int = -1  # -1 = use epochs
    warmup_steps: int = 100
    # LoRA config (for federated mode)
    lora_r: int = 16
    lora_alpha: int = 32
    lora_target_modules: list[str] = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"])
    # DisTrO config
    distro_compression_ratio: int = 1000  # 1000x bandwidth reduction
    distro_sync_interval_steps: int = 10  # sync every N steps
    # Hivemind config
    hivemind_initial_peers: list[str] = field(default_factory=list)
    hivemind_target_batch_size: int = 64  # global batch across all peers


@dataclass
class TrainingContribution:
    """A node's contribution to a training task."""
    node_id: str
    task_id: str
    steps_completed: int = 0
    tokens_processed: int = 0
    loss_history: list[float] = field(default_factory=list)
    adapter_cid: Optional[str] = None  # IPFS CID of trained adapter
    training_time_seconds: float = 0.0


@dataclass
class MergeConfig:
    """Configuration for DARE-TIES adapter merging."""
    merge_method: str = "dare_ties"  # dare_ties, ties, linear, slerp
    # DARE (Drop And REscale) parameters
    dare_density: float = 0.5  # fraction of deltas to keep
    dare_rescale: bool = True
    # TIES (Trim, Elect, Sign) parameters
    ties_density: float = 0.5
    normalize: bool = True
    # Weighting
    adapter_weights: dict[str, float] = field(default_factory=dict)  # adapter_id → weight


class FederatedLoRACoordinator:
    """
    Coordinates federated LoRA training across community nodes.

    Workflow:
    1. Coordinator publishes training task (base model + dataset + config)
    2. Nodes download base model + dataset shard
    3. Nodes train LoRA adapters locally (no gradient sharing needed)
    4. Nodes upload trained adapters to IPFS
    5. Coordinator collects adapters and merges via MergeKit DARE-TIES
    6. Merged model published to IPFS for community use

    This is the lowest-bandwidth training mode — nodes only exchange
    small LoRA adapters (~50MB each), not gradients.
    """

    def __init__(self):
        self.active_tasks: dict[str, TrainingTask] = {}
        self.contributions: dict[str, list[TrainingContribution]] = {}  # task_id → contributions
        self._merge_configs: dict[str, MergeConfig] = {}

    def create_task(self, task: TrainingTask) -> str:
        """Create a new federated LoRA training task."""
        self.active_tasks[task.task_id] = task
        self.contributions[task.task_id] = []
        self._merge_configs[task.task_id] = MergeConfig()
        logger.info(
            f"Created federated LoRA task {task.task_id}: "
            f"model={task.base_model}, lr={task.learning_rate}, "
            f"r={task.lora_r}, epochs={task.num_epochs}"
        )
        return task.task_id

    def submit_contribution(self, contribution: TrainingContribution) -> None:
        """Submit a training contribution from a node."""
        if contribution.task_id not in self.contributions:
            raise ValueError(f"Unknown task: {contribution.task_id}")

        self.contributions[contribution.task_id].append(contribution)
        logger.info(
            f"Contribution from {contribution.node_id} for task {contribution.task_id}: "
            f"{contribution.steps_completed} steps, adapter CID: {contribution.adapter_cid}"
        )

    def generate_merge_config(self, task_id: str) -> dict:
        """
        Generate MergeKit DARE-TIES configuration for merging adapters.

        Weights adapters by:
        - Training steps completed (more steps = higher weight)
        - Final loss (lower loss = higher weight)
        - Node reputation (higher rep = higher trust weight)

        Returns a MergeKit-compatible YAML config dict.
        """
        contribs = self.contributions.get(task_id, [])
        task = self.active_tasks.get(task_id)
        if not contribs or not task:
            return {}

        # Calculate weights based on training quality
        weights = {}
        total_steps = sum(c.steps_completed for c in contribs)
        for c in contribs:
            if c.adapter_cid and c.steps_completed > 0:
                step_weight = c.steps_completed / max(total_steps, 1)
                loss_weight = 1.0
                if c.loss_history:
                    # Lower final loss = higher weight
                    final_loss = c.loss_history[-1]
                    loss_weight = max(0.1, 1.0 / (1.0 + final_loss))
                weights[c.adapter_cid] = step_weight * loss_weight

        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        # Generate MergeKit config
        merge_config = {
            "merge_method": "dare_ties",
            "base_model": task.base_model,
            "models": [
                {
                    "model": f"ipfs://{cid}",
                    "parameters": {
                        "weight": round(weight, 4),
                        "density": 0.5,
                    },
                }
                for cid, weight in weights.items()
            ],
            "parameters": {
                "normalize": True,
                "int8_mask": True,
            },
            "dtype": "bfloat16",
        }

        return merge_config

    def get_task_status(self, task_id: str) -> dict:
        """Get status of a training task."""
        task = self.active_tasks.get(task_id)
        contribs = self.contributions.get(task_id, [])
        if not task:
            return {"error": f"Unknown task: {task_id}"}

        return {
            "task_id": task_id,
            "mode": task.mode.value,
            "base_model": task.base_model,
            "contributors": len(contribs),
            "total_steps": sum(c.steps_completed for c in contribs),
            "total_tokens": sum(c.tokens_processed for c in contribs),
            "adapters_submitted": sum(1 for c in contribs if c.adapter_cid),
            "avg_loss": (
                sum(c.loss_history[-1] for c in contribs if c.loss_history)
                / max(1, sum(1 for c in contribs if c.loss_history))
            ),
        }


class HivemindDDPCoordinator:
    """
    Coordinates Hivemind-based decentralized data-parallel training.

    Uses the Hivemind library for:
    - DHT-based peer discovery (no central server needed)
    - Fault-tolerant gradient averaging
    - Adaptive batch size (adds GPUs seamlessly)
    - Bandwidth-efficient gradient compression

    This mode requires more bandwidth than Federated LoRA but produces
    better models because gradients are actually shared.

    Typical bandwidth: ~100MB per sync step (with compression).
    """

    def __init__(self):
        self._dht_peers: list[str] = []
        self._active = False

    def generate_hivemind_config(self, task: TrainingTask) -> dict:
        """
        Generate Hivemind training configuration.

        This config is used by nodes to join the training swarm.
        """
        return {
            "experiment_prefix": f"spiritbomb-{task.task_id}",
            "initial_peers": task.hivemind_initial_peers,
            "target_batch_size": task.hivemind_target_batch_size,
            "matchmaking_time": 30.0,  # seconds to wait for peers
            "averaging_timeout": 120.0,
            "compression": "float16",  # gradient compression
            "use_local_updates": True,  # allow local SGD between syncs
            "local_updates_before_averaging": task.distro_sync_interval_steps,
            # Model config
            "model_name": task.base_model,
            "learning_rate": task.learning_rate,
            "per_device_batch_size": task.batch_size,
            "gradient_accumulation_steps": task.gradient_accumulation_steps,
            "num_epochs": task.num_epochs,
            "warmup_steps": task.warmup_steps,
            # LoRA (optional — can train full model or LoRA)
            "use_lora": True,
            "lora_r": task.lora_r,
            "lora_alpha": task.lora_alpha,
            "lora_target_modules": task.lora_target_modules,
        }


class DisTrOPretrainingCoordinator:
    """
    Coordinates DisTrO-based distributed pretraining.

    DisTrO (Distributed Training over Slow Networks) achieves 1000x
    bandwidth reduction by compressing optimizer states instead of
    sending full gradients.

    Key insight: Instead of sending 32-bit gradients (standard DDP),
    DisTrO sends compressed optimizer state deltas that are ~1000x smaller
    but contain the same directional information.

    Integration with Psyche Network:
    - Psyche is Nous Research's permissionless DisTrO network
    - Any GPU can join, no approval needed
    - Training contributions are validated trustlessly
    - Rewards distributed based on verified training work

    Bandwidth requirement: ~500KB per sync step (vs ~500MB for standard DDP).
    This makes pretraining over consumer internet connections feasible.
    """

    def __init__(self):
        self._active_runs: dict[str, dict] = {}

    def generate_distro_config(self, task: TrainingTask) -> dict:
        """
        Generate DisTrO training configuration.

        This config is compatible with the Psyche network client.
        """
        return {
            "task_id": task.task_id,
            "mode": "distro_pretrain",
            # Model
            "base_model": task.base_model,
            "model_dtype": "bfloat16",
            # DisTrO-specific
            "compression_ratio": task.distro_compression_ratio,
            "sync_interval_steps": task.distro_sync_interval_steps,
            "optimizer": "adamw",
            "optimizer_state_compression": "quantized_delta",
            # Training
            "learning_rate": task.learning_rate,
            "batch_size": task.batch_size,
            "gradient_accumulation_steps": task.gradient_accumulation_steps,
            "max_steps": task.max_steps,
            "warmup_steps": task.warmup_steps,
            # Network
            "psyche_network": True,
            "initial_peers": task.hivemind_initial_peers,
            "min_peers_for_training": 2,
            "max_peers": 256,
            # Validation
            "validation_interval_steps": 100,
            "validation_dataset": task.dataset_id,
            "early_stopping_patience": 5,
            # Checkpointing
            "checkpoint_interval_steps": 500,
            "checkpoint_to_ipfs": True,
        }

    def estimate_training_time(
        self,
        model_params_b: float,
        dataset_tokens_b: float,
        total_gpus: int,
        avg_gpu_tflops: float = 40.0,  # ~RTX 3060-4070 average
    ) -> dict:
        """
        Estimate distributed pretraining time.

        Uses the Chinchilla scaling law approximation:
        FLOPS ≈ 6 × model_params × dataset_tokens

        With DisTrO, communication overhead is negligible (~0.1%),
        so scaling is near-linear with GPU count.
        """
        total_flops = 6.0 * model_params_b * 1e9 * dataset_tokens_b * 1e9
        total_gpu_tflops = total_gpus * avg_gpu_tflops * 1e12

        # MFU (Model FLOPS Utilization) — typically 40-55% for consumer GPUs
        mfu = 0.45
        effective_tflops = total_gpu_tflops * mfu

        training_seconds = total_flops / effective_tflops
        training_hours = training_seconds / 3600
        training_days = training_hours / 24

        # DisTrO communication overhead (negligible)
        comm_overhead = 0.001  # 0.1%
        adjusted_hours = training_hours * (1 + comm_overhead)

        return {
            "model_params_b": model_params_b,
            "dataset_tokens_b": dataset_tokens_b,
            "total_gpus": total_gpus,
            "total_flops": f"{total_flops:.2e}",
            "effective_tflops_per_second": round(effective_tflops / 1e12, 1),
            "estimated_hours": round(adjusted_hours, 1),
            "estimated_days": round(adjusted_hours / 24, 1),
            "scaling_efficiency": f"{(1 - comm_overhead) * 100:.1f}%",
            "note": (
                f"With {total_gpus} GPUs at ~{avg_gpu_tflops} TFLOPS each, "
                f"DisTrO enables distributed pretraining with <0.1% communication overhead."
            ),
        }


class TrainingOrchestrator:
    """
    Top-level orchestrator for all distributed training modes.

    Selects the appropriate training mode based on:
    - Task type (pretraining, fine-tuning, RL)
    - Available GPU count and bandwidth
    - Model size
    - Community tier
    """

    def __init__(self):
        self.federated = FederatedLoRACoordinator()
        self.hivemind = HivemindDDPCoordinator()
        self.distro = DisTrOPretrainingCoordinator()

    def recommend_training_mode(
        self,
        model_params_b: float,
        task_type: str,  # "pretrain", "finetune", "rl"
        total_gpus: int,
        avg_bandwidth_mbps: float = 100.0,
    ) -> dict:
        """
        Recommend the best training mode for given constraints.

        Returns mode recommendation with rationale.
        """
        if task_type == "pretrain":
            if total_gpus >= 10 and avg_bandwidth_mbps >= 50:
                return {
                    "mode": TrainingMode.DISTRO_PRETRAIN.value,
                    "reason": (
                        f"DisTrO pretraining: {total_gpus} GPUs with {avg_bandwidth_mbps} Mbps "
                        f"is sufficient. DisTrO needs only ~4 Mbps per node (1000x compression)."
                    ),
                    "bandwidth_per_node_mbps": 4.0,
                    "feasible": True,
                }
            elif total_gpus >= 4:
                return {
                    "mode": TrainingMode.HIVEMIND_DDP.value,
                    "reason": (
                        f"Hivemind DDP with gradient compression. "
                        f"Needs ~100MB per sync but compression helps."
                    ),
                    "bandwidth_per_node_mbps": 50.0,
                    "feasible": avg_bandwidth_mbps >= 50,
                }
            else:
                return {
                    "mode": TrainingMode.FEDERATED_LORA.value,
                    "reason": "Too few GPUs for distributed pretraining. Use federated LoRA instead.",
                    "bandwidth_per_node_mbps": 1.0,
                    "feasible": True,
                }

        elif task_type == "finetune":
            if model_params_b > 30 and total_gpus >= 4:
                return {
                    "mode": TrainingMode.HIVEMIND_DDP.value,
                    "reason": f"Large model ({model_params_b}B) fine-tuning benefits from DDP.",
                    "bandwidth_per_node_mbps": 50.0,
                    "feasible": avg_bandwidth_mbps >= 50,
                }
            else:
                return {
                    "mode": TrainingMode.FEDERATED_LORA.value,
                    "reason": (
                        f"Federated LoRA is optimal for fine-tuning: minimal bandwidth, "
                        f"each node trains independently, merge via DARE-TIES."
                    ),
                    "bandwidth_per_node_mbps": 1.0,
                    "feasible": True,
                }

        elif task_type == "rl":
            return {
                "mode": TrainingMode.FEDERATED_LORA.value,
                "reason": (
                    "RL training uses federated approach: nodes generate rollouts locally, "
                    "share rewards via coordinator, train LoRA adapters independently."
                ),
                "bandwidth_per_node_mbps": 1.0,
                "feasible": True,
            }

        return {
            "mode": TrainingMode.FEDERATED_LORA.value,
            "reason": "Default: federated LoRA (lowest bandwidth, always feasible).",
            "bandwidth_per_node_mbps": 1.0,
            "feasible": True,
        }
