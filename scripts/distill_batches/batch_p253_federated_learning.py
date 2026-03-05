"""Federated learning and privacy-preserving ML — FedAvg, differential privacy, secure aggregation."""

PAIRS = [
    (
        "ai/federated-learning",
        "Show federated learning implementation: FedAvg algorithm, client-server architecture, non-IID data handling, and communication efficiency.",
        '''Federated learning — train on distributed private data:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
import copy
import numpy as np
from dataclasses import dataclass


@dataclass
class FedConfig:
    n_clients: int = 10
    rounds: int = 100
    local_epochs: int = 5
    local_lr: float = 0.01
    client_fraction: float = 0.3  # Fraction of clients per round
    batch_size: int = 32


class FedAvgServer:
    """FedAvg server: coordinate federated training.

    1. Send global model to selected clients
    2. Clients train locally on their private data
    3. Server aggregates client updates (weighted average)
    4. Repeat
    """

    def __init__(self, model: nn.Module, config: FedConfig):
        self.global_model = model
        self.config = config

    def select_clients(self, n_clients: int) -> list[int]:
        """Randomly select subset of clients for this round."""
        n_selected = max(1, int(n_clients * self.config.client_fraction))
        return np.random.choice(n_clients, n_selected, replace=False).tolist()

    def aggregate(self, client_models: list[nn.Module], client_sizes: list[int]):
        """FedAvg: weighted average of client model parameters."""
        total_size = sum(client_sizes)
        global_dict = self.global_model.state_dict()

        for key in global_dict:
            global_dict[key] = sum(
                client.state_dict()[key].float() * (size / total_size)
                for client, size in zip(client_models, client_sizes)
            )

        self.global_model.load_state_dict(global_dict)

    def train_round(self, clients: list) -> dict:
        """One round of federated training."""
        selected = self.select_clients(len(clients))

        client_models = []
        client_sizes = []
        client_losses = []

        for idx in selected:
            client = clients[idx]
            # Send global model to client
            local_model = copy.deepcopy(self.global_model)
            # Client trains locally
            loss = client.train(local_model, self.config)
            client_models.append(local_model)
            client_sizes.append(len(client.dataset))
            client_losses.append(loss)

        # Aggregate
        self.aggregate(client_models, client_sizes)

        return {
            "n_clients": len(selected),
            "avg_loss": np.mean(client_losses),
        }


class FedClient:
    """Federated learning client with local training."""

    def __init__(self, dataset, client_id: int):
        self.dataset = dataset
        self.client_id = client_id

    def train(self, model: nn.Module, config: FedConfig) -> float:
        """Train model locally on private data."""
        model.train()
        loader = DataLoader(self.dataset, batch_size=config.batch_size, shuffle=True)
        optimizer = torch.optim.SGD(model.parameters(), lr=config.local_lr, momentum=0.9)

        total_loss = 0
        for epoch in range(config.local_epochs):
            for inputs, targets in loader:
                outputs = model(inputs)
                loss = F.cross_entropy(outputs, targets)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        return total_loss / (config.local_epochs * len(loader))


class FedProxClient(FedClient):
    """FedProx: add proximal term to handle heterogeneous data.

    Penalizes local model from drifting too far from global model.
    Better than FedAvg for non-IID data distributions.
    """

    def train(self, model: nn.Module, config: FedConfig, mu: float = 0.01) -> float:
        model.train()
        global_params = {n: p.clone().detach() for n, p in model.named_parameters()}
        loader = DataLoader(self.dataset, batch_size=config.batch_size, shuffle=True)
        optimizer = torch.optim.SGD(model.parameters(), lr=config.local_lr)

        total_loss = 0
        for epoch in range(config.local_epochs):
            for inputs, targets in loader:
                outputs = model(inputs)
                loss = F.cross_entropy(outputs, targets)

                # Proximal term: ||w - w_global||²
                prox_term = sum(
                    ((p - global_params[n]) ** 2).sum()
                    for n, p in model.named_parameters()
                )
                loss += (mu / 2) * prox_term

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        return total_loss / (config.local_epochs * len(loader))
```

Federated learning comparison:

| Method | Non-IID handling | Communication | Convergence |
|--------|-----------------|---------------|-------------|
| **FedAvg** | Poor | Low (1 model/round) | Fast on IID |
| **FedProx** | Good (proximal term) | Low | Good |
| **SCAFFOLD** | Best (variance reduction) | Medium (2x) | Fast |
| **FedBN** | Good (local batch norm) | Low | Good |

Key patterns:
1. **FedAvg aggregation** — weighted average of client models by dataset size
2. **Client selection** — randomly sample subset of clients each round (communication efficiency)
3. **FedProx** — proximal term prevents client drift on non-IID data
4. **Local epochs** — multiple local SGD steps before aggregation (communication-efficient)
5. **Non-IID challenge** — clients have different data distributions; standard FedAvg struggles'''
    ),
    (
        "ai/differential-privacy",
        "Show differential privacy for ML: DP-SGD, noise calibration, privacy budgets (epsilon), and private model training.",
        '''Differential privacy in machine learning:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import numpy as np
from dataclasses import dataclass


@dataclass
class DPConfig:
    epsilon: float = 8.0       # Total privacy budget
    delta: float = 1e-5        # Failure probability
    max_grad_norm: float = 1.0  # Per-sample gradient clipping
    noise_multiplier: float = 1.1  # Noise scale
    batch_size: int = 256
    epochs: int = 10


class DPSGDOptimizer:
    """DP-SGD: Differentially Private Stochastic Gradient Descent.

    Two key modifications to standard SGD:
    1. Clip per-sample gradients to bound sensitivity
    2. Add calibrated Gaussian noise to aggregated gradients
    """

    def __init__(self, model: nn.Module, config: DPConfig, lr: float = 0.01):
        self.model = model
        self.config = config
        self.lr = lr

    def step(self, loss_per_sample: torch.Tensor):
        """One DP-SGD step with per-sample gradient clipping and noise."""
        batch_size = loss_per_sample.shape[0]

        # Step 1: Compute per-sample gradients
        per_sample_grads = self._compute_per_sample_grads(loss_per_sample)

        # Step 2: Clip per-sample gradients
        clipped_grads = self._clip_gradients(per_sample_grads)

        # Step 3: Aggregate and add noise
        noisy_grads = self._add_noise(clipped_grads, batch_size)

        # Step 4: Update parameters
        with torch.no_grad():
            for name, param in self.model.named_parameters():
                if name in noisy_grads:
                    param -= self.lr * noisy_grads[name]

    def _compute_per_sample_grads(self, loss_per_sample):
        """Compute gradient for each sample individually."""
        per_sample = {}
        for i in range(loss_per_sample.shape[0]):
            self.model.zero_grad()
            loss_per_sample[i].backward(retain_graph=True)
            for name, param in self.model.named_parameters():
                if param.grad is not None:
                    if name not in per_sample:
                        per_sample[name] = []
                    per_sample[name].append(param.grad.clone())

        return {name: torch.stack(grads) for name, grads in per_sample.items()}

    def _clip_gradients(self, per_sample_grads: dict) -> dict:
        """Clip each sample's gradient to max_grad_norm (L2)."""
        clipped = {}
        for name, grads in per_sample_grads.items():
            # Compute per-sample L2 norm across all parameters
            norms = grads.flatten(1).norm(dim=1, keepdim=True).clamp(min=1e-8)
            # Clip factor
            clip_factor = (self.config.max_grad_norm / norms).clamp(max=1.0)
            # Reshape clip factor to match gradient shape
            for _ in range(grads.dim() - 2):
                clip_factor = clip_factor.unsqueeze(-1)
            clipped[name] = grads * clip_factor
        return clipped

    def _add_noise(self, clipped_grads: dict, batch_size: int) -> dict:
        """Add Gaussian noise calibrated to the sensitivity and privacy budget."""
        noisy = {}
        noise_scale = self.config.noise_multiplier * self.config.max_grad_norm / batch_size

        for name, grads in clipped_grads.items():
            # Aggregate (mean of clipped gradients)
            aggregated = grads.mean(dim=0)
            # Add Gaussian noise
            noise = torch.randn_like(aggregated) * noise_scale
            noisy[name] = aggregated + noise

        return noisy


def compute_epsilon(noise_multiplier: float, sample_rate: float,
                    n_steps: int, delta: float = 1e-5) -> float:
    """Compute privacy spent (epsilon) using RDP accountant (simplified).

    Real implementation should use Google's dp-accounting library.
    """
    # Simplified: actual computation uses Renyi Differential Privacy
    rdp_alpha = 1 + 1 / (2 * noise_multiplier ** 2)
    rdp_epsilon = n_steps * sample_rate ** 2 * rdp_alpha / (2 * noise_multiplier ** 2)
    # Convert RDP to (epsilon, delta)-DP
    epsilon = rdp_epsilon + np.log(1 / delta) / (rdp_alpha - 1)
    return epsilon
```

Privacy-utility tradeoff:

| Epsilon | Privacy level | Typical accuracy impact |
|---------|-------------|----------------------|
| **1.0** | Very strong | -10-20% accuracy |
| **3.0** | Strong | -5-10% accuracy |
| **8.0** | Moderate | -2-5% accuracy |
| **∞** | No privacy | Baseline accuracy |

Key patterns:
1. **Per-sample gradient clipping** — bound each sample's influence; clip to max_grad_norm
2. **Calibrated noise** — Gaussian noise proportional to sensitivity/batch_size
3. **Privacy accounting** — track cumulative epsilon across training steps; RDP composition
4. **Privacy-utility tradeoff** — lower epsilon = stronger privacy = more noise = lower accuracy
5. **Batch size matters** — larger batches average out noise; improve utility for same epsilon'''
    ),
    (
        "ai/model-merging",
        "Show model merging techniques: weight averaging, TIES merging, DARE, and task arithmetic for combining fine-tuned models.",
        '''Model merging — combine multiple fine-tuned models without retraining:

```python
import torch
import torch.nn as nn
from collections import OrderedDict
import numpy as np


def simple_average(models: list[nn.Module]) -> OrderedDict:
    """Simple weight averaging (model soup).

    Average weights of models fine-tuned from same base.
    Surprisingly effective — often matches or beats ensembling.
    """
    avg_state = OrderedDict()
    n = len(models)

    for key in models[0].state_dict():
        avg_state[key] = sum(m.state_dict()[key].float() for m in models) / n

    return avg_state


def task_arithmetic(base: nn.Module, fine_tuned: list[nn.Module],
                     scaling: list[float] = None) -> OrderedDict:
    """Task arithmetic: add scaled task vectors to base model.

    task_vector = fine_tuned_weights - base_weights
    merged = base + λ₁·τ₁ + λ₂·τ₂ + ...
    """
    base_state = base.state_dict()
    scaling = scaling or [0.5] * len(fine_tuned)
    merged = OrderedDict()

    for key in base_state:
        result = base_state[key].float()
        for model, scale in zip(fine_tuned, scaling):
            task_vector = model.state_dict()[key].float() - base_state[key].float()
            result += scale * task_vector
        merged[key] = result

    return merged


def ties_merge(base: nn.Module, fine_tuned: list[nn.Module],
               density: float = 0.2, scaling: list[float] = None) -> OrderedDict:
    """TIES: Trim, Elect Sign, and merge.

    1. Trim: keep only top-k% of task vector values (by magnitude)
    2. Elect sign: resolve sign conflicts by majority vote
    3. Merge: average the agreed-upon values
    """
    base_state = base.state_dict()
    scaling = scaling or [1.0] * len(fine_tuned)
    merged = OrderedDict()

    for key in base_state:
        task_vectors = []
        for model, scale in zip(fine_tuned, scaling):
            tv = (model.state_dict()[key].float() - base_state[key].float()) * scale
            task_vectors.append(tv)

        # Step 1: Trim — keep top density% by magnitude
        trimmed = []
        for tv in task_vectors:
            threshold = torch.quantile(tv.abs().float(), 1 - density)
            mask = tv.abs() >= threshold
            trimmed.append(tv * mask.float())

        stacked = torch.stack(trimmed)

        # Step 2: Elect sign — majority vote
        signs = (stacked > 0).float() - (stacked < 0).float()
        elected_sign = signs.sum(dim=0).sign()

        # Step 3: Merge — average values with matching sign
        agreement = (signs == elected_sign.unsqueeze(0)).float()
        matched = stacked * agreement
        count = agreement.sum(dim=0).clamp(min=1)
        merged_tv = matched.sum(dim=0) / count

        merged[key] = base_state[key].float() + merged_tv

    return merged


def dare_merge(base: nn.Module, fine_tuned: list[nn.Module],
               drop_rate: float = 0.9) -> OrderedDict:
    """DARE: Drop And REscale for model merging.

    Randomly drop most task vector values, rescale remaining.
    Works surprisingly well — most fine-tuning changes are redundant.
    """
    base_state = base.state_dict()
    merged = OrderedDict()

    for key in base_state:
        task_vectors = []
        for model in fine_tuned:
            tv = model.state_dict()[key].float() - base_state[key].float()
            # Random drop
            mask = (torch.rand_like(tv) > drop_rate).float()
            # Rescale to preserve expected value
            dropped_tv = tv * mask / (1 - drop_rate)
            task_vectors.append(dropped_tv)

        # Average remaining task vectors
        avg_tv = torch.stack(task_vectors).mean(dim=0)
        merged[key] = base_state[key].float() + avg_tv

    return merged


def slerp_merge(model_a: nn.Module, model_b: nn.Module, t: float = 0.5) -> OrderedDict:
    """Spherical Linear Interpolation (SLERP) between two models.

    Better than linear interpolation for high-dimensional weight spaces.
    """
    state_a = model_a.state_dict()
    state_b = model_b.state_dict()
    merged = OrderedDict()

    for key in state_a:
        a = state_a[key].float().flatten()
        b = state_b[key].float().flatten()

        # Normalize
        a_norm = a / (a.norm() + 1e-8)
        b_norm = b / (b.norm() + 1e-8)

        # Angle between vectors
        cos_omega = (a_norm * b_norm).sum().clamp(-1, 1)
        omega = torch.acos(cos_omega)

        if omega.abs() < 1e-6:
            result = (1 - t) * a + t * b
        else:
            result = (torch.sin((1 - t) * omega) * a + torch.sin(t * omega) * b) / torch.sin(omega)

        merged[key] = result.reshape(state_a[key].shape)

    return merged
```

Merging comparison:

| Method | Best for | Key idea |
|--------|---------|----------|
| **Simple average** | Same-task models | Mean of weights |
| **Task arithmetic** | Multi-task | Add scaled task vectors |
| **TIES** | Conflicting tasks | Trim + sign election |
| **DARE** | Any | Random dropout + rescale |
| **SLERP** | Two models | Spherical interpolation |

Key patterns:
1. **Task vectors** — difference between fine-tuned and base weights; captures task-specific knowledge
2. **TIES sign election** — majority vote resolves conflicting weight changes between models
3. **DARE dropout** — 90% of fine-tuning changes are redundant; drop and rescale works well
4. **SLERP** — spherical interpolation preserves weight norms better than linear interpolation
5. **Scaling factors** — control contribution of each model; task-dependent tuning'''
    ),
]
"""
