"""Neural architecture search and AutoML — NAS, hyperparameter optimization, meta-learning."""

PAIRS = [
    (
        "ai/neural-architecture-search",
        "Show Neural Architecture Search (NAS) patterns: search spaces, one-shot NAS (supernet), DARTS differentiable search, and efficiency-aware search.",
        '''Neural Architecture Search:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional
import random


# === Search Space Definition ===

OPERATIONS = {
    "conv3x3": lambda C: nn.Sequential(
        nn.Conv2d(C, C, 3, padding=1, bias=False), nn.BatchNorm2d(C), nn.ReLU(),
    ),
    "conv5x5": lambda C: nn.Sequential(
        nn.Conv2d(C, C, 5, padding=2, bias=False), nn.BatchNorm2d(C), nn.ReLU(),
    ),
    "sep_conv3x3": lambda C: nn.Sequential(
        nn.Conv2d(C, C, 3, padding=1, groups=C, bias=False),
        nn.Conv2d(C, C, 1, bias=False), nn.BatchNorm2d(C), nn.ReLU(),
    ),
    "max_pool3x3": lambda C: nn.MaxPool2d(3, stride=1, padding=1),
    "avg_pool3x3": lambda C: nn.AvgPool2d(3, stride=1, padding=1),
    "skip_connect": lambda C: nn.Identity(),
    "none": lambda C: Zero(),
}


class Zero(nn.Module):
    def forward(self, x):
        return x * 0


# === DARTS: Differentiable Architecture Search ===

class MixedOp(nn.Module):
    """Mixture of operations with learnable architecture weights."""

    def __init__(self, channels: int):
        super().__init__()
        self.ops = nn.ModuleList([
            op_fn(channels) for op_fn in OPERATIONS.values()
        ])

    def forward(self, x: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
        """Weighted sum of all operations (continuous relaxation)."""
        return sum(w * op(x) for w, op in zip(weights, self.ops))


class DARTSCell(nn.Module):
    """DARTS cell with mixed operations on each edge."""

    def __init__(self, channels: int, n_nodes: int = 4):
        super().__init__()
        self.n_nodes = n_nodes
        self.n_ops = len(OPERATIONS)

        # Create mixed operations for each edge
        self.edges = nn.ModuleDict()
        for i in range(n_nodes):
            for j in range(i + 2):  # Connect to input1, input2, and previous nodes
                self.edges[f"{j}_{i+2}"] = MixedOp(channels)

        # Architecture parameters (alpha)
        self.alphas = nn.ParameterDict()
        for i in range(n_nodes):
            for j in range(i + 2):
                self.alphas[f"{j}_{i+2}"] = nn.Parameter(torch.randn(self.n_ops) * 1e-3)

    def forward(self, s0: torch.Tensor, s1: torch.Tensor) -> torch.Tensor:
        states = [s0, s1]
        for i in range(self.n_nodes):
            node_input = []
            for j in range(len(states)):
                key = f"{j}_{i+2}"
                weights = F.softmax(self.alphas[key], dim=0)
                node_input.append(self.edges[key](states[j], weights))
            states.append(sum(node_input))

        return torch.cat(states[2:], dim=1)  # Concat intermediate nodes


class DARTSTrainer:
    """Bilevel optimization for DARTS.

    Outer loop: update architecture params (alpha) on validation loss.
    Inner loop: update network weights (w) on training loss.
    """

    def __init__(self, model, arch_lr: float = 3e-4, weight_lr: float = 0.025):
        self.model = model
        # Separate optimizers for weights and architecture
        arch_params = [p for n, p in model.named_parameters() if "alpha" in n]
        weight_params = [p for n, p in model.named_parameters() if "alpha" not in n]

        self.arch_optimizer = torch.optim.Adam(arch_params, lr=arch_lr, weight_decay=1e-3)
        self.weight_optimizer = torch.optim.SGD(weight_params, lr=weight_lr, momentum=0.9, weight_decay=3e-4)

    def step(self, train_batch, val_batch):
        """One bilevel optimization step."""
        train_x, train_y = train_batch
        val_x, val_y = val_batch

        # Step 1: Update architecture on validation data
        self.arch_optimizer.zero_grad()
        val_loss = F.cross_entropy(self.model(val_x), val_y)
        val_loss.backward()
        self.arch_optimizer.step()

        # Step 2: Update weights on training data
        self.weight_optimizer.zero_grad()
        train_loss = F.cross_entropy(self.model(train_x), train_y)
        train_loss.backward()
        self.weight_optimizer.step()

        return train_loss.item(), val_loss.item()

    def derive_architecture(self) -> dict:
        """Extract discrete architecture from continuous weights."""
        architecture = {}
        for name, alpha in self.model.alphas.items():
            weights = F.softmax(alpha, dim=0)
            op_idx = weights.argmax().item()
            op_name = list(OPERATIONS.keys())[op_idx]
            architecture[name] = op_name
        return architecture
```

NAS comparison:

| Method | Search cost | Search space | Quality |
|--------|------------|-------------|---------|
| **DARTS** | 1 GPU-day | Continuous relaxation | Good |
| **ENAS** | 0.5 GPU-day | Weight sharing | Good |
| **Random search** | N GPU-days | Any | Baseline |
| **Evolutionary** | 100+ GPU-days | Any | Excellent |

Key patterns:
1. **Continuous relaxation** — DARTS replaces discrete op choice with softmax-weighted mixture
2. **Bilevel optimization** — architecture params on validation, weights on training (prevents overfitting)
3. **Search space** — define candidate operations; cell-based search reuses cells across network
4. **Derive architecture** — after search, take argmax of architecture weights for final discrete model
5. **Weight sharing** — supernet shares weights across all architectures; amortizes training cost'''
    ),
    (
        "ai/hyperparameter-optimization",
        "Show hyperparameter optimization: Optuna Bayesian optimization, pruning, multi-objective optimization, and search space design.",
        '''Hyperparameter optimization with Optuna:

```python
import optuna
from optuna.trial import Trial
from optuna.pruners import HyperbandPruner
from optuna.samplers import TPESampler
import torch
import torch.nn as nn
from torch.utils.data import DataLoader


def create_model(trial: Trial) -> nn.Module:
    """Define model architecture with hyperparameters from trial."""
    n_layers = trial.suggest_int("n_layers", 2, 6)
    hidden_dim = trial.suggest_categorical("hidden_dim", [128, 256, 512, 1024])
    dropout = trial.suggest_float("dropout", 0.1, 0.5)
    activation = trial.suggest_categorical("activation", ["relu", "gelu", "silu"])

    act_fn = {"relu": nn.ReLU, "gelu": nn.GELU, "silu": nn.SiLU}[activation]

    layers = []
    in_dim = 784  # Example: MNIST
    for i in range(n_layers):
        out_dim = hidden_dim if i < n_layers - 1 else 10
        layers.extend([nn.Linear(in_dim, out_dim), act_fn(), nn.Dropout(dropout)])
        in_dim = out_dim

    return nn.Sequential(*layers[:-2], layers[-2])  # Remove last dropout and activation


def objective(trial: Trial) -> float:
    """Optuna objective function for hyperparameter optimization."""
    model = create_model(trial).cuda()

    # Optimizer hyperparameters
    lr = trial.suggest_float("lr", 1e-5, 1e-2, log=True)
    weight_decay = trial.suggest_float("weight_decay", 1e-6, 1e-2, log=True)
    optimizer_name = trial.suggest_categorical("optimizer", ["adam", "adamw", "sgd"])

    if optimizer_name == "adam":
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    elif optimizer_name == "adamw":
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    else:
        momentum = trial.suggest_float("momentum", 0.8, 0.99)
        optimizer = torch.optim.SGD(model.parameters(), lr=lr, momentum=momentum)

    # Training with intermediate reporting for pruning
    for epoch in range(20):
        train_loss = train_epoch(model, optimizer)
        val_acc = evaluate(model)

        # Report intermediate value for pruning
        trial.report(val_acc, epoch)

        # Prune unpromising trials early
        if trial.should_prune():
            raise optuna.TrialPruned()

    return val_acc


def run_optimization():
    """Run Optuna study with advanced features."""
    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=42, n_startup_trials=10),
        pruner=HyperbandPruner(min_resource=3, max_resource=20, reduction_factor=3),
        study_name="model_optimization",
        storage="sqlite:///optuna.db",  # Persistent storage
        load_if_exists=True,
    )

    study.optimize(
        objective,
        n_trials=100,
        timeout=3600,  # 1 hour max
        n_jobs=2,      # Parallel trials
        show_progress_bar=True,
    )

    print(f"Best trial: {study.best_trial.value:.4f}")
    print(f"Best params: {study.best_trial.params}")
    return study


def multi_objective_optimization():
    """Multi-objective: maximize accuracy AND minimize model size."""

    def multi_objective(trial: Trial) -> tuple[float, float]:
        model = create_model(trial).cuda()
        n_params = sum(p.numel() for p in model.parameters())

        lr = trial.suggest_float("lr", 1e-5, 1e-2, log=True)
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

        for epoch in range(10):
            train_epoch(model, optimizer)

        val_acc = evaluate(model)
        return val_acc, n_params  # Maximize acc, minimize params

    study = optuna.create_study(
        directions=["maximize", "minimize"],
        sampler=TPESampler(seed=42),
    )
    study.optimize(multi_objective, n_trials=50)

    # Get Pareto front
    pareto_trials = study.best_trials
    for t in pareto_trials:
        print(f"Acc: {t.values[0]:.4f}, Params: {t.values[1]:,}")


# Placeholder training functions
def train_epoch(model, optimizer):
    pass

def evaluate(model):
    return 0.0
```

Key patterns:
1. **TPE sampler** — Tree-structured Parzen Estimator; Bayesian optimization that models promising regions
2. **Hyperband pruner** — early-stop unpromising trials; saves compute on bad configurations
3. **Log-scale search** — use `log=True` for learning rates and weight decay (span orders of magnitude)
4. **Multi-objective** — Pareto optimization for accuracy vs model size tradeoff
5. **Persistent storage** — SQLite backend enables resumable studies and dashboard visualization'''
    ),
    (
        "ai/meta-learning",
        "Show meta-learning patterns: MAML (Model-Agnostic Meta-Learning), Prototypical Networks, and few-shot learning.",
        '''Meta-learning for few-shot generalization:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import copy


# === MAML: Model-Agnostic Meta-Learning ===

class MAML:
    """MAML: Learn initialization that adapts quickly to new tasks.

    Meta-train: for each task, do K gradient steps, then compute
    meta-loss on the adapted model. Update initialization to minimize
    meta-loss across all tasks.
    """

    def __init__(self, model: nn.Module, inner_lr: float = 0.01,
                 meta_lr: float = 0.001, inner_steps: int = 5):
        self.model = model
        self.inner_lr = inner_lr
        self.inner_steps = inner_steps
        self.meta_optimizer = torch.optim.Adam(model.parameters(), lr=meta_lr)

    def inner_loop(self, support_x, support_y):
        """Adapt model to a single task using support set."""
        adapted_model = copy.deepcopy(self.model)
        adapted_optimizer = torch.optim.SGD(adapted_model.parameters(), lr=self.inner_lr)

        for _ in range(self.inner_steps):
            logits = adapted_model(support_x)
            loss = F.cross_entropy(logits, support_y)
            adapted_optimizer.zero_grad()
            loss.backward()
            adapted_optimizer.step()

        return adapted_model

    def meta_train_step(self, tasks: list[dict]) -> float:
        """One meta-training step across multiple tasks."""
        meta_loss = 0

        for task in tasks:
            # Inner loop: adapt to task
            adapted = self.inner_loop(task["support_x"], task["support_y"])

            # Outer loop: evaluate adapted model on query set
            query_logits = adapted(task["query_x"])
            task_loss = F.cross_entropy(query_logits, task["query_y"])
            meta_loss += task_loss

        meta_loss /= len(tasks)

        # Meta-update: optimize initialization
        self.meta_optimizer.zero_grad()
        meta_loss.backward()
        self.meta_optimizer.step()

        return meta_loss.item()

    def adapt_and_evaluate(self, support_x, support_y, query_x, query_y):
        """Few-shot evaluation: adapt then test."""
        adapted = self.inner_loop(support_x, support_y)
        with torch.no_grad():
            logits = adapted(query_x)
            acc = (logits.argmax(dim=1) == query_y).float().mean()
        return acc.item()


# === Prototypical Networks ===

class PrototypicalNetwork(nn.Module):
    """Prototypical Networks: classify by distance to class prototypes.

    For each class, compute prototype = mean of support embeddings.
    Classify query by nearest prototype in embedding space.
    """

    def __init__(self, encoder: nn.Module, embed_dim: int = 64):
        super().__init__()
        self.encoder = encoder
        self.embed_dim = embed_dim

    def compute_prototypes(self, support_x: torch.Tensor, support_y: torch.Tensor):
        """Compute class prototypes from support set."""
        embeddings = self.encoder(support_x)  # [N_support, embed_dim]
        classes = support_y.unique()
        prototypes = []
        for c in classes:
            mask = (support_y == c)
            prototype = embeddings[mask].mean(dim=0)
            prototypes.append(prototype)
        return torch.stack(prototypes), classes

    def forward(self, support_x, support_y, query_x):
        """Classify query examples using prototypes."""
        prototypes, classes = self.compute_prototypes(support_x, support_y)
        query_embeddings = self.encoder(query_x)  # [N_query, embed_dim]

        # Euclidean distance to each prototype
        distances = torch.cdist(query_embeddings, prototypes)  # [N_query, N_classes]
        logits = -distances  # Negative distance = similarity

        return logits, classes


class EpisodeSampler:
    """Sample N-way K-shot episodes for meta-learning."""

    def __init__(self, dataset, n_way: int = 5, k_shot: int = 5,
                 n_query: int = 15):
        self.dataset = dataset
        self.n_way = n_way
        self.k_shot = k_shot
        self.n_query = n_query

        # Group indices by class
        self.class_indices = {}
        for idx, (_, label) in enumerate(dataset):
            if label not in self.class_indices:
                self.class_indices[label] = []
            self.class_indices[label].append(idx)

    def sample_episode(self) -> dict:
        """Sample one N-way K-shot episode."""
        import random
        classes = random.sample(list(self.class_indices.keys()), self.n_way)

        support_x, support_y, query_x, query_y = [], [], [], []

        for new_label, cls in enumerate(classes):
            indices = random.sample(
                self.class_indices[cls],
                self.k_shot + self.n_query,
            )

            for idx in indices[:self.k_shot]:
                x, _ = self.dataset[idx]
                support_x.append(x)
                support_y.append(new_label)

            for idx in indices[self.k_shot:]:
                x, _ = self.dataset[idx]
                query_x.append(x)
                query_y.append(new_label)

        return {
            "support_x": torch.stack(support_x),
            "support_y": torch.tensor(support_y),
            "query_x": torch.stack(query_x),
            "query_y": torch.tensor(query_y),
        }
```

Meta-learning comparison:

| Method | Adaptation | Memory | Few-shot accuracy |
|--------|-----------|--------|------------------|
| **MAML** | Gradient steps | High (backprop through adapt) | High |
| **ProtoNet** | No adaptation (nearest prototype) | Low | Good |
| **Matching Networks** | Attention over support set | Medium | Good |
| **Reptile** | First-order MAML approximation | Low | Good |

Key patterns:
1. **MAML inner/outer loop** — inner loop adapts to task, outer loop optimizes initialization
2. **Prototypical Networks** — class prototype = mean embedding; classify by nearest prototype
3. **Episode training** — N-way K-shot episodes simulate test-time few-shot conditions
4. **Support/query split** — support set for adaptation, query set for evaluation (per task)
5. **First-order approximation** — Reptile/FOMAML avoid second-order gradients for efficiency'''
    ),
    (
        "ai/model-interpretability",
        "Show model interpretability: attention visualization, SHAP values, feature attribution, and activation maximization for neural networks.",
        '''Model interpretability and explainability:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Optional


class GradientAttribution:
    """Gradient-based feature attribution methods."""

    def __init__(self, model: nn.Module):
        self.model = model
        self.model.eval()

    def vanilla_gradients(self, x: torch.Tensor, target_class: int) -> torch.Tensor:
        """Simple gradient of output w.r.t. input."""
        x = x.clone().requires_grad_(True)
        output = self.model(x)
        output[0, target_class].backward()
        return x.grad.abs()

    def integrated_gradients(self, x: torch.Tensor, target_class: int,
                             baseline: Optional[torch.Tensor] = None,
                             n_steps: int = 50) -> torch.Tensor:
        """Integrated Gradients: accumulate gradients along path from baseline.

        IG satisfies: completeness (attributions sum to prediction difference),
        sensitivity, and implementation invariance.
        """
        if baseline is None:
            baseline = torch.zeros_like(x)

        # Generate interpolated inputs along path
        alphas = torch.linspace(0, 1, n_steps).to(x.device)
        interpolated = torch.stack([
            baseline + alpha * (x - baseline) for alpha in alphas
        ])

        # Compute gradients at each point
        interpolated.requires_grad_(True)
        outputs = self.model(interpolated)
        target_outputs = outputs[:, target_class].sum()
        target_outputs.backward()

        # Average gradients and scale by input difference
        avg_gradients = interpolated.grad.mean(dim=0)
        ig = (x - baseline) * avg_gradients

        return ig

    def grad_cam(self, x: torch.Tensor, target_class: int,
                 target_layer: nn.Module) -> torch.Tensor:
        """Grad-CAM: gradient-weighted class activation mapping.

        Highlights which spatial regions are important for the prediction.
        """
        activations = {}
        gradients = {}

        def save_activation(name):
            def hook(module, input, output):
                activations[name] = output.detach()
            return hook

        def save_gradient(name):
            def hook(module, grad_input, grad_output):
                gradients[name] = grad_output[0].detach()
            return hook

        # Register hooks
        target_layer.register_forward_hook(save_activation("target"))
        target_layer.register_full_backward_hook(save_gradient("target"))

        # Forward + backward
        output = self.model(x)
        output[0, target_class].backward()

        # Compute Grad-CAM
        act = activations["target"]  # [B, C, H, W]
        grad = gradients["target"]   # [B, C, H, W]

        # Global average pooling of gradients -> channel weights
        weights = grad.mean(dim=(2, 3), keepdim=True)  # [B, C, 1, 1]

        # Weighted sum of activations
        cam = (weights * act).sum(dim=1, keepdim=True)  # [B, 1, H, W]
        cam = F.relu(cam)  # Only positive contributions
        cam = cam / (cam.max() + 1e-8)  # Normalize to [0, 1]

        return cam


class SHAPExplainer:
    """Simplified SHAP (Kernel SHAP) for model-agnostic explanations."""

    def __init__(self, model, background_data: torch.Tensor, n_samples: int = 100):
        self.model = model
        self.background = background_data
        self.n_samples = n_samples

    @torch.no_grad()
    def explain(self, x: torch.Tensor) -> torch.Tensor:
        """Approximate SHAP values using sampling."""
        n_features = x.shape[1]
        shap_values = torch.zeros_like(x)

        for _ in range(self.n_samples):
            # Random permutation for feature ordering
            perm = torch.randperm(n_features)
            # Random background sample
            bg_idx = torch.randint(0, len(self.background), (1,)).item()
            bg = self.background[bg_idx]

            # Compute marginal contributions
            x_masked = bg.clone()
            for feat_idx in perm:
                x_with = x_masked.clone()
                x_with[0, feat_idx] = x[0, feat_idx]

                pred_with = self.model(x_with.unsqueeze(0))[0]
                pred_without = self.model(x_masked.unsqueeze(0))[0]

                contribution = pred_with - pred_without
                shap_values[0, feat_idx] += contribution.mean()

                x_masked = x_with

        return shap_values / self.n_samples
```

Interpretability comparison:

| Method | Type | Model-agnostic | Faithfulness |
|--------|------|---------------|-------------|
| **Vanilla gradients** | Gradient | No | Low (noisy) |
| **Integrated Gradients** | Gradient | No | High (axiomatic) |
| **Grad-CAM** | Gradient + activation | No (CNN) | Medium |
| **SHAP** | Game theory | Yes | High |
| **LIME** | Local surrogate | Yes | Medium |

Key patterns:
1. **Integrated Gradients** — accumulate gradients along path from baseline; satisfies completeness axiom
2. **Grad-CAM** — gradient-weighted activation maps; highlights spatial regions for CNN decisions
3. **SHAP values** — Shapley values from cooperative game theory; fair attribution to features
4. **Baseline choice** — zero/black baseline for images; mean for tabular; affects all gradient methods
5. **Hook-based extraction** — register forward/backward hooks to capture intermediate activations'''
    ),
]
