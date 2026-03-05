"""
Batch P7 -- Reinforcement Learning: DQN, policy gradients, multi-agent RL,
model-based RL / world models, and RLHF for language models.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Q-Learning and Deep Q-Networks (DQN) ---
    (
        "reinforcement-learning/dqn-bellman-experience-replay-target-networks",
        "Explain Q-learning and Deep Q-Networks in depth covering the Bellman equation, temporal difference learning, experience replay buffers, target networks with soft updates, double DQN, dueling DQN architecture, the deadly triad, and provide a complete PyTorch DQN agent implementation with epsilon-greedy exploration and convergence analysis.",
        r"""
# Q-Learning and Deep Q-Networks (DQN): From Bellman to Modern Architectures

## Foundations of Value-Based Reinforcement Learning

Reinforcement learning centers on an agent interacting with an environment to maximize cumulative reward. **Q-learning** is a model-free, off-policy algorithm that learns the optimal action-value function Q*(s, a) -- the expected discounted return from taking action a in state s and then following the optimal policy thereafter. The elegance of Q-learning lies in the **Bellman optimality equation**, which provides a recursive decomposition:

Q*(s, a) = E[r + gamma * max_a' Q*(s', a')]

Here gamma is the **discount factor** controlling the trade-off between immediate and future rewards. A gamma close to 1.0 makes the agent far-sighted, while a gamma near 0 makes it myopic. **Temporal difference (TD) learning** is the mechanism that bootstraps this recursion: rather than waiting for a complete episode to compute returns (as in Monte Carlo methods), TD updates the value estimate after each step using the one-step TD target:

TD_target = r + gamma * max_a' Q(s', a')
TD_error = TD_target - Q(s, a)

The Q-value is then updated as Q(s, a) <- Q(s, a) + alpha * TD_error. This is powerful because it combines the sample efficiency of bootstrapping with the ability to learn online. However, a **common mistake** is assuming TD learning always converges -- in the tabular case it does (under standard conditions), but with function approximation the story changes dramatically.

## The Deadly Triad

The **deadly triad** refers to the combination of three elements that can cause divergence in value-based RL: (1) **function approximation** (using a neural network instead of a table), (2) **bootstrapping** (using TD targets that depend on the current estimate), and (3) **off-policy learning** (learning about a policy different from the one generating data). When all three are present, updates can create a positive feedback loop where overestimated values propagate through bootstrapping, the function approximator generalizes these errors to unseen states, and off-policy data exacerbates the distribution mismatch. DQN addresses this instability through two critical innovations: **experience replay** and **target networks**.

## Experience Replay and Target Networks

**Experience replay** stores transitions (s, a, r, s', done) in a buffer and samples random mini-batches for training. This provides three benefits: (1) it breaks temporal correlations between consecutive samples, which would otherwise cause the network to overfit to recent trajectories; (2) it enables data reuse, dramatically improving sample efficiency; and (3) it smooths the training distribution, reducing variance. The **best practice** is to use a replay buffer of 100k-1M transitions, because too small a buffer causes overfitting while too large a buffer dilutes recent experience.

**Target networks** address the moving target problem. Without a target network, the TD target Q(s', a') shifts with every gradient step, creating a non-stationary optimization problem. DQN maintains a separate target network Q_target whose parameters are updated slowly, either through periodic hard copies (every C steps) or **soft updates** (Polyak averaging): theta_target <- tau * theta + (1 - tau) * theta_target, where tau is typically 0.005. This stabilizes training because the TD targets change smoothly.

### Complete DQN Agent in PyTorch

```python
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from typing import Tuple, List, Optional

class ReplayBuffer:
    # Fixed-size circular buffer for experience replay
    def __init__(self, capacity: int = 100_000) -> None:
        self.buffer: deque = deque(maxlen=capacity)

    def push(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> Tuple[
        torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor
    ]:
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            torch.FloatTensor(np.array(states)),
            torch.LongTensor(actions),
            torch.FloatTensor(rewards),
            torch.FloatTensor(np.array(next_states)),
            torch.FloatTensor(dones),
        )

    def __len__(self) -> int:
        return len(self.buffer)


class DuelingDQN(nn.Module):
    # Dueling architecture separates state-value and advantage streams
    # This helps the network learn which states are valuable
    # regardless of the action taken
    def __init__(self, state_dim: int, action_dim: int, hidden: int = 256) -> None:
        super().__init__()
        self.feature = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        # Value stream: V(s) -- scalar value of being in state s
        self.value_stream = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, 1),
        )
        # Advantage stream: A(s, a) -- relative advantage of each action
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.feature(x)
        value = self.value_stream(features)
        advantage = self.advantage_stream(features)
        # Combine using mean-centering: Q(s,a) = V(s) + A(s,a) - mean(A)
        # This identifiability trick ensures V and A are uniquely determined
        q_values = value + advantage - advantage.mean(dim=1, keepdim=True)
        return q_values


class DQNAgent:
    # Full DQN agent with double DQN, dueling architecture,
    # epsilon-greedy exploration, and soft target updates
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr: float = 1e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.01,
        epsilon_decay: int = 50_000,
        buffer_size: int = 100_000,
        batch_size: int = 64,
        device: str = "cpu",
    ) -> None:
        self.action_dim = action_dim
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.device = torch.device(device)

        # Online and target networks (dueling architecture)
        self.q_net = DuelingDQN(state_dim, action_dim).to(self.device)
        self.target_net = DuelingDQN(state_dim, action_dim).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)
        self.buffer = ReplayBuffer(capacity=buffer_size)

        # Epsilon schedule for exploration
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.steps_done: int = 0

    def _get_epsilon(self) -> float:
        # Linear decay from epsilon_start to epsilon_end
        frac = min(1.0, self.steps_done / self.epsilon_decay)
        return self.epsilon_start + frac * (self.epsilon_end - self.epsilon_start)

    def select_action(self, state: np.ndarray) -> int:
        self.steps_done += 1
        if random.random() < self._get_epsilon():
            return random.randrange(self.action_dim)
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            return int(self.q_net(state_t).argmax(dim=1).item())

    def _soft_update(self) -> None:
        # Polyak averaging for target network stability
        for tp, op in zip(
            self.target_net.parameters(), self.q_net.parameters()
        ):
            tp.data.copy_(self.tau * op.data + (1.0 - self.tau) * tp.data)

    def train_step(self) -> Optional[float]:
        if len(self.buffer) < self.batch_size:
            return None

        states, actions, rewards, next_states, dones = self.buffer.sample(
            self.batch_size
        )
        states = states.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        next_states = next_states.to(self.device)
        dones = dones.to(self.device)

        # Current Q-values for chosen actions
        q_values = self.q_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        # Double DQN: select actions with online net, evaluate with target net
        # This decouples action selection from evaluation, reducing overestimation
        with torch.no_grad():
            best_actions = self.q_net(next_states).argmax(dim=1, keepdim=True)
            next_q = self.target_net(next_states).gather(1, best_actions).squeeze(1)
            td_target = rewards + self.gamma * next_q * (1.0 - dones)

        loss = nn.functional.smooth_l1_loss(q_values, td_target)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping prevents catastrophic updates
        nn.utils.clip_grad_norm_(self.q_net.parameters(), max_norm=10.0)
        self.optimizer.step()
        self._soft_update()

        return loss.item()
```

### Training Loop

```python
import gymnasium as gym

def train_dqn(
    env_name: str = "CartPole-v1",
    num_episodes: int = 500,
    max_steps: int = 500,
) -> DQNAgent:
    env = gym.make(env_name)
    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.n

    agent = DQNAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        lr=3e-4,
        gamma=0.99,
        tau=0.005,
        epsilon_start=1.0,
        epsilon_end=0.01,
        epsilon_decay=10_000,
        buffer_size=50_000,
        batch_size=64,
    )

    episode_rewards: List[float] = []
    for episode in range(num_episodes):
        state, _ = env.reset()
        total_reward = 0.0

        for step in range(max_steps):
            action = agent.select_action(state)
            next_state, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated

            agent.buffer.push(state, action, reward, next_state, float(done))
            loss = agent.train_step()

            state = next_state
            total_reward += reward
            if done:
                break

        episode_rewards.append(total_reward)
        if (episode + 1) % 50 == 0:
            avg = np.mean(episode_rewards[-50:])
            eps = agent._get_epsilon()
            print(f"Episode {episode+1} | Avg reward: {avg:.1f} | Epsilon: {eps:.3f}")

    env.close()
    return agent
```

## Double DQN and Overestimation Bias

Standard DQN uses the same network to both select and evaluate actions in the TD target: max_a' Q(s', a'). This causes systematic **overestimation** because the max operator is positively biased when applied to noisy estimates. **Double DQN** decouples selection from evaluation: the online network selects the best action a* = argmax_a' Q_online(s', a'), while the target network evaluates it: Q_target(s', a*). This simple change dramatically reduces overestimation and is therefore considered a **best practice** for all DQN variants.

## Dueling Architecture

The **dueling DQN** architecture splits the network into two streams after the shared feature extractor: a **value stream** V(s) that estimates how good the current state is, and an **advantage stream** A(s, a) that estimates the relative benefit of each action. The final Q-value is Q(s, a) = V(s) + A(s, a) - mean(A). The advantage of this decomposition is that the network can learn state values without needing to estimate the effect of every action -- particularly useful in states where the choice of action does not matter much. However, a **pitfall** is that without the mean-centering trick, V and A are not uniquely identifiable (you could shift a constant between them), which makes learning unstable.

### Prioritized Experience Replay

**Prioritized experience replay** samples transitions proportional to their TD error magnitude, focusing learning on the most surprising experiences. This requires importance sampling weights to correct the resulting distribution bias.

```python
import numpy as np
from typing import Tuple

class PrioritizedReplayBuffer:
    # Sum-tree-based prioritized experience replay
    # Priorities are |TD_error| + epsilon to ensure non-zero probability
    def __init__(
        self,
        capacity: int = 100_000,
        alpha: float = 0.6,
        beta_start: float = 0.4,
        beta_frames: int = 100_000,
    ) -> None:
        self.capacity = capacity
        self.alpha = alpha  # priority exponent: 0 = uniform, 1 = full prioritization
        self.beta_start = beta_start
        self.beta_frames = beta_frames
        self.frame = 0
        self.pos = 0
        self.size = 0
        self.priorities = np.zeros(capacity, dtype=np.float64)
        self.buffer: list = [None] * capacity

    def push(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        max_prio = self.priorities[: self.size].max() if self.size > 0 else 1.0
        self.buffer[self.pos] = (state, action, reward, next_state, done)
        self.priorities[self.pos] = max_prio
        self.pos = (self.pos + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> Tuple:
        self.frame += 1
        beta = min(1.0, self.beta_start + self.frame * (1.0 - self.beta_start) / self.beta_frames)

        prios = self.priorities[: self.size] ** self.alpha
        probs = prios / prios.sum()
        indices = np.random.choice(self.size, batch_size, p=probs, replace=False)

        # Importance sampling weights to correct distribution bias
        weights = (self.size * probs[indices]) ** (-beta)
        weights = weights / weights.max()  # normalize for stability

        batch = [self.buffer[i] for i in indices]
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states), np.array(actions), np.array(rewards),
            np.array(next_states), np.array(dones),
            indices, weights.astype(np.float32),
        )

    def update_priorities(self, indices: np.ndarray, td_errors: np.ndarray) -> None:
        # Update priorities based on latest TD errors
        for idx, td_err in zip(indices, td_errors):
            self.priorities[idx] = abs(td_err) + 1e-6
```

## Convergence Theory and Practical Considerations

Tabular Q-learning converges to Q* given infinite visits to all state-action pairs and a decaying learning rate satisfying the Robbins-Monro conditions (sum alpha_t = infinity, sum alpha_t^2 < infinity). With function approximation, **no such guarantee exists**. The deadly triad means DQN can diverge in theory, though the combination of experience replay, target networks, and gradient clipping makes it work well in practice. **Prioritized experience replay** further improves convergence by sampling transitions with high TD error more frequently, though it requires importance sampling corrections to avoid bias.

**Common mistake**: using a learning rate that is too high. Because TD targets are noisy and non-stationary, RL requires much lower learning rates than supervised learning -- typically 1e-4 to 3e-4 for Adam.

## Summary and Key Takeaways

- **Bellman equation** provides the recursive structure that makes Q-learning possible; TD learning exploits this with one-step bootstrapped updates.
- **Experience replay** breaks correlations and enables data reuse; **target networks** with soft updates (tau ~0.005) stabilize the moving target.
- **Double DQN** reduces overestimation by decoupling action selection from evaluation -- always use it.
- **Dueling DQN** separates value and advantage streams, improving learning in states where action choice matters less.
- The **deadly triad** (function approximation + bootstrapping + off-policy) is the fundamental source of instability; replay and target nets are engineering mitigations, not theoretical solutions.
- **Best practice**: start with moderate buffer sizes (50k-100k), use linear epsilon decay over 10k-50k steps, clip gradients, and monitor TD error magnitude for signs of divergence.
"""
    ),

    # --- 2. Policy Gradient Methods and PPO ---
    (
        "reinforcement-learning/policy-gradients-reinforce-gae-ppo-actor-critic",
        "Explain policy gradient methods comprehensively including the REINFORCE algorithm, advantage estimation with GAE (Generalized Advantage Estimation), Proximal Policy Optimization with clipped surrogate objective, actor-critic architecture, variance reduction techniques, and provide a complete PyTorch PPO implementation with value function baseline and advantage normalization.",
        r"""
# Policy Gradient Methods: From REINFORCE to PPO

## Why Policy Gradients?

Value-based methods like DQN learn a value function and derive a policy implicitly (take the action with highest Q-value). This works well for discrete action spaces, but struggles with continuous actions (you cannot enumerate all possible actions to find the argmax). **Policy gradient** methods instead directly parameterize the policy pi_theta(a|s) and optimize it by gradient ascent on the expected return. This approach has several advantages: it naturally handles continuous action spaces, can learn stochastic policies (important for partially observable environments), and the policy parameterization can encode useful inductive biases. The **trade-off** is higher variance in gradient estimates compared to value-based methods, which necessitates careful variance reduction techniques.

## REINFORCE: The Foundation

The policy gradient theorem states that the gradient of the expected return J(theta) with respect to policy parameters theta is:

nabla J(theta) = E[sum_t nabla log pi_theta(a_t|s_t) * G_t]

where G_t is the return (discounted cumulative reward) from time step t onward. **REINFORCE** implements this directly: collect a full episode, compute returns for each step, and update the policy. However, raw REINFORCE has extremely high variance because G_t includes the randomness of the entire future trajectory. A **common mistake** is using REINFORCE without a baseline -- the vanilla algorithm is nearly unusable in practice because the gradient variance is so large that learning is extremely slow.

### Variance Reduction with Baselines

The key insight is that we can subtract any function b(s) from the return without introducing bias (because E[nabla log pi * b(s)] = 0 for any state-dependent baseline). The optimal baseline is close to the expected return V(s), which motivates the **actor-critic** architecture: the **actor** is the policy pi_theta(a|s), and the **critic** is the value function V_phi(s) that serves as the baseline. The advantage A(s, a) = Q(s, a) - V(s) tells us how much better action a is compared to the average -- using this instead of raw returns dramatically reduces variance.

## Generalized Advantage Estimation (GAE)

Computing the advantage exactly requires knowing Q(s, a), which we do not have. We can estimate it using TD residuals: delta_t = r_t + gamma * V(s_{t+1}) - V(s_t). **GAE** combines multi-step TD residuals using an exponentially-weighted average controlled by a parameter lambda:

A_GAE_t = sum_{l=0}^{T-t} (gamma * lambda)^l * delta_{t+l}

When lambda = 0, GAE uses only the one-step TD residual (low variance, high bias). When lambda = 1, it reduces to the Monte Carlo return minus the baseline (high variance, low bias). The **best practice** is lambda = 0.95, which provides a good bias-variance **trade-off**. This parameter is therefore one of the most important hyperparameters in policy gradient methods -- more important than the learning rate in many cases.

## PPO: Proximal Policy Optimization

Vanilla policy gradients suffer from a catastrophic problem: a single large gradient step can destroy the policy, and because RL data collection depends on the current policy, a bad update creates a doom loop of bad data leading to worse policies. **Trust Region Policy Optimization (TRPO)** addressed this by constraining the KL divergence between old and new policies, but it requires expensive second-order optimization. **PPO** achieves similar stability with a simple clipped surrogate objective:

L_clip = E[min(r_t * A_t, clip(r_t, 1-eps, 1+eps) * A_t)]

where r_t = pi_theta(a_t|s_t) / pi_theta_old(a_t|s_t) is the probability ratio between new and old policies, and eps is typically 0.2. The clipping prevents the ratio from moving too far from 1.0, which implicitly constrains the policy update. When the advantage is positive (good action), the objective clips r_t from above at 1+eps, preventing over-reinforcement. When the advantage is negative (bad action), it clips from below at 1-eps. This asymmetric clipping is the core innovation and makes PPO remarkably stable.

### Complete PPO Implementation

```python
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from typing import List, Tuple, Dict, Optional

class ActorCritic(nn.Module):
    # Shared-backbone actor-critic with separate policy and value heads
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden: int = 256,
        continuous: bool = False,
    ) -> None:
        super().__init__()
        self.continuous = continuous

        # Shared feature extractor
        self.backbone = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )

        # Policy head (actor)
        if continuous:
            self.mean_head = nn.Linear(hidden, action_dim)
            # Learnable log standard deviation
            self.log_std = nn.Parameter(torch.zeros(action_dim))
        else:
            self.policy_head = nn.Linear(hidden, action_dim)

        # Value head (critic)
        self.value_head = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.Tanh(),
            nn.Linear(hidden // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.distributions.Distribution, torch.Tensor]:
        features = self.backbone(x)

        if self.continuous:
            mean = self.mean_head(features)
            std = self.log_std.exp().expand_as(mean)
            dist = torch.distributions.Normal(mean, std)
        else:
            logits = self.policy_head(features)
            dist = torch.distributions.Categorical(logits=logits)

        value = self.value_head(features).squeeze(-1)
        return dist, value


class RolloutBuffer:
    # Stores trajectory data for PPO updates
    def __init__(self) -> None:
        self.states: List[np.ndarray] = []
        self.actions: List[np.ndarray] = []
        self.rewards: List[float] = []
        self.dones: List[bool] = []
        self.log_probs: List[float] = []
        self.values: List[float] = []

    def store(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        done: bool,
        log_prob: float,
        value: float,
    ) -> None:
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.dones.append(done)
        self.log_probs.append(log_prob)
        self.values.append(value)

    def compute_gae(
        self,
        last_value: float,
        gamma: float = 0.99,
        lam: float = 0.95,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # Compute GAE advantages and discounted returns
        advantages: List[float] = []
        gae = 0.0
        values = self.values + [last_value]

        for t in reversed(range(len(self.rewards))):
            mask = 1.0 - float(self.dones[t])
            delta = self.rewards[t] + gamma * values[t + 1] * mask - values[t]
            gae = delta + gamma * lam * mask * gae
            advantages.insert(0, gae)

        adv_tensor = torch.FloatTensor(advantages)
        returns = adv_tensor + torch.FloatTensor(self.values)
        return adv_tensor, returns

    def clear(self) -> None:
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.dones.clear()
        self.log_probs.clear()
        self.values.clear()


class PPOAgent:
    # PPO agent with clipped surrogate objective, GAE, and entropy bonus
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr: float = 3e-4,
        gamma: float = 0.99,
        lam: float = 0.95,
        clip_eps: float = 0.2,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        ppo_epochs: int = 10,
        mini_batch_size: int = 64,
        continuous: bool = False,
        device: str = "cpu",
    ) -> None:
        self.gamma = gamma
        self.lam = lam
        self.clip_eps = clip_eps
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.max_grad_norm = max_grad_norm
        self.ppo_epochs = ppo_epochs
        self.mini_batch_size = mini_batch_size
        self.device = torch.device(device)

        self.policy = ActorCritic(
            state_dim, action_dim, continuous=continuous
        ).to(self.device)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=lr)
        self.buffer = RolloutBuffer()

    def select_action(
        self, state: np.ndarray
    ) -> Tuple[np.ndarray, float, float]:
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            dist, value = self.policy(state_t)
            action = dist.sample()
            log_prob = dist.log_prob(action).sum(-1)

        return (
            action.cpu().numpy().flatten(),
            log_prob.item(),
            value.item(),
        )

    def update(self, last_value: float) -> Dict[str, float]:
        advantages, returns = self.buffer.compute_gae(
            last_value, self.gamma, self.lam
        )
        # Advantage normalization -- critical for stable training
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        states = torch.FloatTensor(np.array(self.buffer.states)).to(self.device)
        actions = torch.FloatTensor(np.array(self.buffer.actions)).to(self.device)
        old_log_probs = torch.FloatTensor(self.buffer.log_probs).to(self.device)
        returns = returns.to(self.device)
        advantages = advantages.to(self.device)

        total_pg_loss = 0.0
        total_v_loss = 0.0
        total_entropy = 0.0
        n_updates = 0

        for _ in range(self.ppo_epochs):
            indices = np.random.permutation(len(self.buffer.states))
            for start in range(0, len(indices), self.mini_batch_size):
                end = start + self.mini_batch_size
                idx = indices[start:end]

                dist, values = self.policy(states[idx])
                new_log_probs = dist.log_prob(actions[idx]).sum(-1)
                entropy = dist.entropy().sum(-1).mean()

                # Clipped surrogate objective
                ratio = torch.exp(new_log_probs - old_log_probs[idx])
                adv_batch = advantages[idx]
                surr1 = ratio * adv_batch
                surr2 = torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps) * adv_batch
                pg_loss = -torch.min(surr1, surr2).mean()

                # Value function loss
                v_loss = nn.functional.mse_loss(values, returns[idx])

                # Combined loss with entropy bonus
                loss = pg_loss + self.value_coef * v_loss - self.entropy_coef * entropy

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(
                    self.policy.parameters(), self.max_grad_norm
                )
                self.optimizer.step()

                total_pg_loss += pg_loss.item()
                total_v_loss += v_loss.item()
                total_entropy += entropy.item()
                n_updates += 1

        self.buffer.clear()
        return {
            "pg_loss": total_pg_loss / n_updates,
            "v_loss": total_v_loss / n_updates,
            "entropy": total_entropy / n_updates,
        }
```

### PPO Training Loop

```python
import gymnasium as gym

def train_ppo(
    env_name: str = "CartPole-v1",
    total_timesteps: int = 100_000,
    rollout_length: int = 2048,
) -> PPOAgent:
    env = gym.make(env_name)
    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.n

    agent = PPOAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        lr=3e-4,
        gamma=0.99,
        lam=0.95,
        clip_eps=0.2,
        entropy_coef=0.01,
        ppo_epochs=10,
        mini_batch_size=64,
    )

    state, _ = env.reset()
    episode_reward = 0.0
    episode_rewards: List[float] = []
    timestep = 0

    while timestep < total_timesteps:
        for _ in range(rollout_length):
            action, log_prob, value = agent.select_action(state)
            next_state, reward, terminated, truncated, _ = env.step(int(action[0]))
            done = terminated or truncated

            agent.buffer.store(state, action, reward, done, log_prob, value)
            state = next_state
            episode_reward += reward
            timestep += 1

            if done:
                episode_rewards.append(episode_reward)
                episode_reward = 0.0
                state, _ = env.reset()

        # Bootstrap value for incomplete trajectory
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0)
            _, last_value = agent.policy(state_t)

        metrics = agent.update(last_value.item())

        if len(episode_rewards) > 0:
            print(
                f"Step {timestep} | "
                f"Avg reward: {np.mean(episode_rewards[-20:]):.1f} | "
                f"PG loss: {metrics['pg_loss']:.4f} | "
                f"Entropy: {metrics['entropy']:.4f}"
            )

    env.close()
    return agent
```

## Variance Reduction Deep Dive

Beyond baselines, several techniques reduce gradient variance in policy gradient methods:

1. **Advantage normalization**: Normalizing advantages to zero mean and unit variance across each mini-batch is a **best practice** that prevents large-magnitude advantages from dominating the gradient. Without it, a single high-reward trajectory can cause catastrophic policy updates.

2. **Entropy bonus**: Adding an entropy term H(pi) to the objective encourages exploration by penalizing deterministic policies. The **trade-off** is between exploration (high entropy coefficient) and exploitation (low coefficient). A **pitfall** is setting the entropy coefficient too high, which prevents the policy from converging to a deterministic optimum.

3. **Reward normalization**: Running estimates of reward mean and variance can stabilize training, especially when reward scales vary across environments.

4. **Gradient clipping**: PPO clips gradients by global norm (typically 0.5), which prevents individual large batches from destabilizing training. This is particularly important because policy gradient estimates have heavy-tailed distributions.

### Running Reward Normalization

```python
import torch
import numpy as np
from typing import Optional

class RunningRewardNormalizer:
    # Tracks running mean and variance of rewards using Welford's algorithm
    # Normalizes rewards to zero mean and unit variance for stable training
    def __init__(self, gamma: float = 0.99, clip: float = 10.0) -> None:
        self.gamma = gamma
        self.clip = clip
        self.mean: float = 0.0
        self.var: float = 1.0
        self.count: int = 0
        self.ret: float = 0.0  # discounted return tracker

    def update(self, reward: float, done: bool) -> float:
        # Update running return estimate
        self.ret = reward + self.gamma * self.ret * (1.0 - float(done))

        # Welford's online algorithm for mean and variance
        self.count += 1
        delta = self.ret - self.mean
        self.mean += delta / self.count
        delta2 = self.ret - self.mean
        self.var += (delta * delta2 - self.var) / self.count

        if done:
            self.ret = 0.0

        # Normalize and clip the reward
        std = max(np.sqrt(self.var), 1e-8)
        return float(np.clip(reward / std, -self.clip, self.clip))

    def normalize_batch(self, rewards: torch.Tensor) -> torch.Tensor:
        std = max(np.sqrt(self.var), 1e-8)
        return torch.clamp(rewards / std, -self.clip, self.clip)
```

## Summary and Key Takeaways

- **REINFORCE** is the simplest policy gradient but has high variance; always use a **value function baseline** to reduce it.
- **GAE** with lambda=0.95 provides the best bias-variance **trade-off** for advantage estimation -- it is more important to tune lambda than the learning rate.
- **PPO's clipped surrogate** prevents catastrophic policy updates by bounding the probability ratio, making it the most robust and widely-used policy gradient method.
- **Advantage normalization** is a critical and often overlooked technique: without it, PPO can be highly unstable across environments with different reward scales.
- The **actor-critic** architecture with a shared backbone is parameter-efficient but can cause interference between policy and value gradients; therefore, some practitioners use separate networks.
- **Common mistake**: running too few PPO epochs (use 3-10) or using mini-batches that are too small (64-256 is typical for discrete actions).
"""
    ),

    # --- 3. Multi-Agent Reinforcement Learning (MARL) ---
    (
        "reinforcement-learning/multi-agent-rl-ctde-qmix-emergent-communication",
        "Explain multi-agent reinforcement learning covering cooperative versus competitive settings, independent learners and non-stationarity, centralized training with decentralized execution (CTDE), QMIX value decomposition, emergent communication, reward shaping, and provide complete implementations of independent Q-learning agents and a QMIX mixing network in PyTorch with analysis of scalability and coordination challenges.",
        r"""
# Multi-Agent Reinforcement Learning: From Independent Learners to QMIX

## The Multi-Agent Challenge

Single-agent RL assumes a stationary environment -- the transition dynamics do not change over time. In **multi-agent reinforcement learning (MARL)**, this assumption breaks catastrophically because each agent's environment includes the other agents, whose policies are changing simultaneously. From any single agent's perspective, the environment is **non-stationary**, which violates the foundational Markov property that most RL algorithms rely on. This is the central challenge of MARL and the reason why naively applying single-agent algorithms to multi-agent problems often fails.

MARL settings fall into three categories: **cooperative** (all agents share a common reward and must coordinate), **competitive** (zero-sum games where one agent's gain is another's loss), and **mixed** (agents have individual rewards that may partially align). The cooperative setting is most common in practical applications like robot swarms, warehouse logistics, and StarCraft micromanagement, and it is where value decomposition methods like QMIX shine.

## Independent Learners: Simple but Flawed

The simplest MARL approach is **independent Q-learning (IQL)**: give each agent its own Q-network, let it observe only its local observation, and train it as if the other agents were part of the environment. This is appealing because it scales linearly with the number of agents and requires no communication infrastructure. However, the **common mistake** of treating IQL as a reliable baseline ignores its fundamental flaw: non-stationarity. Because each agent's policy changes during training, the transition dynamics from any single agent's perspective are constantly shifting, which means the experience replay buffer contains stale transitions that no longer reflect the current environment.

Despite these theoretical problems, IQL works surprisingly well in practice for many cooperative tasks, particularly when agents are loosely coupled. The reason is that with enough exploration and a slow learning rate, the non-stationarity is mild enough that each agent can track the changing environment. **Best practice**: when using IQL, share network parameters across homogeneous agents (parameter sharing) to improve sample efficiency and encourage symmetric policies.

### Independent Q-Learning Implementation

```python
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from typing import List, Tuple, Dict, Optional

class IndependentQNetwork(nn.Module):
    # Q-network for a single agent operating on local observations
    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, action_dim),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.net(obs)


class SharedReplayBuffer:
    # Joint replay buffer storing transitions for all agents
    def __init__(self, capacity: int = 100_000) -> None:
        self.buffer: deque = deque(maxlen=capacity)

    def push(
        self,
        observations: List[np.ndarray],
        actions: List[int],
        reward: float,
        next_observations: List[np.ndarray],
        done: bool,
    ) -> None:
        self.buffer.append((observations, actions, reward, next_observations, done))

    def sample(self, batch_size: int) -> Tuple:
        batch = random.sample(self.buffer, batch_size)
        obs_batch, act_batch, rew_batch, next_obs_batch, done_batch = zip(*batch)
        return obs_batch, act_batch, rew_batch, next_obs_batch, done_batch

    def __len__(self) -> int:
        return len(self.buffer)


class IQLSystem:
    # Independent Q-Learning with optional parameter sharing
    def __init__(
        self,
        n_agents: int,
        obs_dim: int,
        action_dim: int,
        lr: float = 1e-3,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: int = 50_000,
        share_params: bool = True,
        device: str = "cpu",
    ) -> None:
        self.n_agents = n_agents
        self.action_dim = action_dim
        self.gamma = gamma
        self.device = torch.device(device)
        self.share_params = share_params
        self.steps_done = 0
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay

        if share_params:
            # All agents share one network -- massive sample efficiency gain
            self.q_net = IndependentQNetwork(obs_dim, action_dim).to(self.device)
            self.target_net = IndependentQNetwork(obs_dim, action_dim).to(self.device)
            self.target_net.load_state_dict(self.q_net.state_dict())
            self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)
        else:
            self.q_nets = nn.ModuleList(
                [IndependentQNetwork(obs_dim, action_dim).to(self.device) for _ in range(n_agents)]
            )
            self.target_nets = nn.ModuleList(
                [IndependentQNetwork(obs_dim, action_dim).to(self.device) for _ in range(n_agents)]
            )
            for i in range(n_agents):
                self.target_nets[i].load_state_dict(self.q_nets[i].state_dict())
            self.optimizers = [optim.Adam(net.parameters(), lr=lr) for net in self.q_nets]

        self.buffer = SharedReplayBuffer()

    def _get_epsilon(self) -> float:
        frac = min(1.0, self.steps_done / self.epsilon_decay)
        return self.epsilon_start + frac * (self.epsilon_end - self.epsilon_start)

    def select_actions(self, observations: List[np.ndarray]) -> List[int]:
        self.steps_done += 1
        epsilon = self._get_epsilon()
        actions: List[int] = []

        for i, obs in enumerate(observations):
            if random.random() < epsilon:
                actions.append(random.randrange(self.action_dim))
            else:
                with torch.no_grad():
                    obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
                    q_net = self.q_net if self.share_params else self.q_nets[i]
                    q_vals = q_net(obs_t)
                    actions.append(int(q_vals.argmax(dim=1).item()))

        return actions

    def train_step(self, batch_size: int = 64) -> Optional[float]:
        if len(self.buffer) < batch_size:
            return None

        obs_b, act_b, rew_b, next_obs_b, done_b = self.buffer.sample(batch_size)
        total_loss = 0.0

        for i in range(self.n_agents):
            obs_i = torch.FloatTensor(
                np.array([obs_b[b][i] for b in range(batch_size)])
            ).to(self.device)
            act_i = torch.LongTensor(
                [act_b[b][i] for b in range(batch_size)]
            ).to(self.device)
            rew_i = torch.FloatTensor(
                [rew_b[b] for b in range(batch_size)]
            ).to(self.device)
            next_obs_i = torch.FloatTensor(
                np.array([next_obs_b[b][i] for b in range(batch_size)])
            ).to(self.device)
            done_i = torch.FloatTensor(
                [float(done_b[b]) for b in range(batch_size)]
            ).to(self.device)

            q_net = self.q_net if self.share_params else self.q_nets[i]
            target_net = self.target_net if self.share_params else self.target_nets[i]
            optimizer = self.optimizer if self.share_params else self.optimizers[i]

            q_values = q_net(obs_i).gather(1, act_i.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                next_q = target_net(next_obs_i).max(dim=1)[0]
                td_target = rew_i + self.gamma * next_q * (1.0 - done_i)

            loss = nn.functional.mse_loss(q_values, td_target)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        return total_loss / self.n_agents
```

## Centralized Training with Decentralized Execution (CTDE)

The key insight of **CTDE** is that during training we have access to global information (all agents' observations, the global state), but during deployment each agent can only access its local observation. Therefore, we can use centralized information to train better policies while maintaining decentralized execution. This is the **best practice** paradigm for cooperative MARL because it sidesteps non-stationarity during training without requiring communication at deployment time.

**QMIX** is the most influential CTDE algorithm for cooperative settings. It learns individual agent Q-values Q_i(o_i, a_i) that can be used for decentralized action selection, while a **mixing network** combines them into a joint Q_total that is trained against the team reward. The critical constraint is **monotonicity**: dQ_total/dQ_i >= 0 for all agents, which ensures that the argmax of Q_total decomposes into per-agent argmaxes. This is enforced by using non-negative weights in the mixing network, generated by hypernetworks conditioned on the global state.

### QMIX Implementation

```python
class QMIXMixingNetwork(nn.Module):
    # Monotonic mixing network that combines agent Q-values
    # Hypernetworks generate weights conditioned on global state
    def __init__(
        self,
        n_agents: int,
        state_dim: int,
        mixing_embed_dim: int = 32,
    ) -> None:
        super().__init__()
        self.n_agents = n_agents

        # Hypernetwork for first layer weights (must be non-negative)
        self.hyper_w1 = nn.Sequential(
            nn.Linear(state_dim, mixing_embed_dim),
            nn.ReLU(),
            nn.Linear(mixing_embed_dim, n_agents * mixing_embed_dim),
        )
        self.hyper_b1 = nn.Linear(state_dim, mixing_embed_dim)

        # Hypernetwork for second layer weights (must be non-negative)
        self.hyper_w2 = nn.Sequential(
            nn.Linear(state_dim, mixing_embed_dim),
            nn.ReLU(),
            nn.Linear(mixing_embed_dim, mixing_embed_dim),
        )
        self.hyper_b2 = nn.Sequential(
            nn.Linear(state_dim, mixing_embed_dim),
            nn.ReLU(),
            nn.Linear(mixing_embed_dim, 1),
        )

        self.mixing_embed_dim = mixing_embed_dim

    def forward(
        self,
        agent_q_values: torch.Tensor,
        global_state: torch.Tensor,
    ) -> torch.Tensor:
        # agent_q_values: (batch, n_agents)
        # global_state: (batch, state_dim)
        batch_size = agent_q_values.size(0)

        # Generate non-negative weights via abs()
        w1 = torch.abs(self.hyper_w1(global_state))
        w1 = w1.view(batch_size, self.n_agents, self.mixing_embed_dim)
        b1 = self.hyper_b1(global_state).unsqueeze(1)

        # First mixing layer
        q_in = agent_q_values.unsqueeze(1)  # (batch, 1, n_agents)
        hidden = torch.bmm(q_in, w1) + b1   # (batch, 1, embed)
        hidden = torch.relu(hidden)

        # Second mixing layer
        w2 = torch.abs(self.hyper_w2(global_state))
        w2 = w2.view(batch_size, self.mixing_embed_dim, 1)
        b2 = self.hyper_b2(global_state).unsqueeze(1)

        q_total = torch.bmm(hidden, w2) + b2  # (batch, 1, 1)
        return q_total.squeeze(-1).squeeze(-1)


class QMIXSystem:
    # Full QMIX system with per-agent networks and mixing network
    def __init__(
        self,
        n_agents: int,
        obs_dim: int,
        state_dim: int,
        action_dim: int,
        lr: float = 5e-4,
        gamma: float = 0.99,
        device: str = "cpu",
    ) -> None:
        self.n_agents = n_agents
        self.action_dim = action_dim
        self.gamma = gamma
        self.device = torch.device(device)

        # Individual agent networks (shared parameters)
        self.agent_net = IndependentQNetwork(obs_dim, action_dim).to(self.device)
        self.target_agent_net = IndependentQNetwork(obs_dim, action_dim).to(self.device)
        self.target_agent_net.load_state_dict(self.agent_net.state_dict())

        # Mixing networks
        self.mixer = QMIXMixingNetwork(n_agents, state_dim).to(self.device)
        self.target_mixer = QMIXMixingNetwork(n_agents, state_dim).to(self.device)
        self.target_mixer.load_state_dict(self.mixer.state_dict())

        params = list(self.agent_net.parameters()) + list(self.mixer.parameters())
        self.optimizer = optim.Adam(params, lr=lr)

    def compute_q_total(
        self,
        observations: torch.Tensor,
        actions: torch.Tensor,
        global_state: torch.Tensor,
        use_target: bool = False,
    ) -> torch.Tensor:
        # observations: (batch, n_agents, obs_dim)
        # actions: (batch, n_agents)
        batch_size = observations.size(0)
        net = self.target_agent_net if use_target else self.agent_net
        mixer = self.target_mixer if use_target else self.mixer

        agent_qs: List[torch.Tensor] = []
        for i in range(self.n_agents):
            q_vals = net(observations[:, i, :])  # (batch, action_dim)
            q_a = q_vals.gather(1, actions[:, i].unsqueeze(1)).squeeze(1)
            agent_qs.append(q_a)

        agent_q_values = torch.stack(agent_qs, dim=1)  # (batch, n_agents)
        return mixer(agent_q_values, global_state)
```

## Emergent Communication and Reward Shaping

A fascinating phenomenon in cooperative MARL is **emergent communication**: when agents are given a communication channel (a discrete or continuous message they can send at each step), they spontaneously develop protocols to share information. However, a **pitfall** is that emergent protocols are often brittle and environment-specific -- they do not transfer to new tasks or agent configurations.

**Reward shaping** is the practice of augmenting the environment reward with additional signals to guide learning. In MARL, shaped rewards can encourage cooperation (bonus for staying near teammates), exploration (curiosity-based rewards), or coordination (bonus for complementary actions). The **trade-off** is that poorly designed shaped rewards can create local optima that prevent agents from finding the true optimal policy. **Best practice**: use potential-based reward shaping (Phi(s') - Phi(s)) to guarantee that the optimal policy under the shaped reward is the same as under the original reward.

### Potential-Based Reward Shaping

```python
import torch
import torch.nn as nn
import numpy as np
from typing import List

class PotentialBasedShaping:
    # Implements potential-based reward shaping (Ng et al., 1999)
    # Guarantees optimal policy invariance: the shaped policy is
    # identical to the optimal policy under the original reward
    def __init__(
        self,
        potential_fn: nn.Module,
        gamma: float = 0.99,
        shaping_weight: float = 1.0,
    ) -> None:
        self.potential_fn = potential_fn
        self.gamma = gamma
        self.shaping_weight = shaping_weight

    def compute_shaped_reward(
        self,
        reward: float,
        state: np.ndarray,
        next_state: np.ndarray,
        done: bool,
    ) -> float:
        # F(s, s') = gamma * Phi(s') - Phi(s)
        # This guarantees the optimal policy is preserved
        with torch.no_grad():
            s = torch.FloatTensor(state).unsqueeze(0)
            ns = torch.FloatTensor(next_state).unsqueeze(0)
            phi_s = self.potential_fn(s).item()
            phi_ns = self.potential_fn(ns).item() if not done else 0.0
        shaping = self.gamma * phi_ns - phi_s
        return reward + self.shaping_weight * shaping


class CooperativeDistancePotential(nn.Module):
    # Potential function that encourages agents to stay close
    # Useful for cooperative tasks requiring spatial coordination
    def __init__(self, n_agents: int, pos_dim: int = 2) -> None:
        super().__init__()
        self.n_agents = n_agents
        self.pos_dim = pos_dim

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        # Extract agent positions from state and compute negative mean distance
        # Higher potential when agents are closer together
        positions = state[:, :self.n_agents * self.pos_dim].view(
            -1, self.n_agents, self.pos_dim
        )
        # Pairwise distances between all agents
        dists: List[torch.Tensor] = []
        for i in range(self.n_agents):
            for j in range(i + 1, self.n_agents):
                d = torch.norm(positions[:, i] - positions[:, j], dim=-1)
                dists.append(d)
        mean_dist = torch.stack(dists, dim=-1).mean(dim=-1)
        # Negative distance as potential: closer agents = higher potential
        return -mean_dist
```

## Summary and Key Takeaways

- **Non-stationarity** is the fundamental challenge of MARL; each agent sees a changing environment because other agents' policies evolve during training.
- **Independent Q-learning** is simple and scalable but theoretically unsound; parameter sharing among homogeneous agents dramatically improves sample efficiency.
- **CTDE** is the dominant paradigm: train with global information, execute with local observations only.
- **QMIX** enforces monotonicity through non-negative mixing weights generated by hypernetworks, enabling tractable decentralized action selection from joint Q-values.
- **Emergent communication** is possible but fragile; therefore, structured communication protocols are preferred for safety-critical applications.
- **Common mistake**: using dense team rewards without per-agent credit assignment, which causes the **lazy agent** problem where some agents learn to do nothing while others carry the team.
"""
    ),

    # --- 4. Model-Based RL and World Models ---
    (
        "reinforcement-learning/model-based-rl-dyna-muzero-dreamer-world-models",
        "Explain model-based reinforcement learning in detail including learned dynamics models, the Dyna architecture with planning, MuZero's learned latent planning, Dreamer's latent world model, model exploitation pitfalls, ensemble disagreement for uncertainty, and provide a complete Dyna-Q implementation with learned transition model, planning steps, and model error detection in PyTorch.",
        r"""
# Model-Based Reinforcement Learning: Learning and Leveraging World Models

## The Case for Learning a Model

Model-free RL methods like DQN and PPO treat the environment as a black box: the agent interacts, receives rewards, and learns entirely from real experience. This is **sample inefficient** -- Atari DQN requires 200 million frames (equivalent to 38 days of real-time play) to achieve human-level performance. **Model-based RL** addresses this by learning a model of the environment's dynamics f(s, a) -> (s', r) and using it to generate synthetic experience for planning or policy improvement. The core promise is dramatically better sample efficiency because one real transition can inform the model, which then generates many synthetic transitions for training.

The fundamental **trade-off** is between sample efficiency and model accuracy. A learned model is never perfect, and planning with an inaccurate model can lead to policies that exploit model errors rather than maximizing true environment reward. This is the **model exploitation problem**, and it is the central challenge in model-based RL. However, when managed properly through uncertainty estimation and conservative planning, model-based methods can achieve 10-100x better sample efficiency than their model-free counterparts.

## The Dyna Architecture

**Dyna** (Sutton, 1991) is the foundational framework for combining model-free learning with model-based planning. The idea is simple and elegant: after each real environment interaction, (1) update the Q-function using the real transition (model-free step), (2) update the learned dynamics model using the real transition, and (3) perform k **planning steps** by sampling states from experience, simulating transitions using the learned model, and updating the Q-function using these simulated transitions.

The number of planning steps k controls the sample efficiency gain: more planning extracts more value from each real interaction but also increases the risk of model exploitation. A **common mistake** is setting k too high early in training when the model is still inaccurate, which causes the agent to learn a policy that exploits model errors. **Best practice**: start with k=1-5 and increase as the model improves, or use model uncertainty to adaptively control the planning horizon.

### Complete Dyna-Q Implementation

```python
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from typing import Tuple, List, Optional, Dict

class LearnedDynamicsModel(nn.Module):
    # Predicts next state and reward given current state and action
    # Uses an ensemble of models for uncertainty estimation
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden: int = 256,
        n_ensemble: int = 5,
    ) -> None:
        super().__init__()
        self.n_ensemble = n_ensemble
        self.state_dim = state_dim

        # Ensemble of dynamics models for disagreement-based uncertainty
        self.models = nn.ModuleList()
        for _ in range(n_ensemble):
            model = nn.Sequential(
                nn.Linear(state_dim + action_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, state_dim + 1),  # next_state_delta + reward
            )
            self.models.append(model)

    def forward(
        self, state: torch.Tensor, action_onehot: torch.Tensor, model_idx: int = 0
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        x = torch.cat([state, action_onehot], dim=-1)
        output = self.models[model_idx](x)
        # Predict delta (residual) for next state -- more stable than absolute
        next_state_delta = output[:, :self.state_dim]
        reward = output[:, self.state_dim:]
        next_state = state + next_state_delta
        return next_state, reward.squeeze(-1)

    def predict_with_uncertainty(
        self, state: torch.Tensor, action_onehot: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, float]:
        # Run all ensemble members and compute disagreement
        next_states: List[torch.Tensor] = []
        rewards: List[torch.Tensor] = []

        for i in range(self.n_ensemble):
            ns, r = self.forward(state, action_onehot, model_idx=i)
            next_states.append(ns)
            rewards.append(r)

        ns_stack = torch.stack(next_states)  # (n_ensemble, batch, state_dim)
        r_stack = torch.stack(rewards)       # (n_ensemble, batch)

        # Mean prediction
        ns_mean = ns_stack.mean(dim=0)
        r_mean = r_stack.mean(dim=0)

        # Disagreement as uncertainty: variance across ensemble members
        disagreement = ns_stack.var(dim=0).mean().item()

        return ns_mean, r_mean, disagreement


class DynaQAgent:
    # Dyna-Q with learned ensemble dynamics model,
    # planning steps, and model error detection
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr_q: float = 1e-3,
        lr_model: float = 1e-3,
        gamma: float = 0.99,
        planning_steps: int = 5,
        disagreement_threshold: float = 0.1,
        buffer_size: int = 50_000,
        batch_size: int = 64,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: int = 20_000,
        device: str = "cpu",
    ) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.planning_steps = planning_steps
        self.disagreement_threshold = disagreement_threshold
        self.batch_size = batch_size
        self.device = torch.device(device)
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.steps_done = 0

        # Q-network (model-free component)
        self.q_net = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, action_dim),
        ).to(self.device)
        self.q_optimizer = optim.Adam(self.q_net.parameters(), lr=lr_q)

        # Learned dynamics model (ensemble)
        self.dynamics = LearnedDynamicsModel(
            state_dim, action_dim, n_ensemble=5
        ).to(self.device)
        self.model_optimizer = optim.Adam(self.dynamics.parameters(), lr=lr_model)

        # Replay buffer for real transitions
        self.buffer: deque = deque(maxlen=buffer_size)

    def _get_epsilon(self) -> float:
        frac = min(1.0, self.steps_done / self.epsilon_decay)
        return self.epsilon_start + frac * (self.epsilon_end - self.epsilon_start)

    def _action_onehot(self, actions: torch.Tensor) -> torch.Tensor:
        return nn.functional.one_hot(
            actions, num_classes=self.action_dim
        ).float()

    def select_action(self, state: np.ndarray) -> int:
        self.steps_done += 1
        if random.random() < self._get_epsilon():
            return random.randrange(self.action_dim)
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            return int(self.q_net(state_t).argmax(dim=1).item())

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        self.buffer.append((state, action, reward, next_state, done))

    def _update_q(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        rewards: torch.Tensor,
        next_states: torch.Tensor,
        dones: torch.Tensor,
    ) -> float:
        q_values = self.q_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            next_q = self.q_net(next_states).max(dim=1)[0]
            targets = rewards + self.gamma * next_q * (1.0 - dones)

        loss = nn.functional.mse_loss(q_values, targets)
        self.q_optimizer.zero_grad()
        loss.backward()
        self.q_optimizer.step()
        return loss.item()

    def _update_model(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        rewards: torch.Tensor,
        next_states: torch.Tensor,
    ) -> float:
        action_oh = self._action_onehot(actions)
        total_loss = 0.0

        for i in range(self.dynamics.n_ensemble):
            pred_ns, pred_r = self.dynamics(states, action_oh, model_idx=i)
            ns_loss = nn.functional.mse_loss(pred_ns, next_states)
            r_loss = nn.functional.mse_loss(pred_r, rewards)
            loss = ns_loss + r_loss
            total_loss += loss.item()

        # Train all ensemble members jointly
        action_oh = self._action_onehot(actions)
        self.model_optimizer.zero_grad()
        combined_loss = torch.tensor(0.0, device=self.device)
        for i in range(self.dynamics.n_ensemble):
            pred_ns, pred_r = self.dynamics(states, action_oh, model_idx=i)
            combined_loss = combined_loss + nn.functional.mse_loss(pred_ns, next_states) + nn.functional.mse_loss(pred_r, rewards)
        combined_loss.backward()
        self.model_optimizer.step()

        return total_loss / self.dynamics.n_ensemble

    def _planning_step(self) -> Optional[float]:
        # Generate synthetic transitions using the learned model
        # Only use predictions where ensemble disagreement is low
        if len(self.buffer) < self.batch_size:
            return None

        batch = random.sample(list(self.buffer), self.batch_size)
        states = torch.FloatTensor(np.array([t[0] for t in batch])).to(self.device)

        # Random actions for diversity
        actions = torch.randint(0, self.action_dim, (self.batch_size,)).to(self.device)
        action_oh = self._action_onehot(actions)

        with torch.no_grad():
            pred_ns, pred_r, disagreement = self.dynamics.predict_with_uncertainty(
                states, action_oh
            )

        # Model error detection: skip planning when model is uncertain
        if disagreement > self.disagreement_threshold:
            return None

        # Use synthetic data to update Q-function
        dones = torch.zeros(self.batch_size).to(self.device)
        return self._update_q(states, actions, pred_r, pred_ns, dones)

    def train_step(self) -> Dict[str, Optional[float]]:
        if len(self.buffer) < self.batch_size:
            return {"q_loss": None, "model_loss": None, "plan_loss": None}

        # Sample real transitions
        batch = random.sample(list(self.buffer), self.batch_size)
        states = torch.FloatTensor(np.array([t[0] for t in batch])).to(self.device)
        actions = torch.LongTensor([t[1] for t in batch]).to(self.device)
        rewards = torch.FloatTensor([t[2] for t in batch]).to(self.device)
        next_states = torch.FloatTensor(np.array([t[3] for t in batch])).to(self.device)
        dones = torch.FloatTensor([float(t[4]) for t in batch]).to(self.device)

        # Step 1: Model-free Q update from real data
        q_loss = self._update_q(states, actions, rewards, next_states, dones)

        # Step 2: Update dynamics model
        model_loss = self._update_model(states, actions, rewards, next_states)

        # Step 3: Planning steps with learned model
        plan_loss = None
        for _ in range(self.planning_steps):
            pl = self._planning_step()
            if pl is not None:
                plan_loss = pl

        return {"q_loss": q_loss, "model_loss": model_loss, "plan_loss": plan_loss}
```

## MuZero: Planning in Learned Latent Spaces

**MuZero** (Schrittwieser et al., 2020) revolutionized model-based RL by learning a dynamics model entirely in a **latent space**, without ever reconstructing observations. It learns three functions: (1) a **representation function** h(o) -> s that maps observations to latent states, (2) a **dynamics function** g(s, a) -> (s', r) that predicts transitions in latent space, and (3) a **prediction function** f(s) -> (pi, v) that outputs policy and value from latent states. Planning is done by Monte Carlo Tree Search (MCTS) in the latent space, evaluating leaf nodes with the prediction function.

The key insight is that **the model does not need to predict pixels** -- it only needs to predict whatever is sufficient for planning (rewards and values). This makes MuZero applicable to domains where pixel-level prediction is intractable. However, a **pitfall** is that latent dynamics models can silently diverge from reality over long planning horizons because there is no observation-grounding loss beyond the initial representation.

### MuZero Core Networks

```python
import torch
import torch.nn as nn
from typing import Tuple

class MuZeroNetworks(nn.Module):
    # Core MuZero architecture: representation, dynamics, and prediction networks
    # Operates entirely in learned latent space -- never reconstructs observations
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        latent_dim: int = 128,
        hidden: int = 256,
    ) -> None:
        super().__init__()
        self.action_dim = action_dim
        self.latent_dim = latent_dim

        # h(observation) -> latent_state
        self.representation = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, latent_dim),
        )

        # g(latent_state, action) -> (next_latent_state, reward)
        self.dynamics = nn.Sequential(
            nn.Linear(latent_dim + action_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.dynamics_state_head = nn.Linear(hidden, latent_dim)
        self.dynamics_reward_head = nn.Linear(hidden, 1)

        # f(latent_state) -> (policy, value)
        self.prediction_policy = nn.Sequential(
            nn.Linear(latent_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, action_dim),
        )
        self.prediction_value = nn.Sequential(
            nn.Linear(latent_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def represent(self, obs: torch.Tensor) -> torch.Tensor:
        # Map raw observation to latent state
        return self.representation(obs)

    def dynamics_step(
        self, latent: torch.Tensor, action: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # Single step in latent space: (s, a) -> (s', r)
        action_oh = nn.functional.one_hot(action, self.action_dim).float()
        x = torch.cat([latent, action_oh], dim=-1)
        h = self.dynamics(x)
        next_latent = self.dynamics_state_head(h)
        reward = self.dynamics_reward_head(h).squeeze(-1)
        # Scale-normalize latent to prevent drift during multi-step rollouts
        next_latent = next_latent / (next_latent.norm(dim=-1, keepdim=True) + 1e-6) * (self.latent_dim ** 0.5)
        return next_latent, reward

    def predict(self, latent: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Predict policy and value from latent state
        policy_logits = self.prediction_policy(latent)
        value = self.prediction_value(latent).squeeze(-1)
        return policy_logits, value

    def unroll(
        self, obs: torch.Tensor, actions: torch.Tensor, num_steps: int
    ) -> Tuple[list, list, list]:
        # Unroll dynamics for MCTS-based planning
        latent = self.represent(obs)
        policy_logits_list = []
        value_list = []
        reward_list = []

        for t in range(num_steps):
            pl, v = self.predict(latent)
            policy_logits_list.append(pl)
            value_list.append(v)

            if t < num_steps - 1:
                latent, r = self.dynamics_step(latent, actions[:, t])
                reward_list.append(r)

        return policy_logits_list, value_list, reward_list
```

## Dreamer: Imagination-Based Policy Learning

**Dreamer** (Hafner et al., 2020) learns a **Recurrent State Space Model (RSSM)** that combines deterministic recurrent states with stochastic latent variables. It then **imagines** complete trajectories in the latent space and backpropagates through the imagined rewards to learn the policy, using the reparameterization trick for gradient flow through stochastic states. This is fundamentally different from Dyna (which uses synthetic transitions for Q-learning) because Dreamer directly optimizes the policy through differentiable planning.

The RSSM captures both deterministic dynamics (what must happen next) and stochastic dynamics (what could happen), providing a richer model than purely deterministic alternatives. **Best practice**: use KL balancing (alpha=0.8 for posterior, 0.2 for prior) to prevent posterior collapse, which is a **common mistake** when training variational world models.

### Dreamer RSSM Core

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Dict

class RSSM(nn.Module):
    # Recurrent State Space Model (Dreamer / DreamerV2)
    # Combines deterministic GRU state with stochastic latent variable
    # for rich dynamics modeling
    def __init__(
        self,
        obs_embed_dim: int = 256,
        action_dim: int = 4,
        deter_dim: int = 256,
        stoch_dim: int = 32,
        hidden_dim: int = 256,
    ) -> None:
        super().__init__()
        self.deter_dim = deter_dim
        self.stoch_dim = stoch_dim

        # Deterministic state transition (GRU)
        self.gru = nn.GRUCell(hidden_dim, deter_dim)
        self.pre_gru = nn.Sequential(
            nn.Linear(stoch_dim + action_dim, hidden_dim),
            nn.ELU(),
        )

        # Prior: p(s_t | h_t) -- predict stochastic state from deterministic
        self.prior_net = nn.Sequential(
            nn.Linear(deter_dim, hidden_dim),
            nn.ELU(),
            nn.Linear(hidden_dim, stoch_dim * 2),  # mean + log_std
        )

        # Posterior: q(s_t | h_t, o_t) -- incorporate observation
        self.posterior_net = nn.Sequential(
            nn.Linear(deter_dim + obs_embed_dim, hidden_dim),
            nn.ELU(),
            nn.Linear(hidden_dim, stoch_dim * 2),  # mean + log_std
        )

    def _sample_stoch(
        self, stats: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mean, log_std = stats.chunk(2, dim=-1)
        std = F.softplus(log_std) + 0.1  # minimum std for numerical stability
        # Reparameterization trick for differentiable sampling
        eps = torch.randn_like(std)
        sample = mean + std * eps
        return sample, mean, std

    def prior_step(
        self,
        prev_stoch: torch.Tensor,
        prev_action: torch.Tensor,
        prev_deter: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        # Imagination step: predict next state without observation
        x = self.pre_gru(torch.cat([prev_stoch, prev_action], dim=-1))
        deter = self.gru(x, prev_deter)
        prior_stats = self.prior_net(deter)
        stoch, mean, std = self._sample_stoch(prior_stats)
        return {"deter": deter, "stoch": stoch, "mean": mean, "std": std}

    def posterior_step(
        self,
        prev_stoch: torch.Tensor,
        prev_action: torch.Tensor,
        prev_deter: torch.Tensor,
        obs_embed: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        # Training step: incorporate actual observation
        x = self.pre_gru(torch.cat([prev_stoch, prev_action], dim=-1))
        deter = self.gru(x, prev_deter)
        post_stats = self.posterior_net(torch.cat([deter, obs_embed], dim=-1))
        stoch, mean, std = self._sample_stoch(post_stats)

        # Also compute prior for KL loss
        prior_stats = self.prior_net(deter)
        _, prior_mean, prior_std = self._sample_stoch(prior_stats)

        return {
            "deter": deter, "stoch": stoch,
            "post_mean": mean, "post_std": std,
            "prior_mean": prior_mean, "prior_std": prior_std,
        }

    def imagine(
        self,
        initial_deter: torch.Tensor,
        initial_stoch: torch.Tensor,
        actor: nn.Module,
        horizon: int = 15,
    ) -> Dict[str, torch.Tensor]:
        # Imagine a trajectory for policy learning via backprop
        deters, stochs = [initial_deter], [initial_stoch]
        deter, stoch = initial_deter, initial_stoch

        for _ in range(horizon):
            feat = torch.cat([deter, stoch], dim=-1)
            action = actor(feat)  # differentiable action sampling
            state = self.prior_step(stoch, action, deter)
            deter, stoch = state["deter"], state["stoch"]
            deters.append(deter)
            stochs.append(stoch)

        return {
            "deters": torch.stack(deters),
            "stochs": torch.stack(stochs),
        }
```

## Model Exploitation and Ensemble Disagreement

The most dangerous **pitfall** in model-based RL is **model exploitation**: the agent finds states or actions where the learned model makes optimistic errors and exploits them, achieving high reward in the model but poor performance in the real environment. This is analogous to adversarial examples -- the policy optimizer is adversarial with respect to the model.

**Ensemble disagreement** is the most effective defense. By training an ensemble of N models (typically 5-7) with different random initializations on bootstrapped subsets of data, we can use the variance across ensemble predictions as an uncertainty estimate. When ensemble members disagree, the model is uncertain, and we should not trust its predictions. This can be used to (1) penalize the reward with an uncertainty penalty (pessimistic planning), (2) truncate imagined rollouts when uncertainty exceeds a threshold, or (3) weight synthetic transitions by inverse uncertainty.

Therefore, the ensemble approach transforms the model exploitation problem into an exploration problem: regions of high disagreement are precisely the regions where more real data is needed.

## Summary and Key Takeaways

- **Model-based RL** achieves 10-100x better sample efficiency than model-free methods by learning a dynamics model and generating synthetic experience for planning.
- **Dyna** is the foundational framework: real experience updates both Q-values and the model, then planning steps extract additional value from the model.
- **Model exploitation** is the central risk; the policy can exploit inaccuracies in the learned model to achieve illusory high rewards.
- **Ensemble disagreement** is the **best practice** for uncertainty estimation and model exploitation mitigation: high disagreement means the model is unreliable.
- **MuZero** plans in learned latent spaces using MCTS, avoiding the need for pixel-level prediction; however, latent models can silently drift without observation grounding.
- **Dreamer** uses differentiable imagination through a stochastic world model, enabling direct policy optimization via backpropagation through imagined trajectories.
- **Common mistake**: using too many planning steps with an inaccurate model -- start conservative (k=1-5) and increase as the model improves.
"""
    ),

    # --- 5. RLHF for Language Models ---
    (
        "reinforcement-learning/rlhf-reward-modeling-ppo-dpo-kto-language-models",
        "Explain Reinforcement Learning from Human Feedback for language models comprehensively covering reward model training from preference pairs, PPO fine-tuning loop for LLMs, Direct Preference Optimization loss function, KTO (Kahneman-Tversky Optimization), reward hacking, KL divergence regularization, iterative RLHF, and provide complete PyTorch implementations of reward model training, the PPO-based RLHF loop, and the DPO loss with analysis of alignment trade-offs.",
        r"""
# RLHF: Reinforcement Learning from Human Feedback for Language Models

## The Alignment Problem and RLHF

Pretrained language models learn to predict the next token, but next-token prediction does not directly optimize for what humans actually want: helpful, harmless, and honest responses. **RLHF** bridges this gap by using human preferences to train a **reward model** that scores model outputs, then fine-tuning the language model to maximize this reward using reinforcement learning (typically PPO). This three-stage pipeline -- pretraining, reward modeling, RL fine-tuning -- was the key innovation behind InstructGPT and ChatGPT, and it remains the foundation of modern alignment techniques.

The fundamental **trade-off** in RLHF is between alignment (making the model do what humans want) and capability (preserving the model's knowledge and fluency from pretraining). Aggressive RL optimization improves alignment metrics but can cause the model to forget knowledge, produce repetitive outputs, or exploit reward model weaknesses. This tension motivates the KL divergence penalty that anchors the fine-tuned model to the original pretrained model.

## Stage 1: Reward Model Training

The reward model R(x, y) takes a prompt x and a response y and outputs a scalar reward. It is trained on **preference pairs**: given two responses y_w (preferred/winner) and y_l (rejected/loser) to the same prompt, the reward model should assign a higher score to y_w. The training objective uses the **Bradley-Terry model** of preferences:

L_RM = -E[log sigma(R(x, y_w) - R(x, y_l))]

where sigma is the sigmoid function. This loss pushes the reward for the preferred response above the rejected one by a margin. The reward model is typically initialized from the pretrained language model with the LM head replaced by a scalar value head.

### Reward Model Implementation

```python
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

@dataclass
class PreferencePair:
    # A single preference comparison
    prompt_ids: List[int]
    chosen_ids: List[int]
    rejected_ids: List[int]

class RewardModel(nn.Module):
    # Reward model built on top of a pretrained transformer backbone
    # Outputs a scalar reward for each (prompt, response) pair
    def __init__(
        self,
        backbone: nn.Module,
        hidden_dim: int = 768,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.backbone = backbone
        # Value head replaces the language modeling head
        self.value_head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.GELU(),
            nn.Linear(hidden_dim // 4, 1),
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        # Get last hidden state from transformer backbone
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
        )
        # Use the last token's hidden state as the sequence representation
        # This works because we right-pad and the last real token
        # contains information about the full sequence
        last_hidden = outputs.hidden_states[-1]
        # Find the position of the last non-padding token per sequence
        seq_lengths = attention_mask.sum(dim=1) - 1
        batch_idx = torch.arange(input_ids.size(0), device=input_ids.device)
        pooled = last_hidden[batch_idx, seq_lengths]
        reward = self.value_head(pooled).squeeze(-1)
        return reward


class PreferenceDataset(Dataset):
    # Dataset of preference pairs for reward model training
    def __init__(
        self,
        pairs: List[PreferencePair],
        max_length: int = 512,
        pad_token_id: int = 0,
    ) -> None:
        self.pairs = pairs
        self.max_length = max_length
        self.pad_token_id = pad_token_id

    def __len__(self) -> int:
        return len(self.pairs)

    def _pad_and_mask(
        self, token_ids: List[int]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        ids = token_ids[: self.max_length]
        pad_len = self.max_length - len(ids)
        input_ids = torch.tensor(ids + [self.pad_token_id] * pad_len, dtype=torch.long)
        mask = torch.tensor([1] * len(ids) + [0] * pad_len, dtype=torch.long)
        return input_ids, mask

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        pair = self.pairs[idx]
        chosen_full = pair.prompt_ids + pair.chosen_ids
        rejected_full = pair.prompt_ids + pair.rejected_ids

        chosen_ids, chosen_mask = self._pad_and_mask(chosen_full)
        rejected_ids, rejected_mask = self._pad_and_mask(rejected_full)

        return {
            "chosen_ids": chosen_ids,
            "chosen_mask": chosen_mask,
            "rejected_ids": rejected_ids,
            "rejected_mask": rejected_mask,
        }


def train_reward_model(
    model: RewardModel,
    dataset: PreferenceDataset,
    epochs: int = 3,
    batch_size: int = 8,
    lr: float = 1e-5,
    device: str = "cuda",
) -> Dict[str, List[float]]:
    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    history: Dict[str, List[float]] = {"loss": [], "accuracy": []}

    for epoch in range(epochs):
        total_loss = 0.0
        correct = 0
        total = 0

        for batch in loader:
            chosen_ids = batch["chosen_ids"].to(device)
            chosen_mask = batch["chosen_mask"].to(device)
            rejected_ids = batch["rejected_ids"].to(device)
            rejected_mask = batch["rejected_mask"].to(device)

            r_chosen = model(chosen_ids, chosen_mask)
            r_rejected = model(rejected_ids, rejected_mask)

            # Bradley-Terry preference loss
            loss = -torch.log(torch.sigmoid(r_chosen - r_rejected)).mean()

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_loss += loss.item() * chosen_ids.size(0)
            correct += (r_chosen > r_rejected).sum().item()
            total += chosen_ids.size(0)

        avg_loss = total_loss / total
        accuracy = correct / total
        history["loss"].append(avg_loss)
        history["accuracy"].append(accuracy)
        print(f"Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.4f} | Acc: {accuracy:.3f}")

    return history
```

**Best practice**: use a separate validation set of preference pairs and monitor accuracy -- a well-trained reward model should achieve 70-75% accuracy on held-out preferences (human inter-annotator agreement is typically 73-78%, so the model cannot exceed this ceiling).

## Stage 2: PPO Fine-Tuning for Language Models

The PPO fine-tuning loop works as follows: (1) sample a batch of prompts, (2) generate responses using the current policy (the LM being fine-tuned), (3) score responses with the reward model, (4) compute the PPO objective with a KL penalty to stay close to the reference model (the original pretrained LM), and (5) update the policy. The reward for each response is:

R_total = R_reward_model(x, y) - beta * KL(pi_theta || pi_ref)

where beta controls the strength of the KL constraint. The KL penalty is critical: without it, the model would quickly **reward hack** by finding degenerate outputs that the reward model scores highly but that are not actually good responses.

### RLHF PPO Training Loop

```python
import torch
import torch.nn.functional as F
from typing import Any

@dataclass
class RLHFConfig:
    # Configuration for the RLHF PPO training loop
    kl_coef: float = 0.1          # KL penalty coefficient (beta)
    clip_eps: float = 0.2          # PPO clip parameter
    value_coef: float = 0.5        # Value loss coefficient
    entropy_coef: float = 0.01     # Entropy bonus
    gamma: float = 1.0             # Discount factor (1.0 for single-turn)
    lam: float = 0.95              # GAE lambda
    max_grad_norm: float = 1.0     # Gradient clipping
    ppo_epochs: int = 4            # PPO update epochs per batch
    mini_batch_size: int = 4       # Mini-batch size for PPO
    target_kl: Optional[float] = 0.02  # Early stop if KL exceeds this

class RLHFTrainer:
    # RLHF trainer using PPO with KL-penalized reward
    def __init__(
        self,
        policy_model: nn.Module,
        ref_model: nn.Module,
        reward_model: RewardModel,
        tokenizer: Any,
        config: RLHFConfig,
        lr: float = 1e-6,
        device: str = "cuda",
    ) -> None:
        self.policy = policy_model.to(device)
        self.ref = ref_model.to(device)
        self.ref.eval()  # Reference model is frozen
        self.reward_fn = reward_model.to(device)
        self.reward_fn.eval()
        self.tokenizer = tokenizer
        self.config = config
        self.device = device
        self.optimizer = optim.AdamW(self.policy.parameters(), lr=lr)

    def _compute_log_probs(
        self,
        model: nn.Module,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        response_start: int,
    ) -> torch.Tensor:
        # Compute per-token log probabilities for the response portion
        with torch.no_grad() if model == self.ref else torch.enable_grad():
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        logits = outputs.logits[:, response_start - 1 : -1, :]
        target_ids = input_ids[:, response_start:]
        log_probs = F.log_softmax(logits, dim=-1)
        token_log_probs = log_probs.gather(2, target_ids.unsqueeze(2)).squeeze(2)
        # Mask padding tokens
        resp_mask = attention_mask[:, response_start:]
        return token_log_probs * resp_mask

    def _compute_kl_penalty(
        self,
        policy_log_probs: torch.Tensor,
        ref_log_probs: torch.Tensor,
    ) -> torch.Tensor:
        # Per-token KL divergence: KL(policy || ref)
        # Approximated as: exp(log_pi - log_ref) * (log_pi - log_ref) - 1
        # This is the Schulman KL estimator (unbiased, low variance)
        log_ratio = policy_log_probs - ref_log_probs
        kl = (torch.exp(log_ratio) - 1) - log_ratio
        return kl

    def train_step(
        self,
        prompt_ids: torch.Tensor,
        response_ids: torch.Tensor,
        attention_masks: torch.Tensor,
        response_start: int,
    ) -> Dict[str, float]:
        batch_size = prompt_ids.size(0)

        # Concatenate prompt + response as full sequences
        full_ids = torch.cat([prompt_ids, response_ids], dim=1).to(self.device)
        full_mask = attention_masks.to(self.device)

        # Compute rewards from reward model
        with torch.no_grad():
            rewards = self.reward_fn(full_ids, full_mask)

        # Compute log probs under policy and reference
        policy_log_probs = self._compute_log_probs(
            self.policy, full_ids, full_mask, response_start
        )
        with torch.no_grad():
            ref_log_probs = self._compute_log_probs(
                self.ref, full_ids, full_mask, response_start
            )

        # KL penalty
        kl = self._compute_kl_penalty(policy_log_probs, ref_log_probs)
        kl_per_sequence = kl.sum(dim=1)
        mean_kl = kl_per_sequence.mean()

        # KL-penalized reward
        penalized_rewards = rewards - self.config.kl_coef * kl_per_sequence

        # PPO update using sequence-level reward
        old_log_probs = policy_log_probs.detach().sum(dim=1)

        metrics = {"reward": rewards.mean().item(), "kl": mean_kl.item()}

        for ppo_epoch in range(self.config.ppo_epochs):
            new_policy_lp = self._compute_log_probs(
                self.policy, full_ids, full_mask, response_start
            )
            new_log_probs = new_policy_lp.sum(dim=1)

            ratio = torch.exp(new_log_probs - old_log_probs)
            advantages = penalized_rewards - penalized_rewards.mean()
            advantages = advantages / (advantages.std() + 1e-8)

            surr1 = ratio * advantages
            surr2 = torch.clamp(
                ratio, 1 - self.config.clip_eps, 1 + self.config.clip_eps
            ) * advantages
            pg_loss = -torch.min(surr1, surr2).mean()

            self.optimizer.zero_grad()
            pg_loss.backward()
            nn.utils.clip_grad_norm_(
                self.policy.parameters(), self.config.max_grad_norm
            )
            self.optimizer.step()

            # Early stopping on KL divergence
            with torch.no_grad():
                approx_kl = (old_log_probs - new_log_probs.detach()).mean()
            if (
                self.config.target_kl is not None
                and approx_kl > self.config.target_kl
            ):
                break

        metrics["pg_loss"] = pg_loss.item()
        return metrics
```

## DPO: Direct Preference Optimization

**DPO** (Rafailov et al., 2023) eliminates the need for a separate reward model and RL training loop entirely. It shows that the optimal policy under KL-constrained reward maximization has a closed-form relationship with the reward function: R(x, y) = beta * log(pi_theta(y|x) / pi_ref(y|x)) + C. Substituting this into the Bradley-Terry loss gives the **DPO loss** directly in terms of the policy:

L_DPO = -E[log sigma(beta * (log pi_theta(y_w|x)/pi_ref(y_w|x) - log pi_theta(y_l|x)/pi_ref(y_l|x)))]

This is elegant because it bypasses reward modeling and PPO entirely, requiring only supervised training on preference pairs. The **trade-off** is that DPO implicitly defines the reward function through the policy, which means it cannot disentangle reward learning from policy optimization -- any reward model errors are baked into the policy without a separate diagnostic signal.

### DPO Loss Implementation

```python
def compute_dpo_loss(
    policy_model: nn.Module,
    ref_model: nn.Module,
    chosen_ids: torch.Tensor,
    chosen_mask: torch.Tensor,
    rejected_ids: torch.Tensor,
    rejected_mask: torch.Tensor,
    prompt_length: int,
    beta: float = 0.1,
    label_smoothing: float = 0.0,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    # Compute DPO loss from preference pairs
    # No reward model or RL loop needed

    def get_sequence_log_prob(
        model: nn.Module, input_ids: torch.Tensor, mask: torch.Tensor
    ) -> torch.Tensor:
        outputs = model(input_ids=input_ids, attention_mask=mask)
        logits = outputs.logits[:, prompt_length - 1:-1, :]
        target = input_ids[:, prompt_length:]
        log_probs = F.log_softmax(logits, dim=-1)
        token_lp = log_probs.gather(2, target.unsqueeze(2)).squeeze(2)
        resp_mask = mask[:, prompt_length:]
        return (token_lp * resp_mask).sum(dim=1)

    # Policy log probs
    pi_chosen = get_sequence_log_prob(policy_model, chosen_ids, chosen_mask)
    pi_rejected = get_sequence_log_prob(policy_model, rejected_ids, rejected_mask)

    # Reference log probs (frozen)
    with torch.no_grad():
        ref_chosen = get_sequence_log_prob(ref_model, chosen_ids, chosen_mask)
        ref_rejected = get_sequence_log_prob(ref_model, rejected_ids, rejected_mask)

    # Log-ratios: how much the policy diverges from reference for each response
    chosen_log_ratio = pi_chosen - ref_chosen
    rejected_log_ratio = pi_rejected - ref_rejected

    # DPO loss: push chosen log-ratio above rejected log-ratio
    logits_diff = beta * (chosen_log_ratio - rejected_log_ratio)

    if label_smoothing > 0:
        # Robust DPO with label smoothing for noisy preferences
        loss = (
            -label_smoothing * F.logsigmoid(-logits_diff)
            - (1 - label_smoothing) * F.logsigmoid(logits_diff)
        ).mean()
    else:
        loss = -F.logsigmoid(logits_diff).mean()

    # Diagnostic metrics
    chosen_reward = beta * chosen_log_ratio.detach().mean().item()
    rejected_reward = beta * rejected_log_ratio.detach().mean().item()
    reward_margin = chosen_reward - rejected_reward
    accuracy = (logits_diff > 0).float().mean().item()

    metrics = {
        "chosen_reward": chosen_reward,
        "rejected_reward": rejected_reward,
        "reward_margin": reward_margin,
        "accuracy": accuracy,
    }
    return loss, metrics
```

## KTO: Kahneman-Tversky Optimization

**KTO** (Ethayarajh et al., 2024) addresses a practical limitation of DPO: it requires **paired** preferences (two responses to the same prompt), which are expensive to collect. KTO works with **unpaired** data -- individual responses labeled as "good" or "bad." It is motivated by prospect theory: humans are **loss-averse**, meaning the dissatisfaction from a bad output is stronger than the satisfaction from a good one. The KTO loss applies different weights:

L_KTO = E_good[-lambda_good * sigma(beta * (log_ratio - z))] + E_bad[-lambda_bad * sigma(-beta * (log_ratio - z))]

where z is a reference point computed from the batch average and lambda values encode loss aversion. This makes KTO more practical for real-world data collection pipelines where unpaired feedback is much cheaper to obtain. However, the **pitfall** is that without direct comparisons, KTO can be less precise than DPO at capturing fine-grained preferences between similar responses.

## Reward Hacking and Mitigations

**Reward hacking** is the most critical **pitfall** in RLHF. The reward model is an imperfect proxy for human preferences, and given enough optimization pressure, the policy will find inputs where the reward model gives high scores despite the output being low quality. Common manifestations include: (1) excessively long responses (many reward models have a length bias), (2) sycophantic agreement with the user regardless of correctness, (3) hedging language ("As an AI...") that the reward model has learned to score highly, and (4) repetitive confident-sounding statements.

Mitigations for reward hacking:

1. **KL regularization**: The KL penalty beta is the primary defense. Too low and the model reward-hacks; too high and the model barely changes from the reference. **Best practice**: start with beta=0.1-0.2 for PPO and beta=0.1 for DPO, then adjust based on KL divergence monitoring.

2. **Reward model ensembles**: Train multiple reward models and use the minimum (conservative) or mean reward to reduce exploitation of any single model's biases.

3. **Iterative RLHF**: Periodically collect new human preferences on the latest model's outputs and retrain the reward model. This closes the distribution shift gap because the reward model now evaluates the same distribution it was trained on.

4. **Length normalization**: Divide the reward by response length to remove the length bias, or add an explicit length penalty.

**Common mistake**: training for too many PPO steps without monitoring KL divergence. The policy can drift far from the reference model, causing catastrophic quality degradation that is not reflected in the reward model score.

## Summary and Key Takeaways

- **RLHF** aligns language models with human preferences through a three-stage pipeline: pretraining, reward modeling, and RL fine-tuning with PPO.
- The **reward model** is trained on preference pairs using the Bradley-Terry loss; accuracy of 70-75% on held-out data is typical and near the human agreement ceiling.
- **KL regularization** (beta parameter) is critical to prevent **reward hacking** -- it anchors the fine-tuned model to the reference policy and must be carefully tuned.
- **DPO** eliminates the reward model and RL loop by optimizing the preference objective directly through the policy log-ratios; the **trade-off** is losing the ability to diagnose reward model quality independently.
- **KTO** further simplifies data requirements by working with unpaired good/bad labels instead of preference pairs, making it more practical for large-scale production systems.
- **Iterative RLHF** with periodic reward model retraining is the **best practice** for production systems, as it mitigates distribution shift between the reward model's training data and the current policy's outputs.
- **Common mistake**: using a single reward model without ensembling or monitoring for reward hacking; therefore, always track KL divergence, response length distributions, and diversity metrics during RLHF training.
"""
    ),
]
