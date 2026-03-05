"""Robotics and embodied AI — control policies, simulation, imitation learning."""

PAIRS = [
    (
        "ai/imitation-learning",
        "Show imitation learning patterns: behavior cloning, DAgger, and learning from demonstrations for robot control.",
        '''Imitation learning for robot control:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import Dataset, DataLoader
from collections import deque


class DemonstrationDataset(Dataset):
    """Dataset of expert demonstrations (state, action) pairs."""

    def __init__(self, demonstrations: list[dict]):
        self.states = []
        self.actions = []
        for demo in demonstrations:
            for s, a in zip(demo["states"], demo["actions"]):
                self.states.append(np.array(s, dtype=np.float32))
                self.actions.append(np.array(a, dtype=np.float32))

    def __len__(self):
        return len(self.states)

    def __getitem__(self, idx):
        return torch.FloatTensor(self.states[idx]), torch.FloatTensor(self.actions[idx])


class BehaviorCloningPolicy(nn.Module):
    """Behavior Cloning: supervised learning on expert demonstrations.

    Simple but suffers from distribution shift — small errors compound
    because the policy visits states never seen in demonstrations.
    """

    def __init__(self, state_dim: int, action_dim: int, hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, action_dim), nn.Tanh(),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state)

    def train_bc(self, dataset: DemonstrationDataset, epochs: int = 100, lr: float = 1e-3):
        optimizer = torch.optim.Adam(self.parameters(), lr=lr)
        loader = DataLoader(dataset, batch_size=64, shuffle=True)

        for epoch in range(epochs):
            total_loss = 0
            for states, actions in loader:
                pred_actions = self(states)
                loss = F.mse_loss(pred_actions, actions)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if epoch % 20 == 0:
                print(f"Epoch {epoch}: Loss = {total_loss/len(loader):.4f}")


class DAggerTrainer:
    """DAgger: Dataset Aggregation for imitation learning.

    Fixes distribution shift by iteratively:
    1. Run current policy to collect states
    2. Query expert for correct actions at those states
    3. Add to dataset and retrain

    After several rounds, policy has seen states from its own distribution.
    """

    def __init__(self, policy: BehaviorCloningPolicy, expert_fn, env):
        self.policy = policy
        self.expert_fn = expert_fn  # Returns expert action for any state
        self.env = env
        self.dataset_states = []
        self.dataset_actions = []

    def collect_expert_demos(self, n_episodes: int = 10):
        """Collect initial expert demonstrations."""
        for _ in range(n_episodes):
            state = self.env.reset()
            done = False
            while not done:
                action = self.expert_fn(state)
                self.dataset_states.append(state)
                self.dataset_actions.append(action)
                state, _, done, _ = self.env.step(action)

    def dagger_iteration(self, n_episodes: int = 5, beta: float = 0.0):
        """One DAgger iteration: collect with policy, label with expert."""
        for _ in range(n_episodes):
            state = self.env.reset()
            done = False
            while not done:
                # Mix policy and expert (beta controls interpolation)
                if np.random.random() < beta:
                    action = self.expert_fn(state)
                else:
                    with torch.no_grad():
                        action = self.policy(torch.FloatTensor(state)).numpy()

                # Always get expert label for the visited state
                expert_action = self.expert_fn(state)
                self.dataset_states.append(state)
                self.dataset_actions.append(expert_action)

                state, _, done, _ = self.env.step(action)

    def train(self, n_iterations: int = 10, epochs_per_iter: int = 50):
        """Full DAgger training loop."""
        self.collect_expert_demos()

        for i in range(n_iterations):
            # Create dataset from all collected data
            dataset = DemonstrationDataset([{
                "states": self.dataset_states,
                "actions": self.dataset_actions,
            }])

            # Retrain policy on aggregated dataset
            self.policy.train_bc(dataset, epochs=epochs_per_iter)

            # Collect new data using current policy
            beta = max(0, 1 - i / n_iterations)  # Decay expert mixing
            self.dagger_iteration(beta=beta)

            print(f"DAgger iter {i}: dataset size = {len(self.dataset_states)}")
```

Imitation learning comparison:

| Method | Distribution shift | Expert queries | Data efficiency |
|--------|-------------------|---------------|-----------------|
| **Behavior Cloning** | Yes (compounds) | Train only | Good |
| **DAgger** | No (iterative) | Online needed | Better |
| **GAIL** | No (adversarial) | Train only | Lower |
| **IRL** | No (recovers reward) | Train only | Lowest |

Key patterns:
1. **Behavior cloning** — supervised learning on (state, action) pairs; simple but fragile
2. **DAgger** — iteratively aggregate data from policy's own state distribution
3. **Expert mixing (β)** — gradually reduce expert actions as policy improves
4. **Distribution shift** — BC visits unseen states → errors compound; DAgger fixes this
5. **Action space** — Tanh output for continuous control; bounded actions'''
    ),
    (
        "ai/sim-to-real",
        "Show sim-to-real transfer patterns: domain randomization, system identification, and bridging the reality gap for robotics.",
        '''Sim-to-real transfer for robotics:

```python
import torch
import torch.nn as nn
import numpy as np
from dataclasses import dataclass, field
import random


@dataclass
class DomainRandomization:
    """Randomize simulation parameters to bridge sim-to-real gap.

    Key insight: if the policy works across many simulated variations,
    it's more likely to work in the real world.
    """
    # Physics parameters
    friction_range: tuple = (0.5, 1.5)
    mass_scale_range: tuple = (0.8, 1.2)
    gravity_range: tuple = (9.6, 10.0)

    # Sensor noise
    observation_noise_std: float = 0.02
    action_noise_std: float = 0.01
    latency_range: tuple = (0, 3)  # frames of delay

    # Visual randomization
    lighting_range: tuple = (0.5, 1.5)
    texture_randomize: bool = True
    camera_position_noise: float = 0.05

    def randomize_physics(self) -> dict:
        """Sample random physics parameters."""
        return {
            "friction": random.uniform(*self.friction_range),
            "mass_scale": random.uniform(*self.mass_scale_range),
            "gravity": random.uniform(*self.gravity_range),
        }

    def add_observation_noise(self, obs: np.ndarray) -> np.ndarray:
        """Add sensor noise to observations."""
        noise = np.random.normal(0, self.observation_noise_std, obs.shape)
        return obs + noise

    def add_action_noise(self, action: np.ndarray) -> np.ndarray:
        """Add actuator noise to actions."""
        noise = np.random.normal(0, self.action_noise_std, action.shape)
        return np.clip(action + noise, -1, 1)


class DomainAdaptationNetwork(nn.Module):
    """Domain-adversarial network for sim-to-real adaptation.

    Learn features that are useful for the task but invariant
    to the domain (sim vs real).
    """

    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 256):
        super().__init__()
        # Shared feature extractor
        self.feature_extractor = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )

        # Task head (action prediction)
        self.task_head = nn.Sequential(
            nn.Linear(hidden, action_dim), nn.Tanh(),
        )

        # Domain classifier (sim vs real)
        self.domain_head = nn.Sequential(
            nn.Linear(hidden, 64), nn.ReLU(),
            nn.Linear(64, 1), nn.Sigmoid(),
        )

    def forward(self, obs, alpha: float = 1.0):
        features = self.feature_extractor(obs)

        # Task prediction
        actions = self.task_head(features)

        # Domain prediction (with gradient reversal for adversarial training)
        reversed_features = GradientReversal.apply(features, alpha)
        domain_pred = self.domain_head(reversed_features)

        return actions, domain_pred


class GradientReversal(torch.autograd.Function):
    """Gradient reversal layer for domain-adversarial training."""

    @staticmethod
    def forward(ctx, x, alpha):
        ctx.alpha = alpha
        return x.clone()

    @staticmethod
    def backward(ctx, grad_output):
        return -ctx.alpha * grad_output, None
```

Sim-to-real techniques:

| Technique | Approach | Effectiveness |
|-----------|---------|--------------|
| **Domain randomization** | Random sim parameters | High |
| **System identification** | Calibrate sim to real | Medium |
| **Domain adaptation** | Align feature distributions | High |
| **Progressive transfer** | Sim → few real demos | Highest |
| **Digital twin** | High-fidelity simulation | Medium |

Key patterns:
1. **Domain randomization** — vary physics, textures, lighting in simulation; forces robust policies
2. **Gradient reversal** — adversarial training makes features domain-invariant
3. **Observation noise** — add sensor noise in sim to match real-world sensor imprecision
4. **Action delay** — simulate communication latency between controller and actuators
5. **Progressive difficulty** — start with clean sim, gradually add randomization'''
    ),
    (
        "ai/world-models",
        "Show world model patterns: learned dynamics models, model-based RL, and planning with learned simulators.",
        '''World models — learned environment simulators:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class WorldModel(nn.Module):
    """Learned dynamics model: predict next state and reward.

    s_{t+1}, r_t = f(s_t, a_t)

    Enables model-based RL: plan in the learned model instead
    of the real environment (much cheaper/faster).
    """

    def __init__(self, state_dim: int, action_dim: int,
                 hidden_dim: int = 256, ensemble_size: int = 5):
        super().__init__()
        self.ensemble_size = ensemble_size

        # Ensemble of dynamics models for uncertainty estimation
        self.dynamics = nn.ModuleList([
            nn.Sequential(
                nn.Linear(state_dim + action_dim, hidden_dim), nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
                nn.Linear(hidden_dim, state_dim + 1),  # +1 for reward
            )
            for _ in range(ensemble_size)
        ])

    def predict(self, state: torch.Tensor, action: torch.Tensor,
                deterministic: bool = False):
        """Predict next state and reward."""
        x = torch.cat([state, action], dim=-1)

        predictions = []
        for model in self.dynamics:
            pred = model(x)
            next_state = pred[..., :-1]
            reward = pred[..., -1]
            predictions.append((next_state, reward))

        if deterministic:
            # Mean prediction
            next_states = torch.stack([p[0] for p in predictions]).mean(dim=0)
            rewards = torch.stack([p[1] for p in predictions]).mean(dim=0)
        else:
            # Random ensemble member (for exploration)
            idx = torch.randint(0, self.ensemble_size, (1,)).item()
            next_states, rewards = predictions[idx]

        return next_states, rewards

    def uncertainty(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Epistemic uncertainty from ensemble disagreement."""
        x = torch.cat([state, action], dim=-1)
        predictions = torch.stack([
            model(x)[..., :-1] for model in self.dynamics
        ])
        return predictions.std(dim=0).mean(dim=-1)


class ModelBasedPlanner:
    """Plan actions using learned world model (CEM/MPPI)."""

    def __init__(self, world_model: WorldModel, action_dim: int,
                 horizon: int = 15, n_candidates: int = 500,
                 n_elites: int = 50, n_iterations: int = 5):
        self.model = world_model
        self.action_dim = action_dim
        self.horizon = horizon
        self.n_candidates = n_candidates
        self.n_elites = n_elites
        self.n_iterations = n_iterations

    @torch.no_grad()
    def plan(self, state: torch.Tensor) -> torch.Tensor:
        """Cross-Entropy Method (CEM) planning."""
        # Initialize action distribution
        mean = torch.zeros(self.horizon, self.action_dim)
        std = torch.ones(self.horizon, self.action_dim)

        for _ in range(self.n_iterations):
            # Sample action sequences
            actions = mean.unsqueeze(0) + std.unsqueeze(0) * torch.randn(
                self.n_candidates, self.horizon, self.action_dim
            )
            actions = actions.clamp(-1, 1)

            # Evaluate each sequence using world model
            returns = torch.zeros(self.n_candidates)
            current_states = state.unsqueeze(0).expand(self.n_candidates, -1)

            for t in range(self.horizon):
                next_states, rewards = self.model.predict(
                    current_states, actions[:, t], deterministic=True
                )
                returns += rewards * (0.99 ** t)
                current_states = next_states

            # Select elites and update distribution
            elite_idx = returns.topk(self.n_elites).indices
            elite_actions = actions[elite_idx]
            mean = elite_actions.mean(dim=0)
            std = elite_actions.std(dim=0).clamp(min=0.01)

        return mean[0]  # Return first action
```

Key patterns:
1. **Ensemble dynamics** — multiple models estimate uncertainty; high disagreement = low confidence
2. **CEM planning** — sample action sequences, evaluate in model, keep top-k, refine distribution
3. **Model-based RL** — plan in learned model (cheap) instead of real environment (expensive)
4. **Horizon planning** — look ahead H steps; balance between myopic and long-horizon planning
5. **Delta prediction** — predict state change (Δs) instead of absolute next state; more stable'''
    ),
]
"""
