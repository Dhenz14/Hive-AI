"""Reinforcement learning — PPO, DPO, RLHF, multi-agent RL."""

PAIRS = [
    (
        "ai/ppo-training",
        "Show PPO (Proximal Policy Optimization) training implementation with clipped objective, GAE, and value function for continuous control.",
        '''PPO training for continuous control:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal
import numpy as np
from dataclasses import dataclass


@dataclass
class PPOConfig:
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    ppo_epochs: int = 10
    mini_batch_size: int = 64
    lr: float = 3e-4


class ActorCritic(nn.Module):
    """Shared-backbone actor-critic for continuous control."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: int = 256):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
        )
        # Actor: mean and log_std for Gaussian policy
        self.actor_mean = nn.Linear(hidden, act_dim)
        self.actor_log_std = nn.Parameter(torch.zeros(act_dim))
        # Critic: state value
        self.critic = nn.Linear(hidden, 1)

    def forward(self, obs: torch.Tensor):
        features = self.shared(obs)
        mean = self.actor_mean(features)
        std = self.actor_log_std.exp().expand_as(mean)
        value = self.critic(features).squeeze(-1)
        return Normal(mean, std), value

    def get_action(self, obs: torch.Tensor):
        dist, value = self(obs)
        action = dist.sample()
        log_prob = dist.log_prob(action).sum(-1)
        return action, log_prob, value


class RolloutBuffer:
    """Store trajectory data for PPO updates."""

    def __init__(self):
        self.obs, self.actions, self.log_probs = [], [], []
        self.rewards, self.dones, self.values = [], [], []

    def add(self, obs, action, log_prob, reward, done, value):
        self.obs.append(obs)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)

    def compute_gae(self, last_value: float, gamma: float, lam: float):
        """Generalized Advantage Estimation."""
        rewards = np.array(self.rewards)
        dones = np.array(self.dones)
        values = np.array(self.values + [last_value])

        advantages = np.zeros_like(rewards)
        gae = 0.0
        for t in reversed(range(len(rewards))):
            delta = rewards[t] + gamma * values[t + 1] * (1 - dones[t]) - values[t]
            gae = delta + gamma * lam * (1 - dones[t]) * gae
            advantages[t] = gae

        returns = advantages + values[:-1]
        return advantages, returns

    def get_batches(self, advantages, returns, batch_size):
        """Yield mini-batches for PPO update."""
        n = len(self.obs)
        indices = np.random.permutation(n)
        for start in range(0, n, batch_size):
            idx = indices[start:start + batch_size]
            yield (
                torch.FloatTensor(np.array(self.obs))[idx],
                torch.FloatTensor(np.array(self.actions))[idx],
                torch.FloatTensor(np.array(self.log_probs))[idx],
                torch.FloatTensor(advantages)[idx],
                torch.FloatTensor(returns)[idx],
            )

    def clear(self):
        self.__init__()


def ppo_update(model: ActorCritic, buffer: RolloutBuffer, config: PPOConfig):
    """PPO clipped objective update."""
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)

    with torch.no_grad():
        last_obs = torch.FloatTensor(buffer.obs[-1]).unsqueeze(0)
        _, last_value = model(last_obs)
        last_value = last_value.item()

    advantages, returns = buffer.compute_gae(last_value, config.gamma, config.gae_lambda)
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    for epoch in range(config.ppo_epochs):
        for obs, actions, old_log_probs, advs, rets in buffer.get_batches(
            advantages, returns, config.mini_batch_size
        ):
            dist, values = model(obs)
            new_log_probs = dist.log_prob(actions).sum(-1)
            entropy = dist.entropy().sum(-1).mean()

            # PPO clipped objective
            ratio = (new_log_probs - old_log_probs).exp()
            surr1 = ratio * advs
            surr2 = torch.clamp(ratio, 1 - config.clip_eps, 1 + config.clip_eps) * advs
            policy_loss = -torch.min(surr1, surr2).mean()

            # Value loss (clipped)
            value_loss = F.mse_loss(values, rets)

            # Total loss
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()
```

Key patterns:
1. **Clipped objective** — `min(ratio * A, clip(ratio) * A)` prevents destructively large policy updates
2. **GAE (λ-returns)** — balances bias/variance in advantage estimation; λ=0.95 is standard
3. **Entropy bonus** — encourages exploration by penalizing overly deterministic policies
4. **Mini-batch updates** — reuse trajectory data for multiple epochs (sample-efficient)
5. **Advantage normalization** — zero-mean unit-variance advantages stabilize training'''
    ),
    (
        "ai/dpo-alignment",
        "Show DPO (Direct Preference Optimization) training for LLM alignment: preference pairs, reference model, and the DPO loss function.",
        '''DPO — align LLMs directly from preference data without reward models:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional


class PreferenceDataset(Dataset):
    """Dataset of (prompt, chosen, rejected) preference pairs."""

    def __init__(self, data: list[dict], tokenizer, max_length: int = 512):
        self.data = data  # [{"prompt": ..., "chosen": ..., "rejected": ...}]
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        chosen_text = item["prompt"] + item["chosen"]
        rejected_text = item["prompt"] + item["rejected"]

        chosen_enc = self.tokenizer(
            chosen_text, max_length=self.max_length,
            truncation=True, padding="max_length", return_tensors="pt",
        )
        rejected_enc = self.tokenizer(
            rejected_text, max_length=self.max_length,
            truncation=True, padding="max_length", return_tensors="pt",
        )
        prompt_enc = self.tokenizer(
            item["prompt"], return_tensors="pt",
        )

        return {
            "chosen_ids": chosen_enc["input_ids"].squeeze(),
            "chosen_mask": chosen_enc["attention_mask"].squeeze(),
            "rejected_ids": rejected_enc["input_ids"].squeeze(),
            "rejected_mask": rejected_enc["attention_mask"].squeeze(),
            "prompt_length": prompt_enc["input_ids"].shape[1],
        }


def compute_log_probs(model, input_ids, attention_mask, prompt_length):
    """Compute per-token log probabilities for response tokens only."""
    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
    logits = outputs.logits[:, :-1]  # Shift for next-token prediction
    targets = input_ids[:, 1:]

    log_probs = F.log_softmax(logits, dim=-1)
    token_log_probs = log_probs.gather(2, targets.unsqueeze(-1)).squeeze(-1)

    # Mask: only count response tokens (after prompt)
    response_mask = attention_mask[:, 1:].clone()
    response_mask[:, :prompt_length - 1] = 0

    return (token_log_probs * response_mask).sum(dim=-1)


def dpo_loss(
    policy_model: nn.Module,
    reference_model: nn.Module,
    batch: dict,
    beta: float = 0.1,
) -> torch.Tensor:
    """DPO loss: directly optimize policy from preferences.

    L_DPO = -log σ(β * (log π(y_w|x)/π_ref(y_w|x) - log π(y_l|x)/π_ref(y_l|x)))

    No reward model needed — the implicit reward is:
    r(x, y) = β * log(π(y|x) / π_ref(y|x))
    """
    prompt_len = batch["prompt_length"]

    # Policy log probs
    pi_chosen = compute_log_probs(
        policy_model, batch["chosen_ids"], batch["chosen_mask"], prompt_len
    )
    pi_rejected = compute_log_probs(
        policy_model, batch["rejected_ids"], batch["rejected_mask"], prompt_len
    )

    # Reference log probs (frozen)
    with torch.no_grad():
        ref_chosen = compute_log_probs(
            reference_model, batch["chosen_ids"], batch["chosen_mask"], prompt_len
        )
        ref_rejected = compute_log_probs(
            reference_model, batch["rejected_ids"], batch["rejected_mask"], prompt_len
        )

    # DPO objective
    chosen_reward = beta * (pi_chosen - ref_chosen)
    rejected_reward = beta * (pi_rejected - ref_rejected)

    loss = -F.logsigmoid(chosen_reward - rejected_reward).mean()

    # Metrics
    with torch.no_grad():
        reward_margin = (chosen_reward - rejected_reward).mean()
        accuracy = (chosen_reward > rejected_reward).float().mean()

    return loss, {"reward_margin": reward_margin.item(), "accuracy": accuracy.item()}


def train_dpo(
    model_name: str,
    preference_data: list[dict],
    epochs: int = 1,
    lr: float = 5e-7,
    beta: float = 0.1,
    batch_size: int = 4,
):
    """Full DPO training loop."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    policy = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.bfloat16).cuda()
    reference = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.bfloat16).cuda()
    reference.eval()
    for p in reference.parameters():
        p.requires_grad = False

    dataset = PreferenceDataset(preference_data, tokenizer)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=lr, weight_decay=0.01)

    for epoch in range(epochs):
        for batch in loader:
            batch = {k: v.cuda() for k, v in batch.items()}
            loss, metrics = dpo_loss(policy, reference, batch, beta)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()

            print(f"Loss: {loss.item():.4f} | Margin: {metrics['reward_margin']:.3f} | Acc: {metrics['accuracy']:.1%}")
```

DPO vs RLHF comparison:

| Aspect | RLHF (PPO) | DPO |
|--------|-----------|-----|
| **Reward model** | Required (separate training) | Not needed |
| **Training stability** | Tricky (RL + LM) | Stable (supervised-like) |
| **Compute** | 4 models in memory | 2 models in memory |
| **Hyperparameters** | Many (PPO + reward) | Few (β, lr) |
| **Performance** | Strong | Comparable or better |

Key patterns:
1. **Implicit reward** — DPO derives reward from policy/reference ratio; no separate reward model needed
2. **Reference model** — frozen copy of initial policy prevents reward hacking and distribution collapse
3. **β temperature** — controls deviation from reference; higher β = more conservative updates
4. **Response-only loss** — mask prompt tokens; only optimize log-probs on response tokens
5. **Preference pairs** — (chosen, rejected) for same prompt; can come from human annotators or AI feedback'''
    ),
    (
        "ai/multi-agent-rl",
        "Show multi-agent reinforcement learning patterns: independent learners, centralized training with decentralized execution (CTDE), and communication.",
        '''Multi-agent RL — cooperative and competitive settings:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass, field


# === Centralized Training, Decentralized Execution (CTDE) ===

class QMixNetwork(nn.Module):
    """QMIX: Monotonic value decomposition for cooperative MARL.

    Key idea: Q_total = f(Q_1, Q_2, ..., Q_n) where f is monotonic.
    Each agent has local Q-function, mixing network combines them.
    """

    def __init__(self, n_agents: int, state_dim: int, embed_dim: int = 32):
        super().__init__()
        self.n_agents = n_agents

        # Hypernetwork: state -> mixing weights (positive via abs)
        self.hyper_w1 = nn.Sequential(
            nn.Linear(state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, n_agents * embed_dim),
        )
        self.hyper_w2 = nn.Sequential(
            nn.Linear(state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, embed_dim),
        )
        self.hyper_b1 = nn.Linear(state_dim, embed_dim)
        self.hyper_b2 = nn.Sequential(
            nn.Linear(state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, 1),
        )

    def forward(self, agent_qs: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """
        agent_qs: [batch, n_agents] — individual Q-values
        state: [batch, state_dim] — global state
        Returns: [batch, 1] — Q_total
        """
        batch = agent_qs.shape[0]
        agent_qs = agent_qs.unsqueeze(1)  # [B, 1, n_agents]

        # Generate mixing weights from state (abs for monotonicity)
        w1 = self.hyper_w1(state).view(batch, self.n_agents, -1).abs()
        b1 = self.hyper_b1(state).unsqueeze(1)

        w2 = self.hyper_w2(state).view(batch, -1, 1).abs()
        b2 = self.hyper_b2(state).unsqueeze(1)

        # Two-layer mixing
        hidden = F.elu(torch.bmm(agent_qs, w1) + b1)
        q_total = torch.bmm(hidden, w2) + b2

        return q_total.squeeze(-1)


class AgentNetwork(nn.Module):
    """Individual agent network with GRU for partial observability."""

    def __init__(self, obs_dim: int, n_actions: int, hidden_dim: int = 64):
        super().__init__()
        self.fc1 = nn.Linear(obs_dim, hidden_dim)
        self.rnn = nn.GRUCell(hidden_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, n_actions)

    def forward(self, obs: torch.Tensor, hidden: torch.Tensor):
        x = F.relu(self.fc1(obs))
        h = self.rnn(x, hidden)
        q = self.fc2(h)
        return q, h


# === Communication Channel ===

class CommNet(nn.Module):
    """CommNet: agents learn to communicate via continuous messages.

    Each round: agents broadcast hidden states, receive mean of others.
    """

    def __init__(self, n_agents: int, obs_dim: int, n_actions: int,
                 hidden_dim: int = 128, comm_rounds: int = 2):
        super().__init__()
        self.n_agents = n_agents
        self.comm_rounds = comm_rounds

        self.encoder = nn.Linear(obs_dim, hidden_dim)
        self.comm_layers = nn.ModuleList([
            nn.Linear(hidden_dim, hidden_dim) for _ in range(comm_rounds)
        ])
        self.decoders = nn.ModuleList([
            nn.Linear(hidden_dim, n_actions) for _ in range(n_agents)
        ])

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        """
        observations: [batch, n_agents, obs_dim]
        Returns: [batch, n_agents, n_actions]
        """
        h = F.relu(self.encoder(observations))  # [B, N, H]

        for comm_layer in self.comm_layers:
            # Broadcast: each agent receives mean of others' hidden states
            mean_others = (h.sum(dim=1, keepdim=True) - h) / (self.n_agents - 1)
            h = F.relu(comm_layer(h + mean_others))

        # Per-agent action heads
        actions = torch.stack([
            self.decoders[i](h[:, i]) for i in range(self.n_agents)
        ], dim=1)

        return actions


# === Independent PPO for Multi-Agent ===

class MAPPOAgent:
    """Multi-Agent PPO with shared parameters.

    Centralized critic (sees global state), decentralized actors (local obs).
    """

    def __init__(self, obs_dim: int, state_dim: int, n_actions: int,
                 n_agents: int, hidden: int = 256):
        # Shared actor (parameter sharing across agents)
        self.actor = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, n_actions),
        )
        # Centralized critic (sees global state)
        self.critic = nn.Sequential(
            nn.Linear(state_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        self.n_agents = n_agents

    def get_actions(self, observations: torch.Tensor):
        """observations: [n_agents, obs_dim]"""
        logits = self.actor(observations)
        dist = torch.distributions.Categorical(logits=logits)
        actions = dist.sample()
        log_probs = dist.log_prob(actions)
        return actions, log_probs

    def get_value(self, global_state: torch.Tensor):
        """global_state: [state_dim] — centralized critic input"""
        return self.critic(global_state)
```

Multi-agent RL comparison:

| Method | Communication | Scalability | Training |
|--------|--------------|-------------|----------|
| **Independent Q** | None | High | Decentralized |
| **QMIX** | None (mixing only) | Medium | Centralized |
| **MAPPO** | None (shared params) | High | CTDE |
| **CommNet** | Learned continuous | Medium | Centralized |
| **MADDPG** | None | Low | CTDE |

Key patterns:
1. **CTDE** — train with global info (state, all actions), execute with local observations only
2. **QMIX monotonicity** — hypernetwork weights are absolute-valued; ensures Q_total is monotonic in individual Qs
3. **Parameter sharing** — all agents share actor weights; agent ID as input for specialization
4. **Communication** — CommNet broadcasts hidden states; mean aggregation enables learned coordination
5. **GRU for POMDP** — recurrent agent handles partial observability by maintaining hidden state'''
    ),
    (
        "ai/reward-modeling",
        "Show reward modeling for RLHF: Bradley-Terry model, reward model training from comparisons, and reward hacking mitigation.",
        '''Reward modeling for RLHF alignment:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.utils.data import DataLoader, Dataset


class RewardModel(nn.Module):
    """Reward model trained on human preference comparisons.

    Architecture: LLM backbone + scalar reward head.
    Training: Bradley-Terry model on (chosen, rejected) pairs.
    """

    def __init__(self, model_name: str):
        super().__init__()
        self.backbone = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.bfloat16,
        )
        # Remove LM head, add reward head
        hidden_size = self.backbone.config.hidden_size
        self.backbone.lm_head = nn.Identity()
        self.reward_head = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, input_ids, attention_mask):
        """Compute scalar reward for a (prompt, response) sequence."""
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        # Use last non-padding token's hidden state
        hidden = outputs.logits  # After Identity, this is hidden states
        seq_lengths = attention_mask.sum(dim=1) - 1
        last_hidden = hidden[torch.arange(hidden.size(0)), seq_lengths]
        return self.reward_head(last_hidden).squeeze(-1)


class ComparisonDataset(Dataset):
    """Dataset of human preference comparisons."""

    def __init__(self, comparisons: list[dict], tokenizer, max_length: int = 512):
        self.data = comparisons
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        chosen = self.tokenizer(
            item["prompt"] + item["chosen"],
            max_length=self.max_length, truncation=True,
            padding="max_length", return_tensors="pt",
        )
        rejected = self.tokenizer(
            item["prompt"] + item["rejected"],
            max_length=self.max_length, truncation=True,
            padding="max_length", return_tensors="pt",
        )
        return {
            "chosen_ids": chosen["input_ids"].squeeze(),
            "chosen_mask": chosen["attention_mask"].squeeze(),
            "rejected_ids": rejected["input_ids"].squeeze(),
            "rejected_mask": rejected["attention_mask"].squeeze(),
        }


def bradley_terry_loss(reward_chosen: torch.Tensor, reward_rejected: torch.Tensor) -> torch.Tensor:
    """Bradley-Terry preference model loss.

    P(chosen > rejected) = σ(r(chosen) - r(rejected))
    Loss = -log σ(r_w - r_l)
    """
    return -F.logsigmoid(reward_chosen - reward_rejected).mean()


def train_reward_model(
    model_name: str,
    comparisons: list[dict],
    epochs: int = 1,
    lr: float = 1e-5,
    batch_size: int = 8,
):
    """Train reward model from human comparisons."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    reward_model = RewardModel(model_name).cuda()

    dataset = ComparisonDataset(comparisons, tokenizer)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(reward_model.parameters(), lr=lr)

    for epoch in range(epochs):
        total_loss, correct, total = 0, 0, 0
        for batch in loader:
            batch = {k: v.cuda() for k, v in batch.items()}

            r_chosen = reward_model(batch["chosen_ids"], batch["chosen_mask"])
            r_rejected = reward_model(batch["rejected_ids"], batch["rejected_mask"])

            loss = bradley_terry_loss(r_chosen, r_rejected)

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(reward_model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            correct += (r_chosen > r_rejected).sum().item()
            total += r_chosen.shape[0]

        print(f"Epoch {epoch}: Loss={total_loss/len(loader):.4f}, Acc={correct/total:.1%}")

    return reward_model
```

Key patterns:
1. **Bradley-Terry model** — P(a > b) = σ(r(a) - r(b)); turns pairwise comparisons into scalar rewards
2. **Last-token pooling** — reward from final token's hidden state; captures full sequence information
3. **Reward normalization** — normalize rewards during PPO to prevent reward hacking from scale
4. **KL penalty** — add KL(π || π_ref) to reward to prevent policy from diverging too far from base model
5. **Comparison data** — each example is (prompt, chosen_response, rejected_response); annotated by humans or AI'''
    ),
    (
        "ai/offline-rl",
        "Show offline reinforcement learning: Conservative Q-Learning (CQL), Decision Transformer, and batch-constrained approaches.",
        '''Offline RL — learn policies from fixed datasets without environment interaction:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass


# === Conservative Q-Learning (CQL) ===

class CQLCritic(nn.Module):
    """Conservative Q-Learning: penalize Q-values for out-of-distribution actions.

    Key idea: standard Q-learning overestimates Q for unseen actions.
    CQL adds a regularizer that minimizes Q for random actions while
    maximizing Q for dataset actions.
    """

    def __init__(self, obs_dim: int, act_dim: int, hidden: int = 256):
        super().__init__()
        self.q1 = nn.Sequential(
            nn.Linear(obs_dim + act_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )
        self.q2 = nn.Sequential(
            nn.Linear(obs_dim + act_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, obs, action):
        x = torch.cat([obs, action], dim=-1)
        return self.q1(x).squeeze(-1), self.q2(x).squeeze(-1)


def cql_loss(
    critic: CQLCritic,
    obs: torch.Tensor,
    actions: torch.Tensor,
    rewards: torch.Tensor,
    next_obs: torch.Tensor,
    dones: torch.Tensor,
    target_critic: CQLCritic,
    policy,
    gamma: float = 0.99,
    cql_alpha: float = 5.0,
    n_random: int = 10,
):
    """CQL loss = standard Bellman loss + conservative regularizer."""
    with torch.no_grad():
        next_actions = policy(next_obs)
        q1_next, q2_next = target_critic(next_obs, next_actions)
        q_next = torch.min(q1_next, q2_next)
        target_q = rewards + gamma * (1 - dones) * q_next

    # Standard Bellman error
    q1, q2 = critic(obs, actions)
    bellman_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)

    # CQL regularizer: push down Q for random actions, push up for data actions
    batch_size = obs.shape[0]

    # Sample random actions
    random_actions = torch.FloatTensor(batch_size * n_random, actions.shape[-1]).uniform_(-1, 1).to(obs.device)
    obs_repeat = obs.unsqueeze(1).repeat(1, n_random, 1).view(-1, obs.shape[-1])

    # Q-values for random actions (should be low)
    q1_rand, q2_rand = critic(obs_repeat, random_actions)
    q1_rand = q1_rand.view(batch_size, n_random)
    q2_rand = q2_rand.view(batch_size, n_random)

    # CQL: logsumexp(Q_random) - E[Q_data]
    cql_loss_q1 = torch.logsumexp(q1_rand, dim=1).mean() - q1.mean()
    cql_loss_q2 = torch.logsumexp(q2_rand, dim=1).mean() - q2.mean()

    total_loss = bellman_loss + cql_alpha * (cql_loss_q1 + cql_loss_q2)
    return total_loss


# === Decision Transformer ===

class DecisionTransformer(nn.Module):
    """Decision Transformer: RL as sequence modeling.

    Input sequence: (R_1, s_1, a_1, R_2, s_2, a_2, ...)
    where R_t is return-to-go (desired future return).
    At inference: condition on high R to get good actions.
    """

    def __init__(self, state_dim: int, act_dim: int, hidden: int = 128,
                 n_layers: int = 3, n_heads: int = 4, max_ep_len: int = 1000):
        super().__init__()
        self.hidden = hidden

        # Embeddings for each modality
        self.state_embed = nn.Linear(state_dim, hidden)
        self.action_embed = nn.Linear(act_dim, hidden)
        self.return_embed = nn.Linear(1, hidden)
        self.pos_embed = nn.Embedding(max_ep_len, hidden)
        self.ln = nn.LayerNorm(hidden)

        # Transformer
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden, nhead=n_heads,
            dim_feedforward=hidden * 4, dropout=0.1,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        # Prediction heads
        self.action_head = nn.Linear(hidden, act_dim)
        self.state_head = nn.Linear(hidden, state_dim)

    def forward(self, returns_to_go, states, actions, timesteps):
        """
        returns_to_go: [B, T, 1]
        states: [B, T, state_dim]
        actions: [B, T, act_dim]
        timesteps: [B, T]
        """
        B, T, _ = states.shape

        pos = self.pos_embed(timesteps)

        # Embed each modality
        r_embed = self.return_embed(returns_to_go) + pos
        s_embed = self.state_embed(states) + pos
        a_embed = self.action_embed(actions) + pos

        # Interleave: [r1, s1, a1, r2, s2, a2, ...]
        tokens = torch.stack([r_embed, s_embed, a_embed], dim=2)
        tokens = tokens.view(B, T * 3, self.hidden)
        tokens = self.ln(tokens)

        # Causal mask
        mask = nn.Transformer.generate_square_subsequent_mask(T * 3).to(tokens.device)
        out = self.transformer(tokens, mask=mask)

        # Extract state token positions to predict actions
        state_positions = out[:, 1::3]  # s1, s2, ...
        action_preds = self.action_head(state_positions)

        return action_preds

    def get_action(self, returns_to_go, states, actions, timesteps):
        """Get next action given context (for inference)."""
        action_preds = self(returns_to_go, states, actions, timesteps)
        return action_preds[:, -1]  # Last predicted action
```

Offline RL comparison:

| Method | Approach | OOD handling | Compute |
|--------|---------|-------------|---------|
| **CQL** | Conservative Q-values | Penalize unseen actions | Medium |
| **Decision Transformer** | Sequence modeling | Stays near data by design | High |
| **IQL** | Expectile regression | Implicit constraint | Low |
| **BCQ** | Batch-constrained | Only sample near data | Medium |

Key patterns:
1. **CQL conservative penalty** — logsumexp(Q_random) - E[Q_data]; pushes down OOD Q-values
2. **Decision Transformer** — frames RL as sequence prediction; condition on return-to-go for desired behavior
3. **Return conditioning** — at inference, set high return-to-go to elicit optimal actions
4. **No environment needed** — offline RL learns entirely from logged data; no exploration
5. **Interleaved tokens** — (return, state, action) triples form the sequence for transformer'''
    ),
]
