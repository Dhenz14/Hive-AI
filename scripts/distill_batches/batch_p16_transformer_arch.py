PAIRS = [
    (
        "ml/transformer-architecture-deep-dive",
        r"""Explain the Transformer architecture in depth including self-attention mechanism, multi-head attention, positional encoding, layer normalization, the feed-forward network, and how encoder-decoder vs decoder-only architectures differ. Include mathematical intuition and PyTorch implementation.""",
        r"""## Transformer Architecture: Attention Mechanisms, Position Encoding, and Modern Variants

The Transformer is the foundation of modern NLP and increasingly vision and multimodal AI. Understanding its components deeply — not just "attention is all you need" — is essential for working with and fine-tuning language models.

### Self-Attention: The Core Mechanism

Self-attention lets each token "look at" every other token to build context-aware representations:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class SelfAttention(nn.Module):
    """Single-head self-attention from scratch."""

    def __init__(self, embed_dim: int):
        super().__init__()
        self.embed_dim = embed_dim

        # Three projections: Query, Key, Value
        self.W_q = nn.Linear(embed_dim, embed_dim, bias=False)
        self.W_k = nn.Linear(embed_dim, embed_dim, bias=False)
        self.W_v = nn.Linear(embed_dim, embed_dim, bias=False)

    def forward(self, x: torch.Tensor, mask: torch.Tensor = None):
        """
        x: (batch, seq_len, embed_dim)
        mask: (batch, seq_len, seq_len) or (1, seq_len, seq_len)

        Returns: (batch, seq_len, embed_dim)
        """
        # Project input into Q, K, V spaces
        Q = self.W_q(x)  # What am I looking for?
        K = self.W_k(x)  # What do I contain?
        V = self.W_v(x)  # What information do I provide?

        # Compute attention scores: how much should token_i attend to token_j?
        # score(i,j) = Q_i · K_j / sqrt(d_k)
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.embed_dim)
        # Shape: (batch, seq_len, seq_len)

        # Apply mask (e.g., causal mask for autoregressive models)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, float("-inf"))

        # Softmax to get attention weights (sum to 1 for each query)
        attn_weights = F.softmax(scores, dim=-1)

        # Weighted sum of values
        output = torch.matmul(attn_weights, V)
        # Shape: (batch, seq_len, embed_dim)

        return output, attn_weights


# WHY self-attention works:
# 1. Q·K similarity finds relevant tokens regardless of distance
# 2. No recurrence = no vanishing gradient for long sequences
# 3. O(n²) attention lets every token see every other token
# 4. The sqrt(d_k) scaling prevents softmax saturation
```

### Multi-Head Attention

Multiple attention heads learn different types of relationships:

```python
class MultiHeadAttention(nn.Module):
    """Multi-head attention: multiple parallel attention patterns."""

    def __init__(self, embed_dim: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        assert embed_dim % num_heads == 0

        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        # Single matrix for all heads (more efficient than separate)
        self.W_qkv = nn.Linear(embed_dim, 3 * embed_dim, bias=False)
        self.W_out = nn.Linear(embed_dim, embed_dim, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        batch_size, seq_len, _ = x.shape

        # Project to Q, K, V for all heads at once
        qkv = self.W_qkv(x)  # (batch, seq, 3 * embed_dim)
        qkv = qkv.reshape(batch_size, seq_len, 3, self.num_heads, self.head_dim)
        qkv = qkv.permute(2, 0, 3, 1, 4)  # (3, batch, heads, seq, head_dim)
        Q, K, V = qkv[0], qkv[1], qkv[2]

        # Scaled dot-product attention per head
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)

        if mask is not None:
            scores = scores.masked_fill(mask.unsqueeze(1) == 0, float("-inf"))

        attn = F.softmax(scores, dim=-1)
        attn = self.dropout(attn)

        # Combine heads
        out = torch.matmul(attn, V)  # (batch, heads, seq, head_dim)
        out = out.transpose(1, 2).reshape(batch_size, seq_len, self.embed_dim)

        return self.W_out(out)

# Each head learns different attention patterns:
# Head 1 might learn syntactic relationships (subject-verb)
# Head 2 might learn coreference (pronoun → noun it refers to)
# Head 3 might learn positional patterns (attend to adjacent tokens)
# The output projection combines all these perspectives
```

### Positional Encoding

Transformers have no inherent notion of position. Positional encodings inject sequence order:

```python
class SinusoidalPositionalEncoding(nn.Module):
    """Original Transformer positional encoding."""

    def __init__(self, embed_dim: int, max_len: int = 8192):
        super().__init__()

        pe = torch.zeros(max_len, embed_dim)
        position = torch.arange(0, max_len).unsqueeze(1).float()
        div_term = torch.exp(
            torch.arange(0, embed_dim, 2).float()
            * -(math.log(10000.0) / embed_dim)
        )

        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)

        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, embed_dim)

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class RotaryPositionalEmbedding(nn.Module):
    """RoPE: Rotary Position Embedding (used in LLaMA, Qwen, etc.)."""

    def __init__(self, dim: int, max_len: int = 8192, base: float = 10000.0):
        super().__init__()
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)

        t = torch.arange(max_len).float()
        freqs = torch.outer(t, inv_freq)
        self.register_buffer("cos_cached", freqs.cos())
        self.register_buffer("sin_cached", freqs.sin())

    def forward(self, q, k, positions=None):
        """Apply rotary embeddings to query and key."""
        seq_len = q.shape[-2]
        cos = self.cos_cached[:seq_len].unsqueeze(0).unsqueeze(0)
        sin = self.sin_cached[:seq_len].unsqueeze(0).unsqueeze(0)

        q_rotated = self._rotate(q, cos, sin)
        k_rotated = self._rotate(k, cos, sin)
        return q_rotated, k_rotated

    def _rotate(self, x, cos, sin):
        x1, x2 = x[..., ::2], x[..., 1::2]
        rotated = torch.stack(
            [x1 * cos - x2 * sin, x1 * sin + x2 * cos], dim=-1
        )
        return rotated.flatten(-2)

# RoPE advantages over sinusoidal:
# 1. Relative position information (q·k depends on position DIFFERENCE)
# 2. Natural length extrapolation with NTK-aware scaling
# 3. No separate position embedding — applied to Q,K directly
```

### Full Transformer Block

```python
class TransformerBlock(nn.Module):
    """Single Transformer block with pre-norm (modern style)."""

    def __init__(
        self,
        embed_dim: int,
        num_heads: int,
        ff_dim: int,
        dropout: float = 0.1,
    ):
        super().__init__()

        # Pre-norm: normalize BEFORE attention and FFN
        # (Original Transformer used post-norm: less stable training)
        self.norm1 = nn.RMSNorm(embed_dim)  # RMSNorm (LLaMA-style)
        self.attn = MultiHeadAttention(embed_dim, num_heads, dropout)

        self.norm2 = nn.RMSNorm(embed_dim)
        self.ffn = SwiGLU(embed_dim, ff_dim)  # Modern FFN

        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        # Residual connection + pre-norm attention
        h = self.norm1(x)
        h = self.attn(h, mask=mask)
        x = x + self.dropout(h)

        # Residual connection + pre-norm FFN
        h = self.norm2(x)
        h = self.ffn(h)
        x = x + self.dropout(h)

        return x


class SwiGLU(nn.Module):
    """SwiGLU activation (used in LLaMA, PaLM, etc.)."""

    def __init__(self, embed_dim: int, ff_dim: int):
        super().__init__()
        # SwiGLU uses 2/3 of ff_dim for each gate
        self.w1 = nn.Linear(embed_dim, ff_dim, bias=False)
        self.w2 = nn.Linear(ff_dim, embed_dim, bias=False)
        self.w3 = nn.Linear(embed_dim, ff_dim, bias=False)  # Gate

    def forward(self, x):
        # SwiGLU(x) = (Swish(W1·x) ⊙ W3·x) · W2
        return self.w2(F.silu(self.w1(x)) * self.w3(x))

# SwiGLU vs ReLU FFN:
# Old: FFN(x) = max(0, xW1 + b1)W2 + b2
# New: FFN(x) = (SiLU(xW1) ⊙ xW3)W2
# SwiGLU trains faster and produces better models at same param count
```

### Decoder-Only Architecture (GPT/LLaMA-style)

```python
class DecoderOnlyTransformer(nn.Module):
    """Decoder-only Transformer (GPT/LLaMA architecture)."""

    def __init__(
        self,
        vocab_size: int = 32000,
        embed_dim: int = 4096,
        num_heads: int = 32,
        num_layers: int = 32,
        ff_dim: int = 11008,
        max_seq_len: int = 4096,
        dropout: float = 0.0,
    ):
        super().__init__()

        self.token_embed = nn.Embedding(vocab_size, embed_dim)
        self.rope = RotaryPositionalEmbedding(embed_dim // num_heads, max_seq_len)

        self.layers = nn.ModuleList([
            TransformerBlock(embed_dim, num_heads, ff_dim, dropout)
            for _ in range(num_layers)
        ])

        self.norm = nn.RMSNorm(embed_dim)
        self.lm_head = nn.Linear(embed_dim, vocab_size, bias=False)

        # Tie input and output embeddings (saves parameters)
        self.lm_head.weight = self.token_embed.weight

    def forward(self, input_ids: torch.Tensor):
        batch, seq_len = input_ids.shape

        # Causal mask: each token can only attend to previous tokens
        causal_mask = torch.triu(
            torch.ones(seq_len, seq_len, device=input_ids.device),
            diagonal=1,
        ).bool()
        causal_mask = ~causal_mask  # True = can attend

        x = self.token_embed(input_ids)

        for layer in self.layers:
            x = layer(x, mask=causal_mask)

        x = self.norm(x)
        logits = self.lm_head(x)  # (batch, seq_len, vocab_size)

        return logits

    @torch.no_grad()
    def generate(self, input_ids, max_new_tokens=100, temperature=0.7, top_p=0.9):
        """Autoregressive generation with nucleus sampling."""
        for _ in range(max_new_tokens):
            logits = self(input_ids)[:, -1, :]  # Last token's logits
            logits = logits / temperature

            # Top-p (nucleus) sampling
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cum_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
            mask = cum_probs - F.softmax(sorted_logits, dim=-1) >= top_p
            sorted_logits[mask] = float("-inf")
            probs = F.softmax(sorted_logits, dim=-1)

            next_token = sorted_indices.gather(-1, torch.multinomial(probs, 1))
            input_ids = torch.cat([input_ids, next_token], dim=-1)

        return input_ids
```

### Encoder-Decoder vs Decoder-Only

```
Encoder-Decoder (T5, BART):
  Input → [Encoder: bidirectional attention] → hidden states
  hidden states + output tokens → [Decoder: causal + cross-attention] → output
  Best for: translation, summarization, seq2seq tasks
  Cross-attention allows decoder to "look at" encoder representations

Decoder-Only (GPT, LLaMA, Claude):
  Input + output → [Decoder: causal attention only] → output
  Best for: general text generation, instruction following, chat
  Simpler architecture, scales better, dominates modern LLMs
  "Encoder" happens implicitly through causal attention on input prefix

Encoder-Only (BERT):
  Input → [Encoder: bidirectional attention] → representations
  Best for: classification, NER, embedding
  Can see full context in both directions
  Not used for generation
```

**Transformer intuition**: (1) Self-attention is a differentiable dictionary lookup — Q asks "what do I need?", K says "this is what I have", V provides the information, (2) Multiple heads = multiple types of relationships learned in parallel, (3) Residual connections + layer norm make deep networks trainable, (4) RoPE encodes relative position into the attention computation directly, (5) Modern LLMs are just very deep stacks of (attention + SwiGLU FFN) blocks with careful scaling."""
    ),
    (
        "ml/attention-optimizations",
        r"""Explain attention optimization techniques including KV-cache for inference, Flash Attention for training, grouped-query attention (GQA), sliding window attention, multi-query attention, and speculative decoding. Show how these reduce memory and computation.""",
        r"""## Attention Optimizations: KV-Cache, Flash Attention, GQA, and Speculative Decoding

Standard self-attention is O(n²) in memory and compute. For long sequences and large models, optimizations are essential for practical training and inference.

### KV-Cache for Inference

During autoregressive generation, recomputing attention for all previous tokens at each step is wasteful:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class CachedMultiHeadAttention(nn.Module):
    """Multi-head attention with KV-cache for fast inference."""

    def __init__(self, embed_dim: int, num_heads: int):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.W_q = nn.Linear(embed_dim, embed_dim, bias=False)
        self.W_k = nn.Linear(embed_dim, embed_dim, bias=False)
        self.W_v = nn.Linear(embed_dim, embed_dim, bias=False)
        self.W_out = nn.Linear(embed_dim, embed_dim, bias=False)

    def forward(self, x, kv_cache=None, use_cache=False):
        """
        Without cache: process full sequence (prefill phase)
        With cache: process only new token(s) (decode phase)
        """
        batch, seq_len, _ = x.shape

        Q = self.W_q(x).view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        K = self.W_k(x).view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        V = self.W_v(x).view(batch, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        if kv_cache is not None:
            # Append new K, V to cached K, V
            cached_k, cached_v = kv_cache
            K = torch.cat([cached_k, K], dim=2)
            V = torch.cat([cached_v, V], dim=2)

        new_cache = (K, V) if use_cache else None

        # Attention: Q is only for new tokens, K/V includes all history
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn = F.softmax(scores, dim=-1)
        out = torch.matmul(attn, V)

        out = out.transpose(1, 2).reshape(batch, seq_len, -1)
        return self.W_out(out), new_cache


# Memory impact of KV-cache:
# Without cache: Each generation step recomputes ALL tokens
#   Step 1: compute attention for 1000 tokens
#   Step 2: compute attention for 1001 tokens
#   Step 3: compute attention for 1002 tokens  → O(n²) total
#
# With cache: Each step only computes for NEW token
#   Step 1: compute for 1 new token, cache K,V for 1000 prefix tokens
#   Step 2: compute for 1 new token using cached K,V (1001 entries)
#   Step 3: compute for 1 new token using cached K,V (1002 entries)
#   → O(n) total compute, but O(n) memory for the cache
#
# KV-cache size per layer:
#   2 * batch_size * num_heads * seq_len * head_dim * sizeof(dtype)
#   For LLaMA-70B, 4096 context: ~1.6GB per layer, ~128GB total
```

### Grouped-Query Attention (GQA)

Reduce KV-cache size by sharing K,V heads:

```python
class GroupedQueryAttention(nn.Module):
    """GQA: fewer KV heads than query heads (LLaMA 2 70B, Mistral)."""

    def __init__(
        self,
        embed_dim: int,
        num_q_heads: int = 32,
        num_kv_heads: int = 8,  # Shared across groups
    ):
        super().__init__()
        self.num_q_heads = num_q_heads
        self.num_kv_heads = num_kv_heads
        self.head_dim = embed_dim // num_q_heads
        self.group_size = num_q_heads // num_kv_heads

        self.W_q = nn.Linear(embed_dim, num_q_heads * self.head_dim, bias=False)
        self.W_k = nn.Linear(embed_dim, num_kv_heads * self.head_dim, bias=False)
        self.W_v = nn.Linear(embed_dim, num_kv_heads * self.head_dim, bias=False)
        self.W_out = nn.Linear(embed_dim, embed_dim, bias=False)

    def forward(self, x, kv_cache=None, use_cache=False):
        batch, seq_len, _ = x.shape

        Q = self.W_q(x).view(batch, seq_len, self.num_q_heads, self.head_dim)
        K = self.W_k(x).view(batch, seq_len, self.num_kv_heads, self.head_dim)
        V = self.W_v(x).view(batch, seq_len, self.num_kv_heads, self.head_dim)

        # Expand KV heads to match Q heads by repeating
        K = K.unsqueeze(3).expand(-1, -1, -1, self.group_size, -1)
        K = K.reshape(batch, seq_len, self.num_q_heads, self.head_dim)
        V = V.unsqueeze(3).expand(-1, -1, -1, self.group_size, -1)
        V = V.reshape(batch, seq_len, self.num_q_heads, self.head_dim)

        Q = Q.transpose(1, 2)  # (batch, heads, seq, dim)
        K = K.transpose(1, 2)
        V = V.transpose(1, 2)

        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn = F.softmax(scores, dim=-1)
        out = torch.matmul(attn, V)

        out = out.transpose(1, 2).reshape(batch, seq_len, -1)
        return self.W_out(out)


# GQA variants:
# MHA:  32 Q heads, 32 KV heads (standard multi-head attention)
# GQA:  32 Q heads, 8 KV heads  (LLaMA 2 70B — 4x less KV cache)
# MQA:  32 Q heads, 1 KV head   (extreme sharing — Falcon, PaLM)
# Quality: MHA > GQA > MQA, but difference is small with enough training
```

### Flash Attention

IO-aware attention algorithm that avoids materializing the full N×N attention matrix:

```python
# Flash Attention is a CUDA kernel, not pure Python
# But here's the conceptual algorithm:

def flash_attention_conceptual(Q, K, V, block_size=256):
    """
    Standard attention materializes O(N²) attention matrix in HBM (GPU main memory).
    Flash Attention keeps everything in SRAM (on-chip cache) by processing in blocks.

    Key insight: softmax can be computed incrementally using the "online softmax" trick.
    """
    N = Q.shape[0]
    output = torch.zeros_like(Q)
    row_max = torch.full((N,), float("-inf"))
    row_sum = torch.zeros(N)

    for j_start in range(0, N, block_size):
        j_end = min(j_start + block_size, N)
        K_block = K[j_start:j_end]
        V_block = V[j_start:j_end]

        # Compute block of attention scores
        scores = Q @ K_block.T  # Only block_size columns, not all N

        # Online softmax: update running max and sum
        block_max = scores.max(dim=-1).values
        new_max = torch.maximum(row_max, block_max)

        # Rescale previous accumulator
        scale_old = torch.exp(row_max - new_max)
        scale_new = torch.exp(block_max - new_max)

        row_sum = scale_old * row_sum + scale_new * torch.exp(scores - block_max.unsqueeze(-1)).sum(dim=-1)
        output = scale_old.unsqueeze(-1) * output + scale_new.unsqueeze(-1) * (
            torch.exp(scores - block_max.unsqueeze(-1)) @ V_block
        )

        row_max = new_max

    return output / row_sum.unsqueeze(-1)


# In practice, use PyTorch's built-in:
# torch.nn.functional.scaled_dot_product_attention(Q, K, V, is_causal=True)
# This automatically uses Flash Attention 2 on supported GPUs

# Flash Attention benefits:
# Standard: O(N²) memory (attention matrix), many HBM read/writes
# Flash:    O(N) memory, 2-4x faster for seq_len > 1024
# Flash 2:  Additional optimizations, ~2x faster than Flash 1
```

### Sliding Window Attention

Limit attention to a local window instead of full context:

```python
class SlidingWindowAttention(nn.Module):
    """Mistral-style sliding window attention."""

    def __init__(self, embed_dim: int, num_heads: int, window_size: int = 4096):
        super().__init__()
        self.window_size = window_size
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.W_qkv = nn.Linear(embed_dim, 3 * embed_dim, bias=False)
        self.W_out = nn.Linear(embed_dim, embed_dim, bias=False)

    def forward(self, x):
        batch, seq_len, _ = x.shape

        qkv = self.W_qkv(x).reshape(batch, seq_len, 3, self.num_heads, self.head_dim)
        Q, K, V = qkv.permute(2, 0, 3, 1, 4)

        # Create sliding window causal mask
        mask = torch.ones(seq_len, seq_len, dtype=torch.bool, device=x.device)
        mask = torch.triu(mask, diagonal=1)  # Causal
        mask |= torch.triu(torch.ones_like(mask), diagonal=self.window_size)  # Window
        mask = ~mask

        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)
        scores = scores.masked_fill(~mask, float("-inf"))
        attn = F.softmax(scores, dim=-1)
        out = torch.matmul(attn, V)

        out = out.transpose(1, 2).reshape(batch, seq_len, -1)
        return self.W_out(out)


# Sliding window: each token attends to W previous tokens only
# Effective context grows through layers:
# Layer 1: each token sees W tokens
# Layer 2: each token sees 2W tokens (through layer 1 representations)
# Layer L: each token sees L*W tokens
# 32 layers * 4096 window = 131K effective context
# But KV-cache only stores W tokens per layer = massive memory savings
```

### Speculative Decoding

Use a small draft model to speed up generation with a large model:

```python
@torch.no_grad()
def speculative_decode(
    target_model,
    draft_model,
    input_ids: torch.Tensor,
    gamma: int = 5,  # Number of draft tokens to generate
    max_new_tokens: int = 100,
) -> torch.Tensor:
    """
    Speculative decoding: draft model proposes, target model verifies.
    Produces EXACTLY the same distribution as the target model alone.
    """
    generated = input_ids.clone()

    for _ in range(max_new_tokens // gamma):
        # Step 1: Draft model generates gamma tokens quickly
        draft_ids = generated.clone()
        draft_probs_list = []

        for _ in range(gamma):
            draft_logits = draft_model(draft_ids)[:, -1, :]
            draft_probs = F.softmax(draft_logits, dim=-1)
            draft_probs_list.append(draft_probs)

            next_token = torch.multinomial(draft_probs, 1)
            draft_ids = torch.cat([draft_ids, next_token], dim=-1)

        # Step 2: Target model evaluates ALL draft tokens in ONE forward pass
        # (This is the key — one forward pass for gamma+1 tokens)
        target_logits = target_model(draft_ids)
        target_probs = F.softmax(target_logits[:, -gamma-1:, :], dim=-1)

        # Step 3: Accept/reject each draft token
        accepted = 0
        for i in range(gamma):
            draft_token = draft_ids[:, generated.shape[1] + i]
            p_target = target_probs[:, i, draft_token]
            p_draft = draft_probs_list[i][:, draft_token]

            # Accept with probability min(1, p_target / p_draft)
            ratio = p_target / p_draft
            if torch.rand(1) < ratio:
                accepted += 1
            else:
                # Reject: sample from adjusted distribution
                adjusted = torch.clamp(target_probs[:, i] - draft_probs_list[i], min=0)
                adjusted = adjusted / adjusted.sum(dim=-1, keepdim=True)
                token = torch.multinomial(adjusted, 1)
                generated = torch.cat([
                    generated,
                    draft_ids[:, generated.shape[1]:generated.shape[1]+accepted],
                    token
                ], dim=-1)
                break
        else:
            # All accepted — also sample one more from target
            generated = torch.cat([generated, draft_ids[:, generated.shape[1]:]], dim=-1)

    return generated


# Speculative decoding speedup:
# If draft model accepts 80% of tokens:
# Without: 100 forward passes through 70B model
# With: ~25 forward passes through 70B + 100 through 7B draft
# Net speedup: ~2-3x (70B is the bottleneck)
```

**Attention optimization summary**: (1) KV-cache eliminates redundant computation during generation — essential for all production inference, (2) GQA reduces KV-cache size by 4-8x with minimal quality loss, (3) Flash Attention is a pure speed/memory win — always use it, (4) Sliding window + GQA enables very long contexts (128K+) with bounded memory, (5) Speculative decoding gives 2-3x speedup with zero quality degradation."""
    ),
]
