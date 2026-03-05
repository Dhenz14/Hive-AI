"""AI reasoning — GRPO, process reward models, tree-of-thought, and inference-time scaling."""

PAIRS = [
    (
        "ai/grpo-group-relative-policy-optimization",
        "Show GRPO (Group Relative Policy Optimization) for training code models: algorithm, loss function, and training loop without a reward model.",
        '''GRPO — Group Relative Policy Optimization:

```python
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Callable
import math


# --- GRPO Algorithm ---
#
# Key insight: Instead of training a separate reward model,
# GRPO uses GROUP-RELATIVE scoring. For each prompt, generate
# G completions, score them all, then use the relative ranking
# within the group as the reward signal.
#
# This eliminates reward model training entirely while still
# getting strong RL signal from self-comparison.


class GRPOTrainer:
    """Group Relative Policy Optimization trainer."""

    def __init__(
        self,
        model: AutoModelForCausalLM,
        ref_model: AutoModelForCausalLM,  # Frozen reference
        tokenizer: AutoTokenizer,
        reward_fn: Callable[[str, str], float],
        group_size: int = 8,
        kl_coeff: float = 0.1,
        clip_range: float = 0.2,
        lr: float = 1e-6,
    ):
        self.model = model
        self.ref_model = ref_model
        self.tokenizer = tokenizer
        self.reward_fn = reward_fn
        self.group_size = group_size
        self.kl_coeff = kl_coeff
        self.clip_range = clip_range
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    def generate_group(self, prompt: str) -> list[dict]:
        """Generate G completions for a single prompt."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        completions = []
        for _ in range(self.group_size):
            output = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.8,
                top_p=0.95,
            )
            response = self.tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )
            completions.append(response)

        return completions

    def compute_group_rewards(
        self, prompt: str, completions: list[str],
    ) -> torch.Tensor:
        """Score completions and normalize within group."""
        # Get raw scores
        raw_rewards = torch.tensor([
            self.reward_fn(prompt, c) for c in completions
        ])

        # Group-relative normalization (z-score within group)
        mean = raw_rewards.mean()
        std = raw_rewards.std()
        if std > 0:
            normalized = (raw_rewards - mean) / std
        else:
            normalized = torch.zeros_like(raw_rewards)

        return normalized

    def compute_log_probs(
        self, model, prompt_ids, response_ids,
    ) -> torch.Tensor:
        """Compute log probabilities of response given prompt."""
        input_ids = torch.cat([prompt_ids, response_ids], dim=1)
        with torch.no_grad() if model is self.ref_model else torch.enable_grad():
            outputs = model(input_ids)
            logits = outputs.logits[:, prompt_ids.shape[1]-1:-1, :]
            log_probs = F.log_softmax(logits, dim=-1)
            token_log_probs = log_probs.gather(2, response_ids.unsqueeze(-1)).squeeze(-1)
        return token_log_probs.sum(dim=1)

    def grpo_loss(
        self,
        prompt: str,
        completions: list[str],
        rewards: torch.Tensor,
    ) -> torch.Tensor:
        """
        GRPO loss: clipped surrogate objective with KL penalty.

        L = -E[min(r(θ) * A, clip(r(θ), 1-ε, 1+ε) * A)] + β * KL(π_θ || π_ref)

        where r(θ) = π_θ(y|x) / π_old(y|x)
              A = group-normalized reward
        """
        prompt_ids = self.tokenizer(
            prompt, return_tensors="pt",
        ).input_ids.to(self.model.device)

        total_loss = torch.tensor(0.0, device=self.model.device)

        for completion, advantage in zip(completions, rewards):
            resp_ids = self.tokenizer(
                completion, return_tensors="pt",
            ).input_ids.to(self.model.device)

            # Current policy log prob
            log_prob = self.compute_log_probs(self.model, prompt_ids, resp_ids)

            # Reference policy log prob (frozen)
            with torch.no_grad():
                ref_log_prob = self.compute_log_probs(
                    self.ref_model, prompt_ids, resp_ids,
                )

            # Importance ratio
            ratio = torch.exp(log_prob - ref_log_prob)

            # Clipped surrogate objective
            adv = advantage.to(self.model.device)
            surr1 = ratio * adv
            surr2 = torch.clamp(ratio, 1 - self.clip_range, 1 + self.clip_range) * adv
            policy_loss = -torch.min(surr1, surr2)

            # KL penalty (stay close to reference)
            kl = ref_log_prob - log_prob
            kl_penalty = self.kl_coeff * kl

            total_loss += policy_loss + kl_penalty

        return total_loss / len(completions)

    def train_step(self, prompt: str) -> dict:
        """Single GRPO training step."""
        # 1. Generate group of completions
        completions = self.generate_group(prompt)

        # 2. Score and normalize within group
        rewards = self.compute_group_rewards(prompt, completions)

        # 3. Compute loss and update
        self.optimizer.zero_grad()
        loss = self.grpo_loss(prompt, completions, rewards)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()

        return {
            "loss": loss.item(),
            "mean_reward": rewards.mean().item(),
            "max_reward": rewards.max().item(),
        }


# --- Reward function for code ---

def code_reward(prompt: str, completion: str) -> float:
    """Score code completion quality (0-1)."""
    score = 0.0

    # Has code blocks
    if "```" in completion:
        score += 0.3

    # Code runs without syntax errors
    import ast
    code_blocks = extract_python_blocks(completion)
    for code in code_blocks:
        try:
            ast.parse(code)
            score += 0.3
            break
        except SyntaxError:
            pass

    # Length and detail
    if len(completion) > 200:
        score += 0.2

    # Has explanation alongside code
    non_code = completion.replace("```", "").strip()
    if len(non_code) > 100:
        score += 0.2

    return min(score, 1.0)
```

GRPO patterns:
1. **No reward model** — uses group-relative normalization (z-score within batch) instead
2. **Generate G completions** — for each prompt, sample 4-16 responses and rank them
3. **Clipped surrogate** — PPO-style clipping prevents too-large policy updates
4. **KL penalty** — `β * KL(π_θ || π_ref)` keeps policy close to reference model
5. **Code-specific rewards** — AST parsing, execution testing, and structural quality signals'''
    ),
    (
        "ai/process-reward-models",
        "Show process reward models (PRMs) vs outcome reward models (ORMs): step-level scoring, training, and inference-time search.",
        '''Process Reward Models — step-level reasoning verification:

```python
import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional
import math


# --- ORM vs PRM ---
#
# ORM (Outcome Reward Model):
#   Scores the FINAL answer only. "Is the answer correct?"
#   Problem: Can't tell WHERE reasoning went wrong.
#
# PRM (Process Reward Model):
#   Scores EACH STEP of reasoning. "Is this step logically valid?"
#   Advantage: Catches errors early, enables step-level search.


# --- PRM Architecture ---

class ProcessRewardModel(nn.Module):
    """Score each reasoning step independently."""

    def __init__(self, base_model_name: str):
        super().__init__()
        self.base = AutoModelForCausalLM.from_pretrained(
            base_model_name, torch_dtype=torch.bfloat16,
        )
        hidden_size = self.base.config.hidden_size
        # Reward head: predicts step correctness
        self.reward_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Linear(hidden_size // 2, 1),
            nn.Sigmoid(),  # Output: 0.0 (wrong) to 1.0 (correct)
        )

    def forward(
        self, input_ids: torch.Tensor, step_positions: list[int],
    ) -> list[float]:
        """
        Score each reasoning step.

        step_positions: indices where each step ends (e.g., newline positions)
        Returns: list of scores, one per step
        """
        outputs = self.base(input_ids, output_hidden_states=True)
        hidden = outputs.hidden_states[-1]  # Last layer

        step_scores = []
        for pos in step_positions:
            step_hidden = hidden[0, pos, :]  # Hidden state at step boundary
            score = self.reward_head(step_hidden).item()
            step_scores.append(score)

        return step_scores


# --- PRM Training Data Format ---
#
# Each example: prompt + step-by-step solution with per-step labels
#
# {
#   "prompt": "What is 23 * 17?",
#   "steps": [
#     {"text": "I'll break this into 23 * 17 = 23 * (10 + 7)", "label": 1},
#     {"text": "23 * 10 = 230", "label": 1},
#     {"text": "23 * 7 = 161", "label": 1},  # correct
#     {"text": "230 + 161 = 391", "label": 1},
#   ]
# }
#
# Negative example (error at step 3):
# {
#   "prompt": "What is 23 * 17?",
#   "steps": [
#     {"text": "23 * 17 = 23 * (10 + 7)", "label": 1},
#     {"text": "23 * 10 = 230", "label": 1},
#     {"text": "23 * 7 = 151", "label": 0},  # WRONG: 23*7=161
#     {"text": "230 + 151 = 381", "label": 0},  # Cascading error
#   ]
# }


def train_prm_step(
    model: ProcessRewardModel,
    tokenizer: AutoTokenizer,
    prompt: str,
    steps: list[dict],  # [{"text": ..., "label": 0|1}, ...]
    optimizer: torch.optim.Optimizer,
) -> float:
    """Train PRM on step-labeled example."""
    # Build full text with step markers
    full_text = prompt + "\n"
    step_positions = []
    for step in steps:
        full_text += step["text"] + "\n"
        tokens = tokenizer(full_text, return_tensors="pt")
        step_positions.append(tokens.input_ids.shape[1] - 1)

    input_ids = tokenizer(full_text, return_tensors="pt").input_ids
    input_ids = input_ids.to(model.base.device)

    # Predict step scores
    predicted_scores = model(input_ids, step_positions)

    # Binary cross-entropy loss per step
    loss = 0.0
    for score, step in zip(predicted_scores, steps):
        target = float(step["label"])
        loss += -(target * math.log(score + 1e-8) +
                  (1 - target) * math.log(1 - score + 1e-8))
    loss /= len(steps)

    optimizer.zero_grad()
    loss_tensor = torch.tensor(loss, requires_grad=True)
    loss_tensor.backward()
    optimizer.step()

    return loss


# --- Best-of-N with PRM (inference-time search) ---

def best_of_n_with_prm(
    generator: AutoModelForCausalLM,
    prm: ProcessRewardModel,
    tokenizer: AutoTokenizer,
    prompt: str,
    n: int = 16,
    step_delimiter: str = "\n",
) -> tuple[str, float]:
    """Generate N solutions, score with PRM, return best."""
    candidates = []

    for _ in range(n):
        # Generate solution
        inputs = tokenizer(prompt, return_tensors="pt").to(generator.device)
        output = generator.generate(
            **inputs, max_new_tokens=512,
            do_sample=True, temperature=0.7,
        )
        solution = tokenizer.decode(
            output[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True,
        )

        # Score each step with PRM
        steps = solution.split(step_delimiter)
        full = prompt + "\n"
        positions = []
        for step in steps:
            if step.strip():
                full += step + "\n"
                toks = tokenizer(full, return_tensors="pt")
                positions.append(toks.input_ids.shape[1] - 1)

        if positions:
            input_ids = tokenizer(full, return_tensors="pt").input_ids
            step_scores = prm(input_ids.to(prm.base.device), positions)

            # Aggregate: minimum step score (weakest link)
            min_score = min(step_scores)
            # Or: product of step scores (all steps must be correct)
            product_score = math.prod(step_scores)

            candidates.append((solution, min_score, product_score))

    # Return candidate with highest minimum step score
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0], candidates[0][1]


# --- Beam search with PRM (step-level) ---

def prm_beam_search(
    generator, prm, tokenizer, prompt: str,
    beam_width: int = 4, max_steps: int = 10,
) -> str:
    """Step-level beam search guided by PRM."""
    beams = [{"text": prompt, "score": 1.0, "steps": []}]

    for step_idx in range(max_steps):
        all_candidates = []

        for beam in beams:
            # Generate next step candidates
            for _ in range(beam_width):
                next_step = generate_single_step(
                    generator, tokenizer, beam["text"],
                )
                # Score this step with PRM
                step_score = score_step(prm, tokenizer, beam["text"], next_step)

                all_candidates.append({
                    "text": beam["text"] + "\n" + next_step,
                    "score": beam["score"] * step_score,
                    "steps": beam["steps"] + [next_step],
                })

        # Keep top-k beams
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        beams = all_candidates[:beam_width]

        # Check if best beam is done
        if is_complete(beams[0]["text"]):
            break

    return beams[0]["text"]
```

Process Reward Models:
1. **Step-level scoring** — PRM scores each reasoning step, ORM only scores final answer
2. **Error localization** — identifies exactly where reasoning chain goes wrong
3. **Best-of-N search** — generate N solutions, PRM picks the one with strongest steps
4. **Beam search** — step-level beam search prunes bad reasoning paths early
5. **Min-step aggregation** — weakest step score predicts overall solution correctness'''
    ),
    (
        "ai/inference-time-compute-scaling",
        "Show inference-time compute scaling patterns: test-time search, self-consistency, tree-of-thought, and compute-optimal strategies.",
        '''Inference-time compute scaling patterns:

```python
import asyncio
from dataclasses import dataclass
from typing import Callable
import random
import math


# --- The Core Insight ---
#
# Instead of making the MODEL bigger, make INFERENCE smarter.
# Spending more compute at inference time (more samples, search,
# verification) can outperform a 10x larger model.
#
# Scaling laws: for reasoning tasks, doubling test-time compute
# can be worth 4-8x more training compute.


# --- Strategy 1: Self-Consistency (majority voting) ---

async def self_consistency(
    generate_fn: Callable,
    prompt: str,
    n_samples: int = 16,
    extract_answer: Callable = None,
) -> dict:
    """
    Generate N solutions, extract final answer from each,
    return majority-voted answer.

    Key insight: different reasoning paths that arrive at the
    same answer are likely correct.
    """
    # Generate N independent solutions (high temperature)
    solutions = await asyncio.gather(*[
        generate_fn(prompt, temperature=0.7)
        for _ in range(n_samples)
    ])

    # Extract final answers
    answers = [extract_answer(s) for s in solutions]
    answers = [a for a in answers if a is not None]

    # Majority vote
    from collections import Counter
    vote_counts = Counter(answers)
    best_answer, count = vote_counts.most_common(1)[0]

    return {
        "answer": best_answer,
        "confidence": count / len(answers),
        "n_solutions": len(solutions),
        "n_valid": len(answers),
        "vote_distribution": dict(vote_counts),
    }


# --- Strategy 2: Tree-of-Thought ---

@dataclass
class ThoughtNode:
    thought: str
    score: float
    children: list["ThoughtNode"]
    depth: int

    @property
    def is_terminal(self) -> bool:
        return self.depth >= 3 or "ANSWER:" in self.thought


async def tree_of_thought(
    generate_fn: Callable,
    evaluate_fn: Callable,
    prompt: str,
    breadth: int = 3,
    max_depth: int = 3,
    beam_width: int = 2,
) -> str:
    """
    Tree-of-Thought: structured exploration of reasoning paths.

    1. Generate B thought candidates at each step
    2. Evaluate each with a scoring function
    3. Keep top-K (beam width) and expand further
    4. Return highest-scoring complete path
    """
    root_thoughts = await asyncio.gather(*[
        generate_fn(
            f"{prompt}\n\nGenerate one step of reasoning (step 1):",
            temperature=0.8,
        )
        for _ in range(breadth)
    ])

    # Score initial thoughts
    nodes = []
    for thought in root_thoughts:
        score = await evaluate_fn(prompt, thought)
        nodes.append(ThoughtNode(thought, score, [], depth=1))

    # BFS with beam pruning
    for depth in range(2, max_depth + 1):
        # Keep top-K nodes
        nodes.sort(key=lambda n: n.score, reverse=True)
        active = nodes[:beam_width]

        next_nodes = []
        for node in active:
            if node.is_terminal:
                next_nodes.append(node)
                continue

            # Generate children
            children = await asyncio.gather(*[
                generate_fn(
                    f"{prompt}\n\nReasoning so far:\n{node.thought}\n\n"
                    f"Continue reasoning (step {depth}):",
                    temperature=0.7,
                )
                for _ in range(breadth)
            ])

            for child_thought in children:
                full = f"{node.thought}\n{child_thought}"
                score = await evaluate_fn(prompt, full)
                child = ThoughtNode(full, score, [], depth=depth)
                node.children.append(child)
                next_nodes.append(child)

        nodes = next_nodes

    # Return best complete path
    nodes.sort(key=lambda n: n.score, reverse=True)
    return nodes[0].thought


# --- Strategy 3: Compute-optimal allocation ---

def compute_optimal_strategy(
    difficulty: float,
    compute_budget: int,
) -> dict:
    """
    Allocate inference compute based on problem difficulty.

    Easy problems: 1 sample, greedy decoding
    Medium: self-consistency with 8 samples
    Hard: tree-of-thought or best-of-N with PRM

    The key insight from DeepMind's research:
    - Easy tasks: more compute = diminishing returns
    - Hard tasks: more compute = linear improvement
    - Optimal allocation: concentrate compute on hard problems
    """
    if difficulty < 0.3:
        return {
            "strategy": "greedy",
            "n_samples": 1,
            "temperature": 0.0,
            "description": "Single greedy decode (easy problem)",
        }
    elif difficulty < 0.6:
        n = min(compute_budget, 8)
        return {
            "strategy": "self_consistency",
            "n_samples": n,
            "temperature": 0.7,
            "description": f"Self-consistency with {n} samples",
        }
    elif difficulty < 0.8:
        n = min(compute_budget, 16)
        return {
            "strategy": "best_of_n_with_prm",
            "n_samples": n,
            "temperature": 0.8,
            "description": f"Best-of-{n} with process reward model",
        }
    else:
        return {
            "strategy": "tree_of_thought",
            "breadth": 4,
            "depth": 4,
            "beam_width": 3,
            "temperature": 0.8,
            "description": "Full tree-of-thought search",
        }


# --- Strategy 4: Iterative refinement ---

async def iterative_refinement(
    generate_fn: Callable,
    evaluate_fn: Callable,
    prompt: str,
    max_iterations: int = 5,
    threshold: float = 0.9,
) -> str:
    """
    Generate → Evaluate → Critique → Regenerate loop.
    Stops when quality threshold met or max iterations reached.
    """
    solution = await generate_fn(prompt, temperature=0.3)

    for i in range(max_iterations):
        score = await evaluate_fn(prompt, solution)
        if score >= threshold:
            break

        # Generate critique
        critique = await generate_fn(
            f"Problem: {prompt}\n\n"
            f"Current solution:\n{solution}\n\n"
            f"Identify errors or weaknesses in this solution. "
            f"Be specific about what's wrong and how to fix it.",
            temperature=0.3,
        )

        # Regenerate with critique
        solution = await generate_fn(
            f"Problem: {prompt}\n\n"
            f"Previous attempt:\n{solution}\n\n"
            f"Feedback:\n{critique}\n\n"
            f"Write an improved solution addressing all feedback:",
            temperature=0.3,
        )

    return solution
```

Inference-time compute scaling:
1. **Self-consistency** — majority vote across N independent reasoning chains
2. **Tree-of-thought** — BFS with beam pruning over structured reasoning steps
3. **Compute-optimal allocation** — concentrate test-time compute on hard problems
4. **Iterative refinement** — generate → critique → regenerate loop until quality threshold
5. **Scaling law** — doubling test-time compute often beats 4-8x more training compute'''
    ),
]
