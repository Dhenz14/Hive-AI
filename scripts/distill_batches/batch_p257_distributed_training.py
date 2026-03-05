"""Distributed training — data parallelism, model parallelism, FSDP, DeepSpeed."""

PAIRS = [
    (
        "ai/data-parallel-training",
        "Show distributed data parallel training: DDP setup, gradient synchronization, and multi-GPU training with PyTorch.",
        '''Distributed Data Parallel (DDP) training:

```python
import os
import torch
import torch.nn as nn
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler


def setup_distributed(rank: int, world_size: int):
    """Initialize distributed process group."""
    os.environ["MASTER_ADDR"] = "localhost"
    os.environ["MASTER_PORT"] = "12355"
    dist.init_process_group("nccl", rank=rank, world_size=world_size)
    torch.cuda.set_device(rank)


def cleanup():
    dist.destroy_process_group()


def train_ddp(rank: int, world_size: int, model_fn, dataset, epochs: int = 10):
    """Full DDP training loop."""
    setup_distributed(rank, world_size)

    # Create model on this GPU
    model = model_fn().to(rank)
    model = DDP(model, device_ids=[rank])

    # Distributed sampler ensures each GPU gets different data
    sampler = DistributedSampler(dataset, num_replicas=world_size, rank=rank, shuffle=True)
    loader = DataLoader(dataset, batch_size=32, sampler=sampler, num_workers=4, pin_memory=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler()  # For mixed precision

    for epoch in range(epochs):
        sampler.set_epoch(epoch)  # Important: ensures different shuffling each epoch
        model.train()

        for batch_idx, (inputs, targets) in enumerate(loader):
            inputs, targets = inputs.to(rank), targets.to(rank)

            with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
                outputs = model(inputs)
                loss = nn.functional.cross_entropy(outputs, targets)

            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            if rank == 0 and batch_idx % 100 == 0:
                print(f"Epoch {epoch}, Batch {batch_idx}, Loss: {loss.item():.4f}")

        # Save checkpoint (only on rank 0)
        if rank == 0:
            torch.save({
                "epoch": epoch,
                "model_state": model.module.state_dict(),
                "optimizer_state": optimizer.state_dict(),
            }, f"checkpoint_epoch{epoch}.pt")

    cleanup()


def launch_ddp(model_fn, dataset, world_size: int = None):
    """Launch DDP training across available GPUs."""
    import torch.multiprocessing as mp
    world_size = world_size or torch.cuda.device_count()
    mp.spawn(train_ddp, args=(world_size, model_fn, dataset), nprocs=world_size, join=True)
```

Key patterns:
1. **DDP wrapper** — wraps model for automatic gradient synchronization across GPUs
2. **DistributedSampler** — partitions dataset so each GPU processes different samples
3. **`set_epoch()`** — must be called each epoch for proper shuffling with DistributedSampler
4. **Rank 0 logging/saving** — only rank 0 prints and saves checkpoints to avoid duplicates
5. **`model.module`** — access underlying model through DDP wrapper for saving state dict'''
    ),
    (
        "ai/fsdp-training",
        "Show Fully Sharded Data Parallel (FSDP) for training large models that don't fit on a single GPU.",
        '''FSDP — shard model parameters across GPUs:

```python
import torch
import torch.nn as nn
from torch.distributed.fsdp import (
    FullyShardedDataParallel as FSDP,
    MixedPrecision,
    ShardingStrategy,
    CPUOffload,
)
from torch.distributed.fsdp.wrap import (
    transformer_auto_wrap_policy,
    size_based_auto_wrap_policy,
)
import functools


def setup_fsdp_model(model: nn.Module, transformer_layer_cls=None):
    """Configure FSDP for large model training.

    FSDP shards parameters, gradients, and optimizer states
    across GPUs. Each GPU only holds 1/N of the model.
    """
    # Mixed precision policy
    mp_policy = MixedPrecision(
        param_dtype=torch.bfloat16,    # Parameters in bf16
        reduce_dtype=torch.bfloat16,   # Gradient reduction in bf16
        buffer_dtype=torch.bfloat16,   # Buffers in bf16
    )

    # Auto-wrap policy: wrap each transformer layer separately
    if transformer_layer_cls:
        wrap_policy = functools.partial(
            transformer_auto_wrap_policy,
            transformer_layer_cls={transformer_layer_cls},
        )
    else:
        wrap_policy = functools.partial(
            size_based_auto_wrap_policy,
            min_num_params=1_000_000,  # Wrap modules with >1M params
        )

    # Wrap model with FSDP
    fsdp_model = FSDP(
        model,
        sharding_strategy=ShardingStrategy.FULL_SHARD,  # Shard everything
        mixed_precision=mp_policy,
        auto_wrap_policy=wrap_policy,
        device_id=torch.cuda.current_device(),
        use_orig_params=True,  # Required for torch.compile compatibility
    )

    return fsdp_model


def save_fsdp_checkpoint(model: FSDP, optimizer, path: str, rank: int):
    """Save FSDP checkpoint (full state dict on rank 0)."""
    from torch.distributed.fsdp import (
        FullStateDictConfig,
        StateDictType,
    )

    # Gather full state dict to rank 0
    save_policy = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)

    with FSDP.state_dict_type(model, StateDictType.FULL_STATE_DICT, save_policy):
        state_dict = model.state_dict()
        optim_state = FSDP.optim_state_dict(model, optimizer)

    if rank == 0:
        torch.save({
            "model": state_dict,
            "optimizer": optim_state,
        }, path)


def load_fsdp_checkpoint(model: FSDP, optimizer, path: str):
    """Load FSDP checkpoint."""
    from torch.distributed.fsdp import StateDictType

    checkpoint = torch.load(path, map_location="cpu")

    with FSDP.state_dict_type(model, StateDictType.FULL_STATE_DICT):
        model.load_state_dict(checkpoint["model"])
        optim_state = FSDP.optim_state_dict_to_load(
            model, optimizer, checkpoint["optimizer"]
        )
        optimizer.load_state_dict(optim_state)
```

Parallelism comparison:

| Strategy | Model fit | Communication | Memory per GPU |
|----------|----------|---------------|---------------|
| **DDP** | Must fit 1 GPU | Gradient all-reduce | Full model |
| **FSDP (full shard)** | N× larger | Param all-gather + grad reduce | 1/N model |
| **FSDP (hybrid)** | Large | Shard within node, replicate across | 1/local_N |
| **Pipeline parallel** | N× layers | Activations between stages | 1/N layers |
| **Tensor parallel** | N× width | All-reduce per layer | 1/N per layer |

Key patterns:
1. **Full sharding** — each GPU holds 1/N of params, gradients, and optimizer states
2. **Auto-wrap policy** — wrap each transformer layer as FSDP unit; granular sharding
3. **Mixed precision** — bf16 params with bf16 reduction; saves memory and bandwidth
4. **Checkpoint gathering** — collect full state dict to rank 0 for saving; shard on loading
5. **`use_orig_params`** — preserves original parameter structure; needed for torch.compile'''
    ),
    (
        "ai/deepspeed-training",
        "Show DeepSpeed ZeRO training: ZeRO stages, offloading, gradient accumulation, and configuration for large model training.",
        '''DeepSpeed ZeRO for large model training:

```python
import torch
import deepspeed
import json
from torch.utils.data import DataLoader


# === DeepSpeed Configuration ===

DEEPSPEED_CONFIG = {
    "train_batch_size": 256,
    "train_micro_batch_size_per_gpu": 4,  # = gradient_accumulation = 256 / (4 * n_gpus)

    "optimizer": {
        "type": "AdamW",
        "params": {
            "lr": 3e-4,
            "betas": [0.9, 0.95],
            "weight_decay": 0.1,
        },
    },

    "scheduler": {
        "type": "WarmupDecayLR",
        "params": {
            "warmup_min_lr": 0,
            "warmup_max_lr": 3e-4,
            "warmup_num_steps": 2000,
            "total_num_steps": 100000,
        },
    },

    "bf16": {"enabled": True},

    "zero_optimization": {
        "stage": 3,  # ZeRO Stage 3: shard params + gradients + optimizer

        "offload_optimizer": {
            "device": "cpu",  # Offload optimizer states to CPU
            "pin_memory": True,
        },
        "offload_param": {
            "device": "cpu",  # Offload parameters to CPU when not in use
            "pin_memory": True,
        },

        "overlap_comm": True,         # Overlap communication with computation
        "contiguous_gradients": True,
        "reduce_scatter": True,

        "stage3_gather_16bit_weights_on_model_save": True,
    },

    "gradient_clipping": 1.0,

    "activation_checkpointing": {
        "partition_activations": True,
        "cpu_checkpointing": True,
        "contiguous_memory_optimization": True,
    },

    "wall_clock_breakdown": True,
}


def train_with_deepspeed(model, train_dataset, config_path: str = "ds_config.json"):
    """Train model with DeepSpeed."""
    # Save config
    with open(config_path, "w") as f:
        json.dump(DEEPSPEED_CONFIG, f, indent=2)

    # Initialize DeepSpeed
    model_engine, optimizer, _, scheduler = deepspeed.initialize(
        model=model,
        config=config_path,
        model_parameters=model.parameters(),
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=model_engine.train_micro_batch_size_per_gpu(),
        shuffle=True,
        num_workers=4,
    )

    for epoch in range(3):
        for step, (inputs, targets) in enumerate(train_loader):
            inputs = inputs.to(model_engine.device)
            targets = targets.to(model_engine.device)

            outputs = model_engine(inputs)
            loss = torch.nn.functional.cross_entropy(outputs, targets)

            # DeepSpeed handles gradient accumulation, scaling, and sync
            model_engine.backward(loss)
            model_engine.step()

            if step % 100 == 0 and model_engine.local_rank == 0:
                print(f"Step {step}: Loss = {loss.item():.4f}")

        # Save checkpoint
        model_engine.save_checkpoint("checkpoints", tag=f"epoch_{epoch}")
```

ZeRO stages:

| Stage | Shards | Memory savings | Communication |
|-------|--------|---------------|---------------|
| **ZeRO-1** | Optimizer states | ~4x | Same as DDP |
| **ZeRO-2** | + Gradients | ~8x | +Reduce-scatter |
| **ZeRO-3** | + Parameters | ~N× | +All-gather params |
| **ZeRO-Infinity** | + CPU/NVMe offload | ~∞ | +CPU/disk IO |

Key patterns:
1. **ZeRO-3** — shard everything (params, gradients, optimizer) across GPUs; trains 10x larger models
2. **CPU offloading** — move optimizer states and params to CPU; trades compute for memory
3. **Gradient accumulation** — `train_batch_size / (micro_batch * n_gpus)` steps before sync
4. **Activation checkpointing** — recompute activations in backward pass; saves O(layers) memory
5. **Auto config** — `train_batch_size` and `micro_batch_size` control accumulation automatically'''
    ),
    (
        "ai/training-optimization",
        "Show training optimization techniques: gradient checkpointing, mixed precision, learning rate schedules, and warmup strategies.",
        '''Training optimization for deep learning:

```python
import torch
import torch.nn as nn
import math


# === Learning Rate Schedules ===

class CosineWithWarmup:
    """Cosine annealing with linear warmup (most common for LLMs)."""

    def __init__(self, optimizer, warmup_steps: int, total_steps: int,
                 min_lr_ratio: float = 0.1):
        self.optimizer = optimizer
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.min_lr_ratio = min_lr_ratio
        self.base_lrs = [pg["lr"] for pg in optimizer.param_groups]
        self.step_count = 0

    def step(self):
        self.step_count += 1
        for pg, base_lr in zip(self.optimizer.param_groups, self.base_lrs):
            if self.step_count < self.warmup_steps:
                # Linear warmup
                lr = base_lr * self.step_count / self.warmup_steps
            else:
                # Cosine decay
                progress = (self.step_count - self.warmup_steps) / (
                    self.total_steps - self.warmup_steps
                )
                lr = base_lr * (self.min_lr_ratio + (1 - self.min_lr_ratio) * (
                    1 + math.cos(math.pi * progress)
                ) / 2)
            pg["lr"] = lr


# === Gradient Checkpointing ===

class CheckpointedTransformerBlock(nn.Module):
    """Transformer block with gradient checkpointing.

    Trade compute for memory: don't store activations in forward pass,
    recompute them during backward pass.
    """

    def __init__(self, d_model: int, n_heads: int):
        super().__init__()
        self.attn_norm = nn.LayerNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.ffn_norm = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_model * 4),
            nn.GELU(),
            nn.Linear(d_model * 4, d_model),
        )
        self.use_checkpoint = True

    def _forward(self, x):
        h = self.attn_norm(x)
        h, _ = self.attn(h, h, h)
        x = x + h
        h = self.ffn_norm(x)
        h = self.ffn(h)
        return x + h

    def forward(self, x):
        if self.use_checkpoint and self.training:
            return torch.utils.checkpoint.checkpoint(
                self._forward, x, use_reentrant=False,
            )
        return self._forward(x)


# === Gradient Accumulation ===

class GradientAccumulator:
    """Accumulate gradients over multiple micro-batches."""

    def __init__(self, model, optimizer, accumulation_steps: int,
                 max_grad_norm: float = 1.0):
        self.model = model
        self.optimizer = optimizer
        self.accumulation_steps = accumulation_steps
        self.max_grad_norm = max_grad_norm
        self.step_count = 0

    def backward_step(self, loss):
        """Backward pass with accumulation."""
        scaled_loss = loss / self.accumulation_steps
        scaled_loss.backward()
        self.step_count += 1

        if self.step_count % self.accumulation_steps == 0:
            # Clip gradients
            nn.utils.clip_grad_norm_(
                self.model.parameters(), self.max_grad_norm
            )
            # Update weights
            self.optimizer.step()
            self.optimizer.zero_grad()
            return True  # Weight update happened
        return False


# === Weight Decay Groups ===

def create_optimizer_groups(model: nn.Module, lr: float,
                            weight_decay: float = 0.1):
    """Separate parameters into decay and no-decay groups.

    Don't apply weight decay to biases, LayerNorm, and embeddings.
    """
    decay_params = []
    no_decay_params = []

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if param.dim() <= 1 or "bias" in name or "norm" in name or "embed" in name:
            no_decay_params.append(param)
        else:
            decay_params.append(param)

    return torch.optim.AdamW([
        {"params": decay_params, "weight_decay": weight_decay},
        {"params": no_decay_params, "weight_decay": 0.0},
    ], lr=lr, betas=(0.9, 0.95))
```

Key patterns:
1. **Cosine warmup** — linear warmup then cosine decay; standard for LLM training
2. **Gradient checkpointing** — recompute activations in backward; trades 30% compute for 60% memory
3. **Gradient accumulation** — simulate larger batch sizes on limited GPU memory
4. **Weight decay groups** — skip decay for bias/norm/embed; only regularize weight matrices
5. **`use_reentrant=False`** — newer checkpoint API; handles non-deterministic operations correctly'''
    ),
]
"""
