"""Efficient transformers — flash attention, KV cache optimization, sparse attention."""

PAIRS = [
    (
        "ai/flash-attention",
        "Show Flash Attention concepts: tiled computation, memory-efficient attention, and IO-aware algorithms for transformer training.",
        '''Flash Attention — IO-aware exact attention:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class StandardAttention(nn.Module):
    """Standard O(n²) attention for reference."""

    def forward(self, Q, K, V, mask=None):
        """
        Q, K, V: [batch, heads, seq_len, head_dim]
        Standard: materialize full n×n attention matrix in HBM.
        """
        d_k = Q.shape[-1]
        # This creates a [B, H, N, N] attention matrix (memory bottleneck)
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(d_k)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
        attn = F.softmax(scores, dim=-1)
        return torch.matmul(attn, V)


class TiledAttention(nn.Module):
    """Tiled attention (Flash Attention concept in Python).

    Key insight: instead of materializing full N×N attention matrix,
    process in tiles that fit in SRAM. Compute softmax incrementally
    using the online softmax trick.

    This is a pedagogical implementation; real Flash Attention is a CUDA kernel.
    """

    def __init__(self, block_size: int = 64):
        super().__init__()
        self.block_size = block_size

    def forward(self, Q, K, V, mask=None):
        B, H, N, D = Q.shape
        Bc = self.block_size
        Br = self.block_size

        # Output accumulator and softmax statistics
        O = torch.zeros_like(Q)
        L = torch.zeros(B, H, N, 1, device=Q.device)  # log-sum-exp
        M = torch.full((B, H, N, 1), float('-inf'), device=Q.device)  # running max

        scale = 1.0 / math.sqrt(D)

        # Tile over K/V blocks (outer loop)
        for j in range(0, N, Bc):
            Kj = K[:, :, j:j+Bc]
            Vj = V[:, :, j:j+Bc]

            # Tile over Q blocks (inner loop)
            for i in range(0, N, Br):
                Qi = Q[:, :, i:i+Br]

                # Compute attention scores for this tile
                Sij = torch.matmul(Qi, Kj.transpose(-2, -1)) * scale  # [B,H,Br,Bc]

                # Causal mask (optional)
                if mask is not None:
                    row_idx = torch.arange(i, min(i+Br, N), device=Q.device)
                    col_idx = torch.arange(j, min(j+Bc, N), device=Q.device)
                    causal = row_idx.unsqueeze(1) >= col_idx.unsqueeze(0)
                    Sij = Sij.masked_fill(~causal, float('-inf'))

                # Online softmax update
                Mi_old = M[:, :, i:i+Br]
                Mi_new = torch.maximum(Mi_old, Sij.max(dim=-1, keepdim=True).values)

                # Rescale old accumulator
                exp_old = torch.exp(Mi_old - Mi_new)
                exp_new = torch.exp(Sij - Mi_new)

                Li_old = L[:, :, i:i+Br]
                Li_new = exp_old * Li_old + exp_new.sum(dim=-1, keepdim=True)

                # Update output
                O[:, :, i:i+Br] = (
                    exp_old * O[:, :, i:i+Br] +
                    torch.matmul(exp_new, Vj)
                )

                M[:, :, i:i+Br] = Mi_new
                L[:, :, i:i+Br] = Li_new

        # Final normalization
        O = O / L
        return O


def use_flash_attention():
    """Use PyTorch's built-in Flash Attention (recommended)."""
    B, H, N, D = 2, 32, 4096, 128

    Q = torch.randn(B, H, N, D, device="cuda", dtype=torch.bfloat16)
    K = torch.randn(B, H, N, D, device="cuda", dtype=torch.bfloat16)
    V = torch.randn(B, H, N, D, device="cuda", dtype=torch.bfloat16)

    # PyTorch 2.0+ automatically uses Flash Attention when possible
    output = F.scaled_dot_product_attention(
        Q, K, V,
        is_causal=True,     # Causal mask (autoregressive)
        # enable_flash=True  # Hint to use flash kernel
    )

    return output  # [B, H, N, D]
```

Attention algorithm comparison:

| Algorithm | Memory | Compute | Exact? |
|-----------|--------|---------|--------|
| **Standard** | O(N²) | O(N²D) | Yes |
| **Flash Attention** | O(N) | O(N²D) | Yes |
| **Flash Attention 2** | O(N) | O(N²D) (2x faster) | Yes |
| **Ring Attention** | O(N/P) distributed | O(N²D/P) | Yes |
| **Sparse (local+global)** | O(N√N) | O(N√N D) | No |

Key patterns:
1. **Tiled computation** — process attention in SRAM-sized blocks; avoid materializing N×N matrix
2. **Online softmax** — track running max and sum-exp; enables block-wise exact softmax
3. **IO-awareness** — minimize HBM reads/writes; computation is fast, memory transfer is the bottleneck
4. **`scaled_dot_product_attention`** — PyTorch 2.0+ auto-selects Flash/Memory-efficient/math backend
5. **BFloat16** — Flash Attention requires fp16/bf16; bf16 preferred for training stability'''
    ),
    (
        "ai/kv-cache-optimization",
        "Show KV cache optimization for LLM inference: paged attention (vLLM), sliding window, grouped-query attention, and memory management.",
        '''KV cache optimization for efficient LLM inference:

```python
import torch
import torch.nn as nn
import math
from dataclasses import dataclass


@dataclass
class CacheConfig:
    max_seq_len: int = 8192
    n_layers: int = 32
    n_kv_heads: int = 8
    head_dim: int = 128
    block_size: int = 16  # For paged attention
    dtype: torch.dtype = torch.float16


class PagedKVCache:
    """Paged Attention (vLLM): manage KV cache like OS virtual memory.

    Instead of contiguous tensors per sequence, allocate fixed-size
    blocks that can be shared, copied, and freed independently.
    """

    def __init__(self, config: CacheConfig, n_blocks: int = 1024):
        self.config = config
        self.block_size = config.block_size

        # Physical block pool (pre-allocated GPU memory)
        self.k_pool = torch.zeros(
            n_blocks, config.n_layers, config.n_kv_heads,
            config.block_size, config.head_dim,
            dtype=config.dtype, device="cuda",
        )
        self.v_pool = torch.zeros_like(self.k_pool)

        # Block allocation table
        self.free_blocks = list(range(n_blocks))
        self.sequence_blocks: dict[int, list[int]] = {}  # seq_id -> [block_ids]

    def allocate(self, seq_id: int, n_tokens: int) -> list[int]:
        """Allocate blocks for a sequence."""
        n_blocks_needed = (n_tokens + self.block_size - 1) // self.block_size
        if len(self.free_blocks) < n_blocks_needed:
            raise RuntimeError("Out of KV cache blocks")

        blocks = [self.free_blocks.pop() for _ in range(n_blocks_needed)]
        self.sequence_blocks[seq_id] = blocks
        return blocks

    def free(self, seq_id: int):
        """Free blocks for a completed sequence."""
        if seq_id in self.sequence_blocks:
            self.free_blocks.extend(self.sequence_blocks.pop(seq_id))

    def write(self, seq_id: int, layer: int, position: int,
              k: torch.Tensor, v: torch.Tensor):
        """Write KV for a token at given position."""
        block_idx = position // self.block_size
        offset = position % self.block_size
        physical_block = self.sequence_blocks[seq_id][block_idx]
        self.k_pool[physical_block, layer, :, offset] = k
        self.v_pool[physical_block, layer, :, offset] = v

    def read(self, seq_id: int, layer: int, length: int):
        """Read KV cache for attention computation."""
        blocks = self.sequence_blocks[seq_id]
        n_blocks = (length + self.block_size - 1) // self.block_size

        k_parts = [self.k_pool[blocks[i], layer] for i in range(n_blocks)]
        v_parts = [self.v_pool[blocks[i], layer] for i in range(n_blocks)]

        k = torch.cat(k_parts, dim=1)[:, :length]
        v = torch.cat(v_parts, dim=1)[:, :length]
        return k, v

    def fork(self, src_seq_id: int, dst_seq_id: int):
        """Copy-on-write: share blocks between sequences (beam search)."""
        self.sequence_blocks[dst_seq_id] = self.sequence_blocks[src_seq_id].copy()


class SlidingWindowAttention(nn.Module):
    """Sliding window attention (Mistral-style): limit attention span.

    Each token only attends to the last W tokens.
    Reduces KV cache from O(n) to O(W) per layer.
    """

    def __init__(self, d_model: int, n_heads: int, window_size: int = 4096):
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.window_size = window_size

        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x: torch.Tensor, cache_k=None, cache_v=None):
        B, L, D = x.shape
        qkv = self.qkv(x).reshape(B, L, 3, self.n_heads, self.head_dim)
        q, k, v = qkv.unbind(dim=2)
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        # Append to cache
        if cache_k is not None:
            k = torch.cat([cache_k, k], dim=2)
            v = torch.cat([cache_v, v], dim=2)

        # Trim to window size
        if k.shape[2] > self.window_size:
            k = k[:, :, -self.window_size:]
            v = v[:, :, -self.window_size:]

        # Standard attention on windowed KV
        out = torch.nn.functional.scaled_dot_product_attention(q, k, v, is_causal=True)
        out = out.transpose(1, 2).reshape(B, L, D)
        return self.out(out), k, v


class GQAttention(nn.Module):
    """Grouped-Query Attention: share KV heads across query heads.

    MHA: n_kv_heads = n_heads (every head has its own KV)
    GQA: n_kv_heads < n_heads (multiple Q heads share KV)
    MQA: n_kv_heads = 1 (all Q heads share one KV)
    """

    def __init__(self, d_model: int, n_heads: int = 32, n_kv_heads: int = 8):
        super().__init__()
        self.n_heads = n_heads
        self.n_kv_heads = n_kv_heads
        self.head_dim = d_model // n_heads
        self.kv_group_size = n_heads // n_kv_heads

        self.q_proj = nn.Linear(d_model, n_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(d_model, n_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(d_model, n_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x):
        B, L, _ = x.shape
        q = self.q_proj(x).view(B, L, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, L, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, L, self.n_kv_heads, self.head_dim).transpose(1, 2)

        # Repeat KV heads to match Q heads
        k = k.repeat_interleave(self.kv_group_size, dim=1)
        v = v.repeat_interleave(self.kv_group_size, dim=1)

        out = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self.o_proj(out.transpose(1, 2).reshape(B, L, -1))
```

KV cache comparison:

| Technique | Cache per token | Context length | Quality |
|-----------|----------------|---------------|---------|
| **Full MHA** | n_heads × head_dim × 2 | Full | Best |
| **GQA (8 KV heads)** | 8 × head_dim × 2 (4x less) | Full | ~Same |
| **MQA (1 KV head)** | head_dim × 2 (32x less) | Full | Slight loss |
| **Sliding window** | W × head_dim × 2 | W tokens | Good for long ctx |
| **Paged attention** | Same total, better utilization | Full | Same |

Key patterns:
1. **Paged attention** — virtual memory for KV cache; eliminates fragmentation, enables sharing
2. **Sliding window** — fixed-size attention window; O(W) cache instead of O(n)
3. **GQA** — multiple query heads share KV heads; 4-8x cache reduction with minimal quality loss
4. **Copy-on-write** — beam search shares KV blocks until divergence; huge memory savings
5. **Block management** — allocate/free fixed-size blocks; no sequence-length pre-allocation needed'''
    ),
    (
        "ai/mixture-of-experts",
        "Show Mixture of Experts (MoE) architecture: sparse gating, expert routing, load balancing, and training considerations.",
        '''Mixture of Experts for efficient scaling:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class TopKRouter(nn.Module):
    """Token-level top-k expert routing with load balancing.

    Each token is routed to top-k experts (typically k=2).
    Load balancing loss prevents all tokens going to same experts.
    """

    def __init__(self, d_model: int, n_experts: int, top_k: int = 2):
        super().__init__()
        self.gate = nn.Linear(d_model, n_experts, bias=False)
        self.n_experts = n_experts
        self.top_k = top_k

    def forward(self, x: torch.Tensor):
        """x: [batch*seq, d_model] -> routing weights and indices."""
        logits = self.gate(x)  # [B*S, n_experts]

        # Top-k selection
        weights, indices = torch.topk(logits, self.top_k, dim=-1)
        weights = F.softmax(weights, dim=-1)

        # Load balancing loss (auxiliary)
        balance_loss = self._load_balance_loss(logits)

        return weights, indices, balance_loss

    def _load_balance_loss(self, logits: torch.Tensor) -> torch.Tensor:
        """Encourage uniform expert utilization.

        Loss = N * sum(f_i * P_i) where:
        - f_i = fraction of tokens routed to expert i
        - P_i = average gate probability for expert i
        """
        probs = F.softmax(logits, dim=-1)  # [B*S, n_experts]

        # Fraction of tokens per expert (from hard routing)
        top1 = logits.argmax(dim=-1)
        freq = torch.zeros(self.n_experts, device=logits.device)
        for i in range(self.n_experts):
            freq[i] = (top1 == i).float().mean()

        # Average probability per expert
        avg_prob = probs.mean(dim=0)

        return self.n_experts * (freq * avg_prob).sum()


class Expert(nn.Module):
    """Single expert (SwiGLU feed-forward)."""

    def __init__(self, d_model: int, d_ff: int):
        super().__init__()
        self.w1 = nn.Linear(d_model, d_ff, bias=False)
        self.w2 = nn.Linear(d_ff, d_model, bias=False)
        self.w3 = nn.Linear(d_model, d_ff, bias=False)

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class MoELayer(nn.Module):
    """Sparse MoE layer: route tokens to top-k experts."""

    def __init__(self, d_model: int, d_ff: int, n_experts: int = 16, top_k: int = 2):
        super().__init__()
        self.router = TopKRouter(d_model, n_experts, top_k)
        self.experts = nn.ModuleList([Expert(d_model, d_ff) for _ in range(n_experts)])
        self.top_k = top_k

    def forward(self, x: torch.Tensor):
        """x: [batch, seq, d_model]"""
        B, S, D = x.shape
        x_flat = x.reshape(-1, D)

        weights, indices, balance_loss = self.router(x_flat)

        # Compute expert outputs (only for routed tokens)
        output = torch.zeros_like(x_flat)

        for k in range(self.top_k):
            expert_idx = indices[:, k]  # Which expert for each token
            expert_weight = weights[:, k].unsqueeze(-1)

            for e in range(len(self.experts)):
                mask = (expert_idx == e)
                if mask.any():
                    expert_input = x_flat[mask]
                    expert_output = self.experts[e](expert_input)
                    output[mask] += expert_weight[mask] * expert_output

        return output.reshape(B, S, D), balance_loss


class MoETransformerBlock(nn.Module):
    """Transformer block with MoE feed-forward."""

    def __init__(self, d_model: int, n_heads: int, n_experts: int = 16):
        super().__init__()
        self.attn_norm = nn.RMSNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.ffn_norm = nn.RMSNorm(d_model)
        self.moe = MoELayer(d_model, d_model * 4, n_experts)

    def forward(self, x):
        # Attention
        h = self.attn_norm(x)
        h, _ = self.attn(h, h, h)
        x = x + h

        # MoE FFN
        h = self.ffn_norm(x)
        h, balance_loss = self.moe(h)
        x = x + h

        return x, balance_loss
```

MoE comparison:

| Model | Total params | Active params | Experts | Top-k |
|-------|-------------|--------------|---------|-------|
| **Mixtral 8x7B** | 47B | 13B | 8 | 2 |
| **DBRX** | 132B | 36B | 16 | 4 |
| **Jamba** | 52B | 12B | 16 | 2 |
| **Dense (Llama 70B)** | 70B | 70B | N/A | N/A |

Key patterns:
1. **Sparse routing** — each token only uses top-k experts; most parameters inactive per token
2. **Load balancing loss** — auxiliary loss prevents expert collapse (all tokens → same expert)
3. **SwiGLU experts** — each expert is a standard FFN; shared attention, expert MLP
4. **Expert parallelism** — distribute experts across GPUs; each GPU holds subset of experts
5. **Capacity factor** — limit max tokens per expert per batch; drop overflow for efficiency'''
    ),
]
