"""Continual and online learning — avoiding catastrophic forgetting."""

PAIRS = [
    (
        "ai/continual-learning",
        "Show continual learning patterns: EWC, progressive networks, replay buffers, and adapter-based approaches for avoiding catastrophic forgetting.",
        '''Continual learning — training on new tasks without forgetting:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import copy
from collections import defaultdict


# === Elastic Weight Consolidation (EWC) ===

class EWC:
    """Elastic Weight Consolidation: penalize changes to important weights.

    Key idea: estimate how important each weight is for previous tasks
    using the Fisher Information Matrix. Penalize large changes to
    important weights when learning new tasks.
    """

    def __init__(self, model: nn.Module, lambda_ewc: float = 1000.0):
        self.model = model
        self.lambda_ewc = lambda_ewc
        self.fisher: dict[str, torch.Tensor] = {}
        self.old_params: dict[str, torch.Tensor] = {}

    def compute_fisher(self, dataloader: DataLoader, num_samples: int = 200):
        """Estimate Fisher Information Matrix from task data.

        Fisher diagonal approximation: F_ii = E[(d log p(y|x;θ) / dθ_i)²]
        In practice: accumulate squared gradients over data.
        """
        self.model.eval()
        fisher = {n: torch.zeros_like(p) for n, p in self.model.named_parameters() if p.requires_grad}

        for i, (inputs, targets) in enumerate(dataloader):
            if i >= num_samples:
                break

            self.model.zero_grad()
            outputs = self.model(inputs.cuda())
            loss = F.cross_entropy(outputs, targets.cuda())
            loss.backward()

            for name, param in self.model.named_parameters():
                if param.requires_grad and param.grad is not None:
                    fisher[name] += param.grad.data.pow(2)

        # Average and store
        for name in fisher:
            fisher[name] /= min(num_samples, len(dataloader))

        self.fisher = fisher
        self.old_params = {n: p.data.clone() for n, p in self.model.named_parameters() if p.requires_grad}

    def penalty(self) -> torch.Tensor:
        """EWC penalty: sum of Fisher-weighted parameter changes."""
        loss = torch.tensor(0.0, device=next(self.model.parameters()).device)
        for name, param in self.model.named_parameters():
            if name in self.fisher:
                loss += (self.fisher[name] * (param - self.old_params[name]).pow(2)).sum()
        return self.lambda_ewc * loss


# === Experience Replay ===

class ReplayBuffer:
    """Store examples from previous tasks for rehearsal.

    When learning task N, mix in examples from tasks 1..N-1
    to prevent forgetting.
    """

    def __init__(self, max_size: int = 5000, strategy: str = "reservoir"):
        self.max_size = max_size
        self.strategy = strategy
        self.buffer: list[tuple] = []
        self.seen = 0

    def add(self, examples: list[tuple]):
        """Add examples using reservoir sampling (uniform over all seen)."""
        for example in examples:
            self.seen += 1
            if len(self.buffer) < self.max_size:
                self.buffer.append(example)
            else:
                # Reservoir sampling: replace with probability max_size/seen
                idx = torch.randint(0, self.seen, (1,)).item()
                if idx < self.max_size:
                    self.buffer[idx] = example

    def sample(self, batch_size: int) -> list[tuple]:
        """Sample a batch from the replay buffer."""
        indices = torch.randint(0, len(self.buffer), (min(batch_size, len(self.buffer)),))
        return [self.buffer[i] for i in indices]


class ReplayTrainer:
    """Train with experience replay from previous tasks."""

    def __init__(self, model: nn.Module, buffer_size: int = 5000, replay_ratio: float = 0.3):
        self.model = model
        self.buffer = ReplayBuffer(buffer_size)
        self.replay_ratio = replay_ratio

    def train_task(self, dataloader: DataLoader, epochs: int = 5, lr: float = 1e-3):
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        for epoch in range(epochs):
            for inputs, targets in dataloader:
                inputs, targets = inputs.cuda(), targets.cuda()

                # Mix in replay examples
                if len(self.buffer.buffer) > 0:
                    replay_batch = self.buffer.sample(
                        int(inputs.shape[0] * self.replay_ratio)
                    )
                    if replay_batch:
                        replay_inputs = torch.stack([r[0] for r in replay_batch]).cuda()
                        replay_targets = torch.tensor([r[1] for r in replay_batch]).cuda()
                        inputs = torch.cat([inputs, replay_inputs])
                        targets = torch.cat([targets, replay_targets])

                outputs = self.model(inputs)
                loss = F.cross_entropy(outputs, targets)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            # Store examples from current task
            for inputs, targets in dataloader:
                examples = [(inputs[i], targets[i].item()) for i in range(inputs.shape[0])]
                self.buffer.add(examples)
                break  # Just one batch per epoch


# === Progressive Networks (no forgetting by design) ===

class ProgressiveColumn(nn.Module):
    """A single column in a progressive network."""

    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.layers = nn.ModuleList([
            nn.Linear(input_dim, hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Linear(hidden_dim, output_dim),
        ])

    def forward(self, x: torch.Tensor, lateral_inputs: list[list[torch.Tensor]] | None = None) -> list[torch.Tensor]:
        activations = []
        for i, layer in enumerate(self.layers):
            if lateral_inputs and i > 0:
                # Add lateral connections from previous columns
                lateral_sum = sum(lat[i-1] for lat in lateral_inputs if len(lat) > i-1)
                x = F.relu(layer(x) + lateral_sum)
            else:
                x = F.relu(layer(x))
            activations.append(x)
        return activations


class ProgressiveNetwork(nn.Module):
    """Progressive Networks: add new column per task, freeze old ones.

    No forgetting: previous columns are frozen.
    Transfer: lateral connections from old to new columns.
    Downside: model grows linearly with number of tasks.
    """

    def __init__(self, input_dim: int, hidden_dim: int, output_dims: list[int]):
        super().__init__()
        self.columns: nn.ModuleList = nn.ModuleList()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim

    def add_task(self, output_dim: int):
        """Add a new column for a new task."""
        # Freeze all existing columns
        for col in self.columns:
            for param in col.parameters():
                param.requires_grad = False

        new_column = ProgressiveColumn(self.input_dim, self.hidden_dim, output_dim)
        self.columns.append(new_column)

    def forward(self, x: torch.Tensor, task_id: int) -> torch.Tensor:
        all_activations = []
        for i, col in enumerate(self.columns):
            lateral = all_activations if i > 0 else None
            activations = col(x, lateral)
            all_activations.append(activations)

        return all_activations[task_id][-1]  # Output of the task's column


# === Adapter-based Continual Learning ===

class TaskAdapter(nn.Module):
    """Lightweight adapter per task (like LoRA for continual learning)."""

    def __init__(self, hidden_dim: int, adapter_dim: int = 64):
        super().__init__()
        self.down = nn.Linear(hidden_dim, adapter_dim)
        self.up = nn.Linear(adapter_dim, hidden_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.up(F.relu(self.down(x)))


class AdapterContinualModel(nn.Module):
    """Shared backbone + per-task adapters.

    Backbone is frozen after initial training.
    Each new task gets a lightweight adapter (~2% of backbone params).
    """

    def __init__(self, backbone: nn.Module, hidden_dim: int, adapter_dim: int = 64):
        super().__init__()
        self.backbone = backbone
        self.adapters: nn.ModuleDict = nn.ModuleDict()
        self.heads: nn.ModuleDict = nn.ModuleDict()
        self.hidden_dim = hidden_dim
        self.adapter_dim = adapter_dim

    def add_task(self, task_name: str, num_classes: int):
        self.adapters[task_name] = TaskAdapter(self.hidden_dim, self.adapter_dim)
        self.heads[task_name] = nn.Linear(self.hidden_dim, num_classes)

    def forward(self, x: torch.Tensor, task_name: str) -> torch.Tensor:
        with torch.no_grad():
            features = self.backbone(x)
        adapted = self.adapters[task_name](features)
        return self.heads[task_name](adapted)
```

Continual learning comparison:

| Method | Forgetting | Model growth | Compute | Transfer |
|--------|-----------|-------------|---------|----------|
| **EWC** | Low (regularized) | Fixed | +Fisher compute | Implicit |
| **Replay** | Low (rehearsal) | Fixed + buffer | +Replay batch | Through data |
| **Progressive** | Zero (frozen) | Linear in tasks | Base | Lateral connections |
| **Adapters** | Zero (frozen backbone) | ~2% per task | Low | Shared backbone |
| **Naive fine-tuning** | Catastrophic | Fixed | Base | None |

Key patterns:
1. **EWC penalty** — Fisher Information identifies important weights; penalty prevents large changes to them
2. **Reservoir sampling** — uniformly sample from all seen examples into fixed-size buffer
3. **Progressive columns** — freeze old, add new column per task; lateral connections enable transfer
4. **Task adapters** — lightweight per-task modules on frozen backbone; scales to many tasks efficiently
5. **Replay ratio** — mix 30% old data with current task data; prevents forgetting while learning new'''
    ),
    (
        "ai/model-pruning",
        "Show model pruning and compression: magnitude pruning, structured pruning, knowledge editing, and lottery ticket hypothesis.",
        '''Model pruning and compression:

```python
import torch
import torch.nn as nn
import torch.nn.utils.prune as prune
from torch.nn.utils.prune import BasePruningMethod


# === Magnitude Pruning (unstructured) ===

def magnitude_prune(model: nn.Module, sparsity: float = 0.5):
    """Remove weights with smallest magnitude.

    After pruning 50%, the model has 50% zeros in weight matrices.
    Requires sparse compute support for actual speedup.
    """
    for name, module in model.named_modules():
        if isinstance(module, (nn.Linear, nn.Conv2d)):
            prune.l1_unstructured(module, name="weight", amount=sparsity)
            # Make pruning permanent (remove mask, zero out weights)
            prune.remove(module, "weight")

    # Count remaining parameters
    total = sum(p.numel() for p in model.parameters())
    nonzero = sum((p != 0).sum().item() for p in model.parameters())
    print(f"Sparsity: {1 - nonzero/total:.1%} ({nonzero}/{total} params)")


# === Structured Pruning (remove entire neurons/channels) ===

def structured_prune_linear(module: nn.Linear, prune_ratio: float = 0.3) -> nn.Linear:
    """Remove least important output neurons entirely.

    Unlike unstructured pruning, this actually reduces model dimensions
    and gives real speedup without sparse compute.
    """
    weight = module.weight.data
    bias = module.bias.data if module.bias is not None else None

    # Importance score: L2 norm of each output neuron's weights
    importance = weight.norm(dim=1)  # [out_features]

    # Keep top (1-prune_ratio) neurons
    num_keep = int(weight.shape[0] * (1 - prune_ratio))
    _, keep_indices = importance.topk(num_keep)
    keep_indices = keep_indices.sort().values

    # Create smaller linear layer
    new_linear = nn.Linear(weight.shape[1], num_keep, bias=bias is not None)
    new_linear.weight.data = weight[keep_indices]
    if bias is not None:
        new_linear.bias.data = bias[keep_indices]

    return new_linear


# === Iterative Magnitude Pruning (IMP / Lottery Ticket) ===

class LotteryTicketPruner:
    """Find winning lottery tickets via iterative magnitude pruning.

    Lottery Ticket Hypothesis: dense networks contain sparse subnetworks
    (winning tickets) that can train to the same accuracy from their
    original initialization.

    Algorithm:
    1. Train dense model to convergence
    2. Prune smallest 20% of weights
    3. Reset remaining weights to their INITIAL values
    4. Retrain the sparse network
    5. Repeat from step 2
    """

    def __init__(self, model: nn.Module, prune_rate: float = 0.2):
        self.prune_rate = prune_rate
        # Save initial weights (the "ticket")
        self.initial_state = {
            name: param.data.clone()
            for name, param in model.named_parameters()
        }
        self.masks: dict[str, torch.Tensor] = {
            name: torch.ones_like(param)
            for name, param in model.named_parameters()
        }

    def prune_and_reset(self, model: nn.Module):
        """Prune smallest weights and reset to initial values."""
        # Global magnitude pruning
        all_weights = []
        for name, param in model.named_parameters():
            if "weight" in name:
                masked = param.data.abs() * self.masks[name]
                all_weights.append(masked[masked > 0])

        all_magnitudes = torch.cat(all_weights)
        threshold = torch.quantile(all_magnitudes, self.prune_rate)

        # Update masks
        for name, param in model.named_parameters():
            if "weight" in name:
                new_mask = (param.data.abs() > threshold).float()
                self.masks[name] *= new_mask

        # Reset to initial weights with mask applied
        for name, param in model.named_parameters():
            if name in self.initial_state:
                param.data = self.initial_state[name] * self.masks[name]

        total_params = sum(m.numel() for m in self.masks.values())
        remaining = sum(m.sum().item() for m in self.masks.values())
        print(f"Remaining: {remaining/total_params:.1%}")

    def apply_masks(self, model: nn.Module):
        """Apply masks during forward pass (hook-based)."""
        def mask_hook(name):
            def hook(module, inputs):
                if hasattr(module, "weight"):
                    module.weight.data *= self.masks.get(name + ".weight",
                                                         torch.ones_like(module.weight))
            return hook

        for name, module in model.named_modules():
            if isinstance(module, (nn.Linear, nn.Conv2d)):
                module.register_forward_pre_hook(mask_hook(name))


# === Width Multiplier (simple structured pruning) ===

def create_slim_model(original: nn.Module, width_multiplier: float = 0.5) -> nn.Module:
    """Create a narrower version of the model.

    Width multiplier reduces hidden dimensions uniformly.
    Common in mobile models (MobileNet 0.5x, 0.75x, 1.0x).
    """
    import copy
    slim = copy.deepcopy(original)

    for name, module in slim.named_modules():
        if isinstance(module, nn.Linear):
            in_feat = int(module.in_features * width_multiplier)
            out_feat = int(module.out_features * width_multiplier)
            new_module = nn.Linear(in_feat, out_feat, bias=module.bias is not None)
            # Initialize from original weights (sliced)
            new_module.weight.data = module.weight.data[:out_feat, :in_feat]
            if module.bias is not None:
                new_module.bias.data = module.bias.data[:out_feat]
            # Replace module (requires parent access)

    return slim
```

Pruning comparison:

| Method | Speedup type | Accuracy loss | Sparsity achievable |
|--------|-------------|--------------|-------------------|
| **Magnitude (unstructured)** | Needs sparse HW | Low at 50-80% | 90%+ |
| **Structured (neurons)** | Real speedup | Moderate | 30-50% |
| **Lottery Ticket (IMP)** | Needs sparse HW | Minimal | 80-95% |
| **Width multiplier** | Real speedup | Moderate | 25-75% |
| **Distillation** | Real speedup | Low | N/A (smaller model) |

Key patterns:
1. **Magnitude pruning** — remove weights closest to zero; simple but needs sparse compute for speedup
2. **Structured pruning** — remove entire neurons/channels; gives real speedup on standard hardware
3. **Lottery ticket** — iterative prune → reset to init → retrain finds sparse subnetworks matching dense accuracy
4. **Global vs layer-wise** — global pruning (single threshold) outperforms uniform per-layer pruning
5. **Width multiplier** — scale all hidden dimensions by 0.5x-0.75x for predictable compute reduction'''
    ),
]
"""
