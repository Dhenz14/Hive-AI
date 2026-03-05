"""p16 transformer arch"""

PAIRS = [
    (
        "ml/transformer-architecture-deep-dive",
        "Explain the Transformer architecture in depth including self-attention mechanism, multi-head attention, positional encoding, layer normalization, the feed-forward network, and how encoder-decoder vs decoder-only architectures differ. Include mathematical intuition and PyTorch implementation.",
        '''The Transformer is the foundation of modern NLP and increasingly vision and multimodal AI. Understanding its components deeply -- not just "attention is all you need" -- is essential for working with and fine-tuning language models.

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
        # score(i,j) = Q_i * K_j / sqrt(d_k)
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
# 1. Q*K similarity finds relevant tokens regardless of distance
# 2. No recurrence = no vanishing gradient for long sequences
# 3. O(n**2) attention lets every token see every other token
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
# Head 2 might learn coreference (pronoun -> noun it refers to)
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
            * -(math.log(10000.0) / embed_dim)'''
    ),
    (
        "Encoder",
        "Encoder-Only (BERT): Input -> [Encoder: bidirectional attention] -> representations Best for: classification, NER, embedding Can see full context in both directions Not used for generation",
        '''**Transformer intuition**: (1) Self-attention is a differentiable dictionary lookup -- Q asks "what do I need?", K says "this is what I have", V provides the information, (2) Multiple heads = multiple types of relationships learned in parallel, (3) Residual connections + layer norm make deep networks trainable, (4) RoPE encodes relative position into the attention computation directly, (5) Modern LLMs are just very deep stacks of (attention + SwiGLU FFN) blocks with careful scaling.'''
    ),
    (
        "ml/attention-optimizations",
        "Explain attention optimization techniques including KV-cache for inference, Flash Attention for training, grouped-query attention (GQA), sliding window attention, multi-query attention, and speculative decoding. Show how these reduce memory and computation.",
        '''Standard self-attention is O(n**2) in memory and compute. For long sequences and large models, optimizations are essential for practical training and inference.

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
#   Step 3: compute attention for 1002 tokens  -> O(n**2) total
#
# With cache: Each step only computes for NEW token
#   Step 1: compute for 1 new token, cache K,V for 1000 prefix tokens
#   Step 2: compute for 1 new token using cached K,V (1001 entries)
#   Step 3: compute for 1 new token using cached K,V (1002 entries)
#   -> O(n) total compute, but O(n) memory for the cache
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
# GQA:  32 Q heads, 8 KV heads  (LLaMA 2 70B -- 4x less KV cache)
# MQA:  32 Q heads, 1 KV head   (extreme sharing -- Falcon, PaLM)
# Quality: MHA > GQA > MQA, but difference is small with enough training
```

### Flash Attention

IO-aware attention algorithm that avoids materializing the full NxN attention matrix:

```python
# Flash Attention is a CUDA kernel, not pure Python
# But here's the conceptual algorithm:

def flash_attention_conceptual(Q, K, V, block_size=256):
    """
    Standard attention materializes O(N**2) attention matrix in HBM (GPU main memory).
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
            torch.exp(scores - block_max.unsqueeze(-1)) @ V_block'''
    ),
]
