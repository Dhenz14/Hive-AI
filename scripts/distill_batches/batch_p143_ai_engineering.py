"""AI engineering — model merging, embedding fine-tuning, long context, and MoE architecture."""

PAIRS = [
    (
        "ai/model-merging-dare-ties",
        "Show model merging techniques: SLERP, TIES, DARE, and task arithmetic for combining fine-tuned models.",
        '''Model merging techniques:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional
import copy


# --- Why Model Merging? ---
#
# Instead of training one model on ALL tasks:
#   1. Fine-tune separate specialists (code, math, chat, etc.)
#   2. Merge them into a single model
#   3. Get multi-task capability without multi-task data
#
# Used by: OpenChat, NeuralChat, MergeKit, virtually all open LLM leaderboard toppers


# --- Task Arithmetic (basic merging) ---

def task_arithmetic_merge(
    base_model: dict[str, torch.Tensor],
    finetuned_models: list[dict[str, torch.Tensor]],
    scaling_coefficients: list[float],
) -> dict[str, torch.Tensor]:
    """
    Task Arithmetic: θ_merged = θ_base + Σ λ_i * (θ_ft_i - θ_base)

    Each fine-tuned model contributes a "task vector" (delta from base).
    Scale and add task vectors to the base.
    """
    merged = {}
    for key in base_model:
        task_vectors = [
            coeff * (ft[key] - base_model[key])
            for ft, coeff in zip(finetuned_models, scaling_coefficients)
        ]
        merged[key] = base_model[key] + sum(task_vectors)
    return merged


# --- TIES Merging (Trim, Elect Sign, Disjoint Merge) ---

def ties_merge(
    base_state: dict[str, torch.Tensor],
    ft_states: list[dict[str, torch.Tensor]],
    density: float = 0.5,
    weights: Optional[list[float]] = None,
) -> dict[str, torch.Tensor]:
    """
    TIES: resolves sign conflicts between task vectors.

    1. TRIM: zero out small-magnitude deltas (keep top density%)
    2. ELECT SIGN: for each parameter, majority-vote the sign
    3. MERGE: average only values matching the elected sign
    """
    if weights is None:
        weights = [1.0 / len(ft_states)] * len(ft_states)

    merged = {}

    for key in base_state:
        # Compute task vectors
        deltas = [ft[key] - base_state[key] for ft in ft_states]

        # Step 1: TRIM — keep only top density% by magnitude
        trimmed = []
        for delta in deltas:
            threshold = torch.quantile(
                delta.abs().float(), 1.0 - density,
            )
            mask = delta.abs() >= threshold
            trimmed.append(delta * mask)

        # Step 2: ELECT SIGN — majority vote
        signs = torch.stack([torch.sign(d) for d in trimmed])
        elected_sign = torch.sign(signs.sum(dim=0))

        # Step 3: DISJOINT MERGE — average values matching elected sign
        aligned = []
        for delta, weight in zip(trimmed, weights):
            mask = torch.sign(delta) == elected_sign
            aligned.append(delta * mask * weight)

        task_vector = torch.stack(aligned).sum(dim=0)
        merged[key] = base_state[key] + task_vector

    return merged


# --- DARE (Drop And REscale) ---

def dare_merge(
    base_state: dict[str, torch.Tensor],
    ft_states: list[dict[str, torch.Tensor]],
    drop_rate: float = 0.9,
    weights: Optional[list[float]] = None,
) -> dict[str, torch.Tensor]:
    """
    DARE: randomly drop most delta values, rescale survivors.

    Insight: fine-tuned models have highly redundant deltas.
    Dropping 90% of delta values barely affects performance
    but massively reduces interference between merged models.

    1. Compute delta = θ_ft - θ_base
    2. Randomly drop (1-p) fraction of delta values
    3. Rescale survivors by 1/p to maintain expected magnitude
    4. Sum rescaled deltas
    """
    if weights is None:
        weights = [1.0 / len(ft_states)] * len(ft_states)

    merged = {}
    p = 1.0 - drop_rate  # Keep probability

    for key in base_state:
        task_vectors = []
        for ft, weight in zip(ft_states, weights):
            delta = ft[key] - base_state[key]

            # Random binary mask (keep with probability p)
            mask = torch.bernoulli(torch.full_like(delta.float(), p)).to(delta.dtype)

            # Rescale to maintain expected value
            rescaled = delta * mask / p * weight
            task_vectors.append(rescaled)

        merged[key] = base_state[key] + sum(task_vectors)

    return merged


# --- SLERP (Spherical Linear Interpolation) ---

def slerp_merge(
    state_a: dict[str, torch.Tensor],
    state_b: dict[str, torch.Tensor],
    t: float = 0.5,
) -> dict[str, torch.Tensor]:
    """
    SLERP: interpolate on the hypersphere (preserves magnitude).

    Better than linear interpolation (LERP) for high-dimensional
    weight spaces where magnitude matters.

    Only works for 2-model merges (pairwise).
    """
    merged = {}

    for key in state_a:
        a = state_a[key].float().flatten()
        b = state_b[key].float().flatten()

        # Normalize
        a_norm = a / (a.norm() + 1e-8)
        b_norm = b / (b.norm() + 1e-8)

        # Angle between vectors
        cos_theta = torch.clamp(torch.dot(a_norm, b_norm), -1.0, 1.0)
        theta = torch.acos(cos_theta)

        if theta.abs() < 1e-6:
            # Vectors nearly parallel — use linear interp
            result = (1 - t) * a + t * b
        else:
            # Spherical interpolation
            sin_theta = torch.sin(theta)
            result = (
                torch.sin((1 - t) * theta) / sin_theta * a +
                torch.sin(t * theta) / sin_theta * b
            )

        merged[key] = result.reshape(state_a[key].shape).to(state_a[key].dtype)

    return merged


# --- Practical usage with MergeKit ---

# mergekit-yaml config (the standard tool for model merging):
"""
# slerp_merge.yaml
slices:
  - sources:
      - model: base_model
        layer_range: [0, 32]
      - model: code_expert
        layer_range: [0, 32]

merge_method: slerp
base_model: base_model
parameters:
  t:
    - filter: self_attn
      value: 0.6  # More code expert for attention
    - filter: mlp
      value: 0.4  # More base for MLP
    - value: 0.5  # Default

dtype: bfloat16
"""

# mergekit-cli: mergekit-yaml slerp_merge.yaml ./merged_output
```

Model merging techniques:
1. **Task Arithmetic** — add weighted task vectors (δ = θ_ft - θ_base) to base model
2. **TIES** — trim small deltas, elect sign by majority vote, merge aligned values only
3. **DARE** — drop 90% of delta values randomly, rescale survivors (reduces interference)
4. **SLERP** — spherical interpolation preserves weight magnitude (best for 2-model merge)
5. **MergeKit** — YAML-based tool supporting per-layer and per-module merge ratios'''
    ),
    (
        "ai/embedding-finetuning",
        "Show embedding model fine-tuning patterns: contrastive learning, hard negative mining, Matryoshka embeddings, and evaluation.",
        '''Embedding model fine-tuning:

```python
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sentence_transformers import (
    SentenceTransformer, InputExample, losses,
    evaluation, SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
)
from datasets import Dataset as HFDataset
import random


# --- Why fine-tune embeddings? ---
#
# General-purpose embeddings (bge-m3, text-embedding-3) work well
# but domain-specific fine-tuning can improve retrieval by 10-30%:
#   - Medical documents: fine-tune on PubMed abstracts
#   - Legal search: fine-tune on case law pairs
#   - Code search: fine-tune on code-docstring pairs
#   - Product search: fine-tune on query-product pairs


# --- Training data format ---

# Pairs: (query, positive_passage)
# Triplets: (query, positive, negative)
# With scores: (sentence_a, sentence_b, similarity_score)

train_examples = [
    InputExample(texts=["How to sort a list?", "Use sorted() or .sort() for in-place"]),
    InputExample(texts=["Python async await", "asyncio enables concurrent I/O operations"]),
    InputExample(texts=["Database indexing", "B-tree indexes speed up lookups on columns"]),
]


# --- Contrastive learning (MultipleNegativesRankingLoss) ---

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

# MNRL: for each (query, positive) pair, all other positives
# in the batch become negatives automatically
train_loss = losses.MultipleNegativesRankingLoss(model)

# With hard negatives (much more effective)
# Each example: [query, positive, hard_negative]
hard_neg_examples = [
    InputExample(texts=[
        "Python list comprehension",
        "List comprehensions provide concise syntax: [x**2 for x in range(10)]",
        "Python lists are mutable sequences that can hold any type",  # Hard negative
    ]),
]
train_loss_hard = losses.MultipleNegativesRankingLoss(model)


# --- Hard negative mining ---

def mine_hard_negatives(
    model: SentenceTransformer,
    queries: list[str],
    corpus: list[str],
    positives: list[int],  # Index of positive for each query
    n_negatives: int = 5,
) -> list[list[str]]:
    """Mine hard negatives: similar but wrong passages."""
    query_embeddings = model.encode(queries, convert_to_tensor=True)
    corpus_embeddings = model.encode(corpus, convert_to_tensor=True)

    # Cosine similarity
    sims = F.cosine_similarity(
        query_embeddings.unsqueeze(1),
        corpus_embeddings.unsqueeze(0),
        dim=2,
    )

    triplets = []
    for i, (query, pos_idx) in enumerate(zip(queries, positives)):
        # Get top-K similar passages (excluding the positive)
        scores = sims[i].clone()
        scores[pos_idx] = -1  # Exclude positive

        # Hard negatives: high similarity but wrong
        top_neg_indices = scores.topk(n_negatives).indices
        hard_negs = [corpus[idx] for idx in top_neg_indices]

        triplets.append([query, corpus[pos_idx]] + hard_negs)

    return triplets


# --- Matryoshka Representation Learning (MRL) ---

# Matryoshka embeddings: single model produces useful embeddings
# at multiple dimensions (e.g., 64, 128, 256, 512, 768)
# Smaller dimensions for fast approximate search,
# full dimensions for precise reranking

from sentence_transformers.losses import MatryoshkaLoss

matryoshka_loss = MatryoshkaLoss(
    model=model,
    loss=losses.MultipleNegativesRankingLoss(model),
    matryoshka_dims=[64, 128, 256, 512, 768],
    matryoshka_weights=[1, 1, 1, 1, 1],
)

# At inference time, truncate embeddings to any trained dimension:
# full_emb = model.encode("query")  # shape: (768,)
# fast_emb = full_emb[:128]         # Still useful! (128-dim)
# precise_emb = full_emb[:512]      # More precise (512-dim)


# --- Training with SentenceTransformerTrainer ---

train_dataset = HFDataset.from_dict({
    "anchor": ["How to sort?", "async await Python"],
    "positive": ["Use sorted() function", "asyncio for concurrency"],
    "negative": ["Sorting algorithms theory", "Threading vs multiprocessing"],
})

args = SentenceTransformerTrainingArguments(
    output_dir="./embedding-finetuned",
    num_train_epochs=3,
    per_device_train_batch_size=64,  # Larger batch = more negatives
    learning_rate=2e-5,
    warmup_ratio=0.1,
    fp16=True,
    eval_strategy="steps",
    eval_steps=100,
    save_steps=100,
    logging_steps=10,
)

trainer = SentenceTransformerTrainer(
    model=model,
    args=args,
    train_dataset=train_dataset,
    loss=matryoshka_loss,
)
trainer.train()


# --- Evaluation ---

from sentence_transformers.evaluation import (
    InformationRetrievalEvaluator,
    EmbeddingSimilarityEvaluator,
)

# Information retrieval evaluation (NDCG, MAP, MRR)
ir_evaluator = InformationRetrievalEvaluator(
    queries={"q1": "How to sort?", "q2": "async patterns"},
    corpus={"d1": "sorted() function", "d2": "asyncio module", "d3": "unrelated"},
    relevant_docs={"q1": {"d1"}, "q2": {"d2"}},
    name="custom-ir-eval",
)
results = ir_evaluator(model)
print(f"NDCG@10: {results['custom-ir-eval_ndcg@10']:.4f}")
print(f"MAP@10: {results['custom-ir-eval_map@10']:.4f}")
```

Embedding fine-tuning patterns:
1. **MultipleNegativesRankingLoss** — in-batch negatives: every other positive becomes a negative
2. **Hard negative mining** — find similar-but-wrong passages for harder training signal
3. **Matryoshka embeddings** — train once, use at any dimension (64 to 768)
4. **Large batch size** — more negatives per batch = better contrastive signal
5. **IR evaluation** — NDCG@10, MAP@10, MRR measure retrieval quality after fine-tuning'''
    ),
    (
        "ai/mixture-of-experts-architecture",
        "Show Mixture of Experts (MoE) architecture: sparse gating, expert routing, load balancing, and training considerations.",
        '''Mixture of Experts (MoE) architecture:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional


# --- MoE Core Concept ---
#
# Standard transformer: EVERY parameter activates for EVERY token
# MoE transformer: only a SUBSET of parameters (experts) activate
#
# Result: 8x more parameters but same compute cost per token
# Example: Mixtral 8x7B = 46.7B total params, but only 12.9B active per token


class Expert(nn.Module):
    """Single expert (standard MLP)."""

    def __init__(self, hidden_size: int, intermediate_size: int):
        super().__init__()
        self.gate_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # SwiGLU activation (used in Llama, Mixtral, Qwen)
        return self.down_proj(
            F.silu(self.gate_proj(x)) * self.up_proj(x)
        )


class TopKRouter(nn.Module):
    """Sparse gating: route each token to top-K experts."""

    def __init__(
        self,
        hidden_size: int,
        num_experts: int,
        top_k: int = 2,
        noise_std: float = 0.1,
    ):
        super().__init__()
        self.top_k = top_k
        self.noise_std = noise_std
        self.gate = nn.Linear(hidden_size, num_experts, bias=False)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns:
            router_weights: (batch, seq_len, top_k) — softmax weights for selected experts
            selected_experts: (batch, seq_len, top_k) — indices of selected experts
            router_logits: (batch, seq_len, num_experts) — raw logits for load balancing
        """
        logits = self.gate(x)  # (batch, seq_len, num_experts)

        # Add noise during training for exploration
        if self.training and self.noise_std > 0:
            noise = torch.randn_like(logits) * self.noise_std
            logits = logits + noise

        # Select top-K experts per token
        top_k_logits, selected_experts = logits.topk(self.top_k, dim=-1)

        # Softmax over selected experts only
        router_weights = F.softmax(top_k_logits, dim=-1)

        return router_weights, selected_experts, logits


class MoELayer(nn.Module):
    """Mixture of Experts layer replacing the standard MLP."""

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_experts: int = 8,
        top_k: int = 2,
    ):
        super().__init__()
        self.router = TopKRouter(hidden_size, num_experts, top_k)
        self.experts = nn.ModuleList([
            Expert(hidden_size, intermediate_size)
            for _ in range(num_experts)
        ])
        self.num_experts = num_experts
        self.top_k = top_k

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        batch_size, seq_len, hidden_size = x.shape

        # Route tokens to experts
        weights, indices, logits = self.router(x)

        # Compute expert outputs
        output = torch.zeros_like(x)

        for expert_idx in range(self.num_experts):
            # Find tokens routed to this expert
            mask = (indices == expert_idx).any(dim=-1)  # (batch, seq_len)

            if not mask.any():
                continue

            # Get tokens for this expert
            expert_input = x[mask]  # (num_tokens, hidden_size)
            expert_output = self.experts[expert_idx](expert_input)

            # Weighted contribution
            for k in range(self.top_k):
                k_mask = indices[..., k] == expert_idx
                if k_mask.any():
                    w = weights[..., k][k_mask].unsqueeze(-1)
                    output[k_mask] += w * expert_output[:k_mask.sum()]

        return output, logits


# --- Load Balancing Loss ---

def load_balancing_loss(
    router_logits: torch.Tensor,
    num_experts: int,
    top_k: int,
) -> torch.Tensor:
    """
    Auxiliary loss to prevent expert collapse.

    Without this, the router learns to send ALL tokens to 1-2 experts
    while the rest are unused (expert collapse).

    L_balance = num_experts * Σ(f_i * P_i)
    where f_i = fraction of tokens routed to expert i
          P_i = mean routing probability for expert i
    """
    # f_i: fraction of tokens dispatched to each expert
    routing_probs = F.softmax(router_logits, dim=-1)
    _, selected = routing_probs.topk(top_k, dim=-1)

    # Count tokens per expert
    expert_mask = F.one_hot(selected, num_experts).sum(dim=-2).float()
    tokens_per_expert = expert_mask.sum(dim=(0, 1))
    total_tokens = expert_mask.sum()
    f = tokens_per_expert / total_tokens

    # P_i: mean routing probability
    P = routing_probs.mean(dim=(0, 1))

    # Balance loss
    return num_experts * (f * P).sum()


# --- MoE Transformer Block ---

class MoETransformerBlock(nn.Module):
    """Transformer block with MoE replacing standard MLP."""

    def __init__(self, hidden_size, num_heads, num_experts, intermediate_size):
        super().__init__()
        self.attention = nn.MultiheadAttention(hidden_size, num_heads, batch_first=True)
        self.attn_norm = nn.RMSNorm(hidden_size)
        self.moe = MoELayer(hidden_size, intermediate_size, num_experts)
        self.moe_norm = nn.RMSNorm(hidden_size)

    def forward(self, x, mask=None):
        # Self-attention
        residual = x
        x = self.attn_norm(x)
        x, _ = self.attention(x, x, x, attn_mask=mask)
        x = residual + x

        # MoE (replaces standard MLP)
        residual = x
        x = self.moe_norm(x)
        moe_output, router_logits = self.moe(x)
        x = residual + moe_output

        return x, router_logits
```

MoE architecture patterns:
1. **Sparse gating** — top-K router selects 2 of 8 experts per token (75% compute savings)
2. **SwiGLU experts** — each expert is a standard MLP with gated activation
3. **Load balancing loss** — auxiliary loss `L = N * Σ(f_i * P_i)` prevents expert collapse
4. **Training noise** — add Gaussian noise to router logits for expert exploration
5. **Total vs active params** — Mixtral 8x7B has 47B params but only 13B active per token'''
    ),
]
