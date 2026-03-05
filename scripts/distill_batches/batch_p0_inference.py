"""P0 Batch: Inference engines, constrained decoding, DPO variants, LLM evaluation."""

PAIRS = [
    (
        "constrained decoding and grammar-guided generation",
        "Explain how constrained decoding and grammar-guided generation work in LLM inference. How do tools like Outlines and llama.cpp GBNF grammars guarantee structured output? Show implementations.",
        """## Constrained Decoding: Guaranteeing Structured LLM Output

### The Problem with Prompting for JSON

When you ask an LLM to "respond in JSON", it usually does — but sometimes it doesn't. It might add markdown fences, include a preamble, miss a closing brace, or output an invalid value for an enum field. For production systems that parse LLM output programmatically, "usually works" is unacceptable.

Constrained decoding solves this at the **token sampling level**: before the model picks each token, you mask out all tokens that would violate the desired format. The model can only generate valid output because invalid tokens literally have zero probability.

### How It Works: Token Masking

```python
import numpy as np
from dataclasses import dataclass


@dataclass
class TokenConstraint:
    \"\"\"
    At each generation step, provides a mask of allowed tokens.

    The key insight: we're not changing what the model WANTS to say,
    only HOW it says it. The model still picks the highest-probability
    token among the allowed ones. This preserves quality while
    guaranteeing format.
    \"\"\"
    allowed_token_ids: set[int]

    def apply_mask(self, logits: np.ndarray) -> np.ndarray:
        masked = np.full_like(logits, -float("inf"))
        for tid in self.allowed_token_ids:
            masked[tid] = logits[tid]
        return masked


def constrained_sample(logits: np.ndarray, constraint: TokenConstraint, temperature: float = 1.0) -> int:
    \"\"\"Sample a token respecting the constraint mask.\"\"\"
    masked_logits = constraint.apply_mask(logits)
    if temperature > 0:
        probs = np.exp(masked_logits / temperature)
        probs = probs / probs.sum()
        return np.random.choice(len(probs), p=probs)
    else:
        return int(np.argmax(masked_logits))
```

### JSON Schema to Finite State Machine

The real power comes from converting a JSON schema into a finite state machine (FSM) that tracks where we are in the output and what tokens are valid next.

```python
from enum import Enum, auto


class JsonState(Enum):
    START = auto()          # Expecting { to open object
    KEY_OR_END = auto()     # Expecting "key" or }
    KEY = auto()            # Inside a key string
    COLON = auto()          # Expecting :
    VALUE = auto()          # Expecting a value (string, number, bool, etc.)
    STRING_VALUE = auto()   # Inside a string value
    NUMBER_VALUE = auto()   # Inside a number
    COMMA_OR_END = auto()   # Expecting , or }
    DONE = auto()           # Complete valid JSON


class JsonFSM:
    \"\"\"
    Finite state machine that tracks position in JSON generation.

    Given a JSON schema like:
      {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}}

    The FSM knows that after '{"name": ' only string tokens are valid,
    and after '{"name": "Alice", "age": ' only integer tokens are valid.

    Why FSM and not regex? Because JSON is context-free (nested braces),
    which regular expressions can't handle. The FSM uses a stack for
    nesting depth, making it a pushdown automaton.
    \"\"\"

    def __init__(self, schema: dict, tokenizer):
        self.schema = schema
        self.tokenizer = tokenizer
        self.state = JsonState.START
        self.stack = []  # For nested objects/arrays
        self.current_key = None
        self.required_keys = set(schema.get("required", []))
        self.seen_keys = set()

    def get_allowed_tokens(self) -> set[int]:
        \"\"\"Return token IDs that are valid in the current state.\"\"\"
        vocab = self.tokenizer.get_vocab()

        if self.state == JsonState.START:
            return {tid for tok, tid in vocab.items() if tok.strip().startswith("{")}

        elif self.state == JsonState.KEY_OR_END:
            allowed = set()
            # Allow closing brace if all required keys are present
            if self.required_keys.issubset(self.seen_keys):
                allowed |= {tid for tok, tid in vocab.items() if tok.strip().startswith("}")}
            # Allow quote to start a key
            remaining = set(self.schema.get("properties", {}).keys()) - self.seen_keys
            if remaining:
                allowed |= {tid for tok, tid in vocab.items() if tok.strip().startswith('"')}
            return allowed

        elif self.state == JsonState.VALUE:
            prop_schema = self.schema.get("properties", {}).get(self.current_key, {})
            prop_type = prop_schema.get("type", "string")
            if prop_type == "string":
                return {tid for tok, tid in vocab.items() if tok.strip().startswith('"')}
            elif prop_type == "integer":
                return {tid for tok, tid in vocab.items()
                        if tok.strip() and tok.strip()[0] in "0123456789-"}
            elif prop_type == "boolean":
                return {tid for tok, tid in vocab.items()
                        if tok.strip().startswith(("true", "false"))}

        # Fallback: allow all (shouldn't reach here in well-defined schema)
        return set(vocab.values())

    def advance(self, token: str):
        \"\"\"Update FSM state based on generated token.\"\"\"
        t = token.strip()
        if self.state == JsonState.START and t.startswith("{"):
            self.state = JsonState.KEY_OR_END
        elif self.state == JsonState.KEY_OR_END and t.startswith('"'):
            self.state = JsonState.KEY
        elif self.state == JsonState.KEY and t.endswith('"'):
            self.current_key = t.strip('"')
            self.seen_keys.add(self.current_key)
            self.state = JsonState.COLON
        elif self.state == JsonState.COLON and ":" in t:
            self.state = JsonState.VALUE
        elif self.state == JsonState.VALUE:
            self.state = JsonState.COMMA_OR_END
        elif self.state == JsonState.COMMA_OR_END:
            if "," in t:
                self.state = JsonState.KEY_OR_END
            elif "}" in t:
                self.state = JsonState.DONE
```

### GBNF Grammars in llama.cpp

llama.cpp uses Backus-Naur Form (GBNF) grammars for constrained decoding. This is more general than JSON-only constraints:

```
# GBNF grammar for a SQL SELECT statement
root   ::= "SELECT " columns " FROM " table where? ";"
columns ::= column ("," " " column)*
column  ::= [a-zA-Z_][a-zA-Z0-9_]*
table   ::= [a-zA-Z_][a-zA-Z0-9_]*
where   ::= " WHERE " condition
condition ::= column " " operator " " value
operator ::= "=" | "!=" | ">" | "<" | ">=" | "<="
value   ::= [0-9]+ | "'" [^']* "'"
```

This grammar ensures the model can ONLY output valid SQL SELECT statements. Every token that would break the grammar is masked to zero probability.

### Performance Impact

Constrained decoding adds ~5-10% overhead per token (for the mask computation), but eliminates all retry/parsing failures. For production systems, this tradeoff is overwhelmingly positive: zero parsing errors vs. occasional 5-10% slowdown.

The deeper implication: constrained decoding means you can use smaller, faster models for structured output tasks because the format correctness is guaranteed by the engine, not the model. A 7B model with grammar constraints can match a 70B model's JSON reliability.""",
    ),

    (
        "DPO and modern preference optimization variants",
        "Explain Direct Preference Optimization (DPO) and its successors — KTO, ORPO, SimPO, online DPO. When should you use each? Show the loss functions and practical training code.",
        """## Preference Optimization: Teaching Models What Humans Prefer

### Why Preference Optimization Exists

Supervised fine-tuning (SFT) teaches a model to imitate demonstrations. But imitation has a ceiling: the model can only be as good as the training data. Preference optimization goes further by teaching the model which of two outputs is BETTER — even if neither is perfect. This is how you get models that are helpful, harmless, and honest.

### DPO: The Breakthrough (Rafailov et al., 2023)

RLHF required training a separate reward model, then using PPO to optimize against it — complex, unstable, and expensive. DPO's insight: you can skip the reward model entirely by deriving a closed-form loss from the preference data.

```python
import torch
import torch.nn.functional as F


def dpo_loss(
    policy_chosen_logps: torch.Tensor,    # log P(chosen | x) under current model
    policy_rejected_logps: torch.Tensor,   # log P(rejected | x) under current model
    ref_chosen_logps: torch.Tensor,        # log P(chosen | x) under reference model
    ref_rejected_logps: torch.Tensor,      # log P(rejected | x) under reference model
    beta: float = 0.1,                      # Controls how far policy can drift from reference
) -> torch.Tensor:
    \"\"\"
    DPO loss: directly optimize the policy from preference pairs.

    The math: instead of training reward model R, then optimizing
    policy π to maximize R while staying close to reference π_ref,
    DPO derives the OPTIMAL policy in closed form:

        π*(y|x) ∝ π_ref(y|x) · exp(R(x,y) / β)

    Rearranging gives the implicit reward:
        R(x,y) = β · log(π(y|x) / π_ref(y|x))

    The loss pushes the implicit reward of chosen > rejected.

    Why beta matters: small beta (0.01) = aggressive optimization,
    model diverges far from reference. Large beta (0.5) = conservative,
    stays close to reference. 0.1 is the standard default.
    \"\"\"
    # Implicit rewards
    chosen_rewards = beta * (policy_chosen_logps - ref_chosen_logps)
    rejected_rewards = beta * (policy_rejected_logps - ref_rejected_logps)

    # Bradley-Terry preference model: P(chosen > rejected) = sigmoid(reward_diff)
    loss = -F.logsigmoid(chosen_rewards - rejected_rewards)
    return loss.mean()
```

### KTO: When You Only Have Thumbs Up/Down (Ethayarajh et al., 2024)

DPO requires PAIRED preferences (chosen vs. rejected for the SAME prompt). KTO works with unpaired data — just "good" or "bad" labels on individual outputs.

```python
def kto_loss(
    policy_logps: torch.Tensor,       # log P(y | x) under current model
    ref_logps: torch.Tensor,          # log P(y | x) under reference model
    is_desirable: torch.Tensor,       # 1 for good outputs, 0 for bad
    beta: float = 0.1,
) -> torch.Tensor:
    \"\"\"
    KTO (Kahneman-Tversky Optimization): uses prospect theory.

    The key insight from behavioral economics: humans feel losses
    more strongly than gains (loss aversion). KTO bakes this in:
    the penalty for generating undesirable output is LARGER than
    the reward for generating desirable output.

    When to use KTO over DPO:
    - You have thumbs-up/down data (not paired comparisons)
    - Your data is imbalanced (lots of good, few bad, or vice versa)
    - You're working with implicit feedback (clicks, usage time)
    \"\"\"
    log_ratio = policy_logps - ref_logps
    kl = (torch.exp(log_ratio) - 1 - log_ratio).mean().clamp(min=0)

    desirable_mask = is_desirable.bool()
    undesirable_mask = ~desirable_mask

    # Desirable: reward for being better than reference
    if desirable_mask.any():
        desirable_loss = -F.logsigmoid(beta * log_ratio[desirable_mask] - kl)
    else:
        desirable_loss = torch.tensor(0.0)

    # Undesirable: penalty for not being worse than reference (loss aversion)
    if undesirable_mask.any():
        undesirable_loss = -F.logsigmoid(-beta * log_ratio[undesirable_mask] + kl)
    else:
        undesirable_loss = torch.tensor(0.0)

    # Loss aversion: undesirable weight > desirable weight
    lambda_d = 1.0
    lambda_u = 1.5  # 50% higher penalty for bad outputs

    return (lambda_d * desirable_loss.mean() + lambda_u * undesirable_loss.mean())
```

### ORPO: No Reference Model Needed (Hong et al., 2024)

```python
def orpo_loss(
    policy_chosen_logps: torch.Tensor,
    policy_rejected_logps: torch.Tensor,
    sft_loss: torch.Tensor,   # Standard cross-entropy loss on chosen
    alpha: float = 0.1,
) -> torch.Tensor:
    \"\"\"
    ORPO (Odds Ratio Preference Optimization): combines SFT + preference
    in a single training phase. No reference model needed.

    The insight: instead of computing how the policy differs from
    a reference (like DPO), directly optimize the ODDS RATIO between
    chosen and rejected. This eliminates the need to load a reference
    model, saving 50% GPU memory.

    When to use ORPO:
    - Memory-constrained training (can't fit policy + reference)
    - Starting from a base model (no good reference available)
    - Want simpler training pipeline (one phase instead of SFT→DPO)
    \"\"\"
    # Odds: P(y) / (1 - P(y))
    chosen_odds = torch.exp(policy_chosen_logps) / (1 - torch.exp(policy_chosen_logps) + 1e-10)
    rejected_odds = torch.exp(policy_rejected_logps) / (1 - torch.exp(policy_rejected_logps) + 1e-10)

    # Log odds ratio
    log_odds_ratio = torch.log(chosen_odds / (rejected_odds + 1e-10) + 1e-10)

    preference_loss = -F.logsigmoid(log_odds_ratio)

    return sft_loss + alpha * preference_loss.mean()
```

### SimPO: Length-Normalized, Reference-Free (Meng et al., 2024)

```python
def simpo_loss(
    policy_chosen_logps: torch.Tensor,
    policy_rejected_logps: torch.Tensor,
    chosen_length: torch.Tensor,
    rejected_length: torch.Tensor,
    beta: float = 2.0,
    gamma: float = 1.0,   # Reward margin
) -> torch.Tensor:
    \"\"\"
    SimPO: Simple Preference Optimization.

    Two improvements over DPO:
    1. Length normalization: divide log-probs by sequence length.
       Without this, models learn to prefer SHORTER outputs
       (fewer tokens = higher total log-prob). This is a known
       DPO failure mode called the 'length exploitation' problem.

    2. Target reward margin (gamma): instead of just preferring
       chosen over rejected, require a MINIMUM gap. This prevents
       the model from being barely better on chosen — it must be
       significantly better.

    SimPO consistently outperforms DPO on benchmarks by 3-7 points
    while being simpler (no reference model needed).
    \"\"\"
    # Length-normalized rewards (this is the key difference from DPO)
    chosen_rewards = beta * (policy_chosen_logps / chosen_length)
    rejected_rewards = beta * (policy_rejected_logps / rejected_length)

    # Margin-based preference: chosen must be better by at least gamma
    loss = -F.logsigmoid(chosen_rewards - rejected_rewards - gamma)
    return loss.mean()
```

### Decision Matrix

| Method | Needs Reference Model | Needs Paired Data | Memory | Best For |
|--------|----------------------|-------------------|--------|----------|
| **DPO** | Yes | Yes | 2× model | Gold standard, paired preferences |
| **KTO** | Yes | No (unpaired) | 2× model | Thumbs up/down, implicit feedback |
| **ORPO** | No | Yes | 1× model | Memory-constrained, single-phase training |
| **SimPO** | No | Yes | 1× model | Best overall quality, production use |
| **Online DPO** | Yes | Generated on-the-fly | 2× model + generation | Iterative improvement, self-play |

For most practitioners in 2025-2026: **start with SimPO**. It's simpler, cheaper, and typically outperforms DPO. Use KTO if you only have binary feedback. Use online DPO for the absolute best results when you can afford the compute.""",
    ),

    (
        "LLM-as-judge evaluation methodology",
        "How do you use LLMs to evaluate other LLMs? Explain the LLM-as-judge pattern, its biases and mitigations, and show a complete evaluation framework with working code.",
        """## LLM-as-Judge: Automated Evaluation That Scales

### Why Human Evaluation Doesn't Scale

Human evaluation is the gold standard — but it costs $5-20 per evaluation, takes days, and has high inter-annotator disagreement (typically 70-80% agreement on subjective quality). For iterative model development where you need to evaluate thousands of outputs per experiment, this is too slow and expensive.

LLM-as-judge uses a strong model (like Claude or GPT-4) to evaluate a weaker model's outputs. When calibrated properly, it correlates 80-90% with human preferences at 1000× lower cost.

### The Core Pattern

```python
import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class JudgmentResult:
    score: float           # 1-5 or 1-10 scale
    reasoning: str         # Why this score
    dimensions: dict       # Per-dimension scores
    confidence: float      # Judge's self-assessed confidence


def llm_judge(
    llm_fn,
    instruction: str,
    response: str,
    reference: Optional[str] = None,
    dimensions: list[str] = None,
) -> JudgmentResult:
    \"\"\"
    Evaluate a response using an LLM judge.

    Why structured rubrics matter: without specific criteria,
    judges default to 'this sounds good' and cluster around 4/5.
    Explicit dimensions force the judge to evaluate each aspect
    separately, producing more discriminative scores.
    \"\"\"
    if dimensions is None:
        dimensions = ["correctness", "completeness", "clarity", "code_quality"]

    rubric = "\\n".join(f"- **{d}** (1-5): " + {
        "correctness": "Are the facts and code correct? Does it compile/run?",
        "completeness": "Does it fully address the question? Any missing aspects?",
        "clarity": "Is the explanation clear? Could a developer follow it?",
        "code_quality": "Is the code production-ready? Type hints, error handling, tests?",
        "reasoning_depth": "Does it explain WHY, not just WHAT? Are tradeoffs discussed?",
        "practical_value": "Could someone use this code in a real project?",
    }.get(d, f"Rate the {d} from 1 (poor) to 5 (excellent).") for d in dimensions)

    ref_section = f"\\n\\nReference answer (for comparison):\\n{reference}" if reference else ""

    prompt = f\"\"\"You are an expert code reviewer evaluating an AI assistant's response.

## Instruction
{instruction}

## Response to Evaluate
{response}{ref_section}

## Evaluation Rubric
Rate each dimension from 1 (poor) to 5 (excellent):
{rubric}

## Output Format
Respond with EXACTLY this JSON format:
{{
    "reasoning": "Brief explanation of your evaluation",
    "scores": {{{", ".join(f'"{d}": <1-5>' for d in dimensions)}}},
    "overall": <1-5 weighted average>,
    "confidence": <0.0-1.0 how confident you are in this evaluation>
}}\"\"\"

    raw = llm_fn(prompt)

    # Parse JSON from response (handle markdown fences)
    json_match = re.search(r"\\{[^{}]*(?:\\{[^{}]*\\}[^{}]*)*\\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return JudgmentResult(
                score=data.get("overall", 3.0),
                reasoning=data.get("reasoning", ""),
                dimensions=data.get("scores", {}),
                confidence=data.get("confidence", 0.5),
            )
        except json.JSONDecodeError:
            pass

    return JudgmentResult(score=3.0, reasoning="Failed to parse judge output", dimensions={}, confidence=0.0)
```

### Known Biases and Mitigations

```python
class DebiasedJudge:
    \"\"\"
    LLM judges have systematic biases. The three biggest:

    1. Position bias: prefers the FIRST response in A/B comparisons
       Mitigation: evaluate both orderings, average the scores

    2. Verbosity bias: longer responses score higher regardless of quality
       Mitigation: normalize by length, or instruct judge to penalize padding

    3. Self-enhancement bias: models prefer outputs that match their own style
       Mitigation: use a different model family as judge than the one being evaluated
    \"\"\"

    def __init__(self, judge_fn, n_evaluations: int = 3):
        self.judge_fn = judge_fn
        self.n_evaluations = n_evaluations

    def evaluate_pair(self, instruction: str, response_a: str, response_b: str) -> dict:
        \"\"\"
        Compare two responses with position-bias mitigation.
        Evaluates in BOTH orderings and averages.
        \"\"\"
        # Order 1: A first
        result_ab = self.judge_fn(
            f"Compare these two responses to: {instruction}\\n\\n"
            f"Response 1:\\n{response_a}\\n\\nResponse 2:\\n{response_b}\\n\\n"
            f"Which is better? Reply with JSON: {{\\"winner\\": 1 or 2, \\"reasoning\\": \\"...\\"}}"
        )

        # Order 2: B first (mitigate position bias)
        result_ba = self.judge_fn(
            f"Compare these two responses to: {instruction}\\n\\n"
            f"Response 1:\\n{response_b}\\n\\nResponse 2:\\n{response_a}\\n\\n"
            f"Which is better? Reply with JSON: {{\\"winner\\": 1 or 2, \\"reasoning\\": \\"...\\"}}"
        )

        # If both orderings agree, high confidence
        # If they disagree, it's a tie (position bias was the deciding factor)
        return {
            "order_ab": result_ab,
            "order_ba": result_ba,
            "agreement": "consistent" if result_ab != result_ba else "position_bias_detected",
        }

    def evaluate_single(self, instruction: str, response: str) -> JudgmentResult:
        \"\"\"
        Multi-evaluation with aggregation for stability.

        Why multiple evaluations? LLM judges have ~10-15% variance
        between identical calls. Averaging 3 evaluations reduces
        this to ~5% variance — cheap insurance for reliable scores.
        \"\"\"
        results = []
        for _ in range(self.n_evaluations):
            result = llm_judge(self.judge_fn, instruction, response)
            results.append(result)

        # Aggregate: median score (robust to outliers)
        scores = sorted(r.score for r in results)
        median_score = scores[len(scores) // 2]

        # Aggregate dimensions
        all_dims = {}
        for r in results:
            for dim, score in r.dimensions.items():
                all_dims.setdefault(dim, []).append(score)
        median_dims = {dim: sorted(scores)[len(scores) // 2] for dim, scores in all_dims.items()}

        return JudgmentResult(
            score=median_score,
            reasoning=results[0].reasoning,
            dimensions=median_dims,
            confidence=sum(r.confidence for r in results) / len(results),
        )
```

### Complete Evaluation Framework

```python
class EvalHarness:
    \"\"\"
    Full evaluation pipeline: run challenges, judge outputs, report.
    \"\"\"

    def __init__(self, judge, challenges: list[dict]):
        self.judge = judge
        self.challenges = challenges

    def evaluate_model(self, model_fn) -> dict:
        results = []
        for challenge in self.challenges:
            response = model_fn(challenge["instruction"])
            judgment = self.judge.evaluate_single(
                challenge["instruction"], response
            )
            results.append({
                "challenge_id": challenge.get("id", "unknown"),
                "domain": challenge.get("domain", "general"),
                "score": judgment.score,
                "dimensions": judgment.dimensions,
                "confidence": judgment.confidence,
            })

        # Aggregate by domain
        from collections import defaultdict
        domain_scores = defaultdict(list)
        for r in results:
            domain_scores[r["domain"]].append(r["score"])

        report = {
            "overall": sum(r["score"] for r in results) / len(results),
            "by_domain": {
                domain: sum(scores) / len(scores)
                for domain, scores in domain_scores.items()
            },
            "n_challenges": len(results),
            "weak_areas": [
                domain for domain, scores in domain_scores.items()
                if sum(scores) / len(scores) < 3.0
            ],
        }
        return report


# Usage
challenges = [
    {"id": "py001", "domain": "python", "instruction": "Implement an LRU cache in Python with O(1) get/put."},
    {"id": "rs001", "domain": "rust", "instruction": "Implement a thread-safe queue in Rust using Arc<Mutex<VecDeque<T>>>."},
    {"id": "go001", "domain": "go", "instruction": "Build an HTTP middleware chain in Go with logging and auth."},
]

# judge = DebiasedJudge(your_judge_llm_fn)
# harness = EvalHarness(judge, challenges)
# report = harness.evaluate_model(your_model_fn)
# print(f"Overall: {report['overall']:.2f}, Weak areas: {report['weak_areas']}")
```

The critical takeaway: LLM-as-judge is a tool, not a replacement for human evaluation. Use it for rapid iteration during development, then validate key decisions with human evaluators. The 80-90% correlation with humans is good enough for "which experiment is better" but not for "is this model safe to deploy".""",
    ),

    (
        "GRPO and reward-free reinforcement learning for code",
        "Explain Group Relative Policy Optimization (GRPO) — how does it enable RL training for code models without a reward model? Show the algorithm, loss function, and a practical training loop.",
        """## GRPO: Reinforcement Learning Without a Reward Model

### Why GRPO Matters for Code Models

Traditional RLHF requires training a separate reward model on human preferences, then using PPO to optimize the policy against it. This is expensive (reward model training + PPO instability) and error-prone (reward hacking).

GRPO (DeepSeek, 2024) eliminates the reward model by using **group-relative scoring**: generate multiple outputs for the same prompt, score them with a verifiable signal (code execution, test pass rate), then use the relative rankings within each group as the reward signal.

For code, this is natural: execution feedback IS the reward.

### The Algorithm

```
For each training batch:
  1. Sample prompt x from dataset
  2. Generate K completions {y_1, ..., y_K} from current policy π
  3. Score each completion: r_i = execute_and_score(y_i)
  4. Normalize scores within the group:
     advantage_i = (r_i - mean(r)) / std(r)
  5. Update policy to increase probability of high-advantage completions
     and decrease probability of low-advantage completions
```

### Implementation

```python
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from dataclasses import dataclass


@dataclass
class GRPOConfig:
    group_size: int = 8        # K: completions per prompt
    beta: float = 0.04         # KL penalty coefficient
    clip_range: float = 0.2    # PPO-style clipping
    max_new_tokens: int = 512
    temperature: float = 0.8   # Sampling temperature for diversity
    num_epochs: int = 3
    learning_rate: float = 1e-6


def compute_grpo_loss(
    policy_logprobs: torch.Tensor,      # [batch, group_size, seq_len]
    ref_logprobs: torch.Tensor,         # [batch, group_size, seq_len]
    advantages: torch.Tensor,            # [batch, group_size] — group-normalized
    mask: torch.Tensor,                  # [batch, group_size, seq_len] — padding mask
    config: GRPOConfig,
) -> torch.Tensor:
    \"\"\"
    GRPO loss function.

    The key difference from PPO: advantages are computed from
    GROUP-RELATIVE scores, not from a learned value function.
    This eliminates the critic network entirely.

    Why group-relative? Absolute scores are noisy (a score of 0.7
    means different things for different problems). But WITHIN a
    group of K completions for the SAME prompt, relative ranking
    is stable and meaningful.
    \"\"\"
    # Per-token log probability ratio
    ratio = torch.exp(policy_logprobs - ref_logprobs)  # π / π_ref

    # PPO-style clipping for stability
    clipped_ratio = torch.clamp(ratio, 1 - config.clip_range, 1 + config.clip_range)

    # Expand advantages to per-token
    advantages_expanded = advantages.unsqueeze(-1).expand_as(policy_logprobs)

    # Clipped surrogate objective (take the pessimistic bound)
    surr1 = ratio * advantages_expanded
    surr2 = clipped_ratio * advantages_expanded
    policy_loss = -torch.min(surr1, surr2)

    # KL penalty to prevent drift from reference
    kl = (ref_logprobs - policy_logprobs).mean()
    kl_penalty = config.beta * kl

    # Apply mask and average
    masked_loss = (policy_loss * mask).sum() / mask.sum()
    return masked_loss + kl_penalty


def score_code_completions(completions: list[str], test_code: str) -> list[float]:
    \"\"\"
    Score code completions by execution.

    Scoring rubric (0.0 to 1.0):
    - 0.0: Doesn't compile/parse
    - 0.3: Parses but fails all tests
    - 0.5: Passes some tests
    - 0.8: Passes all tests
    - 1.0: Passes all tests + clean code signals (type hints, docstrings)
    \"\"\"
    import subprocess
    import tempfile
    import ast

    scores = []
    for completion in completions:
        score = 0.0

        # Check if it parses
        try:
            ast.parse(completion)
            score = 0.3
        except SyntaxError:
            scores.append(0.0)
            continue

        # Check if tests pass
        combined = f"{completion}\\n\\n{test_code}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(combined)
            f.flush()
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", f.name, "-v", "--tb=short"],
                    capture_output=True, text=True, timeout=30,
                )
                # Parse pytest output for pass/fail count
                output = result.stdout + result.stderr
                if "passed" in output:
                    import re
                    passed = re.search(r"(\\d+) passed", output)
                    failed = re.search(r"(\\d+) failed", output)
                    n_passed = int(passed.group(1)) if passed else 0
                    n_failed = int(failed.group(1)) if failed else 0
                    total = n_passed + n_failed
                    if total > 0:
                        pass_rate = n_passed / total
                        score = 0.3 + 0.5 * pass_rate  # 0.3-0.8

                    # Bonus for code quality signals
                    if pass_rate == 1.0:
                        if "def " in completion and ":" in completion:
                            score += 0.05  # Has functions
                        if "->" in completion or ": " in completion:
                            score += 0.05  # Type hints
                        if '\"\"\"' in completion or "'''" in completion:
                            score += 0.05  # Docstrings
                        score = min(score, 1.0)
            except subprocess.TimeoutExpired:
                score = 0.1  # Ran but hung — partial credit
            except Exception:
                pass

        scores.append(score)
    return scores


def grpo_training_step(
    model,
    ref_model,
    tokenizer,
    prompts: list[str],
    test_cases: list[str],
    config: GRPOConfig,
    optimizer: torch.optim.Optimizer,
):
    \"\"\"
    One GRPO training step:
    1. Generate K completions per prompt
    2. Score via execution
    3. Compute group-normalized advantages
    4. Update policy
    \"\"\"
    all_completions = []
    all_scores = []

    # Step 1: Generate completions
    for prompt in prompts:
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        completions = []
        for _ in range(config.group_size):
            with torch.no_grad():
                output = model.generate(
                    **inputs,
                    max_new_tokens=config.max_new_tokens,
                    temperature=config.temperature,
                    do_sample=True,
                )
            completion = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            completions.append(completion)
        all_completions.append(completions)

    # Step 2: Score via execution
    for completions, tests in zip(all_completions, test_cases):
        scores = score_code_completions(completions, tests)
        all_scores.append(scores)

    # Step 3: Group-normalize advantages
    advantages = []
    for scores in all_scores:
        scores_t = torch.tensor(scores, dtype=torch.float32)
        mean = scores_t.mean()
        std = scores_t.std() + 1e-8
        normalized = (scores_t - mean) / std
        advantages.append(normalized)
    advantages = torch.stack(advantages)  # [batch, group_size]

    # Step 4: Compute loss and update (simplified — full version needs per-token logprobs)
    # In practice, you'd re-tokenize completions, compute logprobs under policy and ref
    # loss = compute_grpo_loss(policy_logprobs, ref_logprobs, advantages, mask, config)
    # loss.backward()
    # optimizer.step()

    stats = {
        "avg_score": sum(sum(s) for s in all_scores) / sum(len(s) for s in all_scores),
        "pass_rate": sum(1 for scores in all_scores for s in scores if s >= 0.8) / sum(len(s) for s in all_scores),
        "advantage_std": advantages.std().item(),
    }
    return stats
```

### Why GRPO Beats DPO for Code

DPO requires pre-collected preference pairs (chosen/rejected). These are static — the model can't discover solutions beyond the dataset. GRPO generates NEW completions every training step, scores them live, and learns from its own successes and failures.

This is especially powerful for code because:
1. **Execution feedback is free** — no human annotators needed
2. **Diversity matters** — K samples explore different solution strategies
3. **Self-improvement** — as the model improves, it generates harder challenges and better solutions

The practical training recipe: start with SFT on curated data (your 2000+ pairs), then run 3-5 epochs of GRPO using your eval challenges as the execution environment. Expect 5-15% improvement on pass@1 over SFT alone.""",
    ),

    (
        "long context management and retrieval augmented generation",
        "How do you effectively manage long contexts in LLM applications? Compare RAG vs. long-context models, explain context compression techniques, and show practical implementations for handling documents that exceed context windows.",
        """## Long Context: When Your Data Doesn't Fit

### The Fundamental Tradeoff

Long-context models (128K-1M tokens) seem like they'd eliminate the need for RAG. But there are three reasons RAG is still essential:

1. **Cost**: Processing 100K tokens costs 50-100× more than retrieving 4K relevant tokens
2. **Needle-in-haystack degradation**: Models lose accuracy on information buried in the middle of long contexts (the "lost in the middle" problem, Liu et al. 2024)
3. **Freshness**: Long context requires reprocessing the entire document on every query; RAG indexes once and queries cheaply

The right approach depends on your data:

| Scenario | Best Approach |
|----------|---------------|
| Single document, few queries | Long context (just stuff it in) |
| Many documents, many queries | RAG (index once, query many) |
| Complex reasoning over full document | Long context + RAG hybrid |
| Real-time/streaming data | RAG with incremental indexing |

### Context Compression: Fitting More Into Less

```python
from dataclasses import dataclass


@dataclass
class CompressedContext:
    original_tokens: int
    compressed_tokens: int
    content: str
    compression_ratio: float


def compress_context_extractive(
    text: str,
    query: str,
    llm_fn,
    target_tokens: int = 2000,
) -> CompressedContext:
    \"\"\"
    Extractive compression: keep only the sentences most relevant to the query.

    Why extractive over abstractive? Extractive preserves exact quotes,
    numbers, and code — critical for factual accuracy. Abstractive
    compression (summarization) can hallucinate details.
    \"\"\"
    import re

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\\s+', text)
    original_tokens = len(text.split())

    if original_tokens <= target_tokens:
        return CompressedContext(original_tokens, original_tokens, text, 1.0)

    # Score each sentence by relevance to query
    scores = []
    for sent in sentences:
        # Simple keyword overlap (production: use embeddings)
        query_words = set(query.lower().split())
        sent_words = set(sent.lower().split())
        overlap = len(query_words & sent_words) / max(len(query_words), 1)
        # Bonus for sentences with code, numbers, or definitions
        has_code = '`' in sent or 'def ' in sent or 'class ' in sent
        has_numbers = bool(re.search(r'\\d+', sent))
        score = overlap + (0.3 if has_code else 0) + (0.1 if has_numbers else 0)
        scores.append((score, sent))

    # Select top sentences by relevance, maintaining original order
    scores.sort(key=lambda x: -x[0])
    token_budget = target_tokens
    selected = []
    for score, sent in scores:
        sent_tokens = len(sent.split())
        if token_budget - sent_tokens >= 0:
            selected.append((sentences.index(sent), sent))
            token_budget -= sent_tokens

    # Restore original order
    selected.sort(key=lambda x: x[0])
    compressed = " ".join(sent for _, sent in selected)
    compressed_tokens = len(compressed.split())

    return CompressedContext(
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        content=compressed,
        compression_ratio=compressed_tokens / original_tokens,
    )
```

### Recursive Summarization for Very Long Documents

```python
def recursive_summarize(
    text: str,
    llm_fn,
    chunk_size: int = 3000,
    target_size: int = 1000,
    max_depth: int = 3,
) -> str:
    \"\"\"
    Recursively summarize a document that exceeds context limits.

    Algorithm:
    1. Split document into chunks that fit the context window
    2. Summarize each chunk independently
    3. If concatenated summaries still exceed target, recurse

    Why recursive instead of map-reduce? Map-reduce (summarize chunks,
    then summarize summaries) loses cross-chunk context. Recursive
    summarization preserves running context by including the previous
    summary as context for the next chunk.
    \"\"\"
    words = text.split()
    if len(words) <= target_size:
        return text

    # Split into chunks
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)

    # Summarize each chunk with rolling context
    summaries = []
    running_context = ""
    for i, chunk in enumerate(chunks):
        prompt = (
            f"Summarize this section concisely, preserving key facts, "
            f"numbers, and code examples.\\n\\n"
        )
        if running_context:
            prompt += f"Previous context: {running_context[:500]}\\n\\n"
        prompt += f"Section {i+1}/{len(chunks)}:\\n{chunk}"

        summary = llm_fn(prompt)
        summaries.append(summary)
        running_context = summary  # Rolling context for coherence

    combined = "\\n\\n".join(summaries)

    # Recurse if still too long
    if len(combined.split()) > target_size and max_depth > 0:
        return recursive_summarize(combined, llm_fn, chunk_size, target_size, max_depth - 1)

    return combined
```

### Hybrid RAG + Long Context

```python
class HybridRetriever:
    \"\"\"
    Best of both worlds: RAG for retrieval, long context for reasoning.

    Strategy:
    1. Use embedding search to find the TOP relevant chunks (RAG)
    2. Use the surrounding context of each chunk (long context)
    3. Feed retrieved chunks + surrounding context to the LLM

    This avoids the needle-in-haystack problem (RAG finds the needle)
    while preserving surrounding context (long context gives coherence).
    \"\"\"

    def __init__(self, embed_fn, llm_fn, chunk_size: int = 500, context_window: int = 2000):
        self.embed_fn = embed_fn
        self.llm_fn = llm_fn
        self.chunk_size = chunk_size
        self.context_window = context_window
        self.chunks = []
        self.embeddings = []

    def index_document(self, text: str):
        \"\"\"Split and embed document chunks.\"\"\"
        words = text.split()
        self.chunks = []
        for i in range(0, len(words), self.chunk_size):
            chunk = " ".join(words[i:i + self.chunk_size])
            self.chunks.append({"text": chunk, "start_word": i})

        # Embed all chunks
        self.embeddings = [self.embed_fn(c["text"]) for c in self.chunks]

    def query(self, question: str, top_k: int = 5) -> str:
        \"\"\"Retrieve relevant chunks with surrounding context.\"\"\"
        import numpy as np

        query_embedding = self.embed_fn(question)

        # Cosine similarity
        similarities = []
        for emb in self.embeddings:
            q = np.array(query_embedding)
            d = np.array(emb)
            sim = np.dot(q, d) / (np.linalg.norm(q) * np.linalg.norm(d) + 1e-10)
            similarities.append(sim)

        # Get top-k chunk indices
        top_indices = sorted(range(len(similarities)), key=lambda i: -similarities[i])[:top_k]

        # Expand each chunk with surrounding context
        expanded_chunks = []
        for idx in sorted(top_indices):  # Sort by position for coherence
            # Include one chunk before and after for context
            start = max(0, idx - 1)
            end = min(len(self.chunks), idx + 2)
            expanded = " ".join(self.chunks[i]["text"] for i in range(start, end))
            expanded_chunks.append(expanded)

        # Deduplicate overlapping expansions
        context = "\\n\\n---\\n\\n".join(expanded_chunks)

        # Compress if exceeding context window
        context_tokens = len(context.split())
        if context_tokens > self.context_window:
            context = compress_context_extractive(
                context, question, self.llm_fn, self.context_window
            ).content

        # Generate answer
        prompt = (
            f"Answer this question using ONLY the provided context.\\n\\n"
            f"Context:\\n{context}\\n\\n"
            f"Question: {question}\\n\\n"
            f"If the context doesn't contain enough information, say so."
        )
        return self.llm_fn(prompt)
```

### Key Takeaway

The future isn't "long context OR RAG" — it's both. Long context handles coherence and complex reasoning; RAG handles scale, cost, and freshness. The hybrid approach gives you the best of both worlds at a fraction of the cost of stuffing everything into a 1M-token context.""",
    ),
]
