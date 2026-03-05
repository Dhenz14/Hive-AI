"""State Space Models — Mamba, S4, and linear-time sequence modeling."""

PAIRS = [
    (
        "ai/mamba-architecture",
        "Show Mamba (selective state space model) architecture: selective scan, hardware-aware implementation, and comparison to transformers.",
        '''Mamba — selective state space model for linear-time sequences:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange
import math


class SelectiveSSM(nn.Module):
    """Mamba's Selective State Space Model.

    Unlike standard SSMs (S4) with fixed dynamics, Mamba makes
    the state transition matrices input-dependent (selective).
    This allows content-based reasoning while maintaining O(n) complexity.
    """

    def __init__(self, d_model: int, d_state: int = 16, d_conv: int = 4,
                 expand: int = 2, dt_rank: str | int = "auto"):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.d_conv = d_conv
        self.expand = expand
        self.d_inner = d_model * expand

        if dt_rank == "auto":
            self.dt_rank = math.ceil(d_model / 16)
        else:
            self.dt_rank = dt_rank

        # Input projection: x -> (z, x) where z is the gate
        self.in_proj = nn.Linear(d_model, self.d_inner * 2, bias=False)

        # Depthwise convolution (local context before SSM)
        self.conv1d = nn.Conv1d(
            self.d_inner, self.d_inner, d_conv,
            padding=d_conv - 1, groups=self.d_inner,
        )

        # SSM parameters — input-dependent (selective)
        # x -> (B, C, dt) projections
        self.x_proj = nn.Linear(self.d_inner, self.dt_rank + d_state * 2, bias=False)

        # dt projection (dt_rank -> d_inner)
        self.dt_proj = nn.Linear(self.dt_rank, self.d_inner, bias=True)

        # Initialize A as a structured matrix (HiPPO)
        A = torch.arange(1, d_state + 1, dtype=torch.float32).repeat(self.d_inner, 1)
        self.A_log = nn.Parameter(torch.log(A))  # Log parameterization for stability
        self.D = nn.Parameter(torch.ones(self.d_inner))  # Skip connection

        # Output projection
        self.out_proj = nn.Linear(self.d_inner, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: [batch, seq_len, d_model]
        Returns: [batch, seq_len, d_model]
        """
        B, L, D = x.shape

        # Input projection and split into x and gate z
        xz = self.in_proj(x)  # [B, L, 2 * d_inner]
        x, z = xz.chunk(2, dim=-1)  # Each [B, L, d_inner]

        # Depthwise conv for local context
        x = rearrange(x, "b l d -> b d l")
        x = self.conv1d(x)[:, :, :L]
        x = rearrange(x, "b d l -> b l d")
        x = F.silu(x)

        # Selective SSM
        y = self.ssm(x)

        # Gated output
        z = F.silu(z)
        output = y * z
        return self.out_proj(output)

    def ssm(self, x: torch.Tensor) -> torch.Tensor:
        """Selective scan — the core of Mamba.

        Makes A, B, C, dt input-dependent for content-based reasoning.
        """
        B, L, D = x.shape

        # Compute input-dependent SSM parameters
        x_dbl = self.x_proj(x)  # [B, L, dt_rank + 2*d_state]
        dt, B_param, C_param = x_dbl.split(
            [self.dt_rank, self.d_state, self.d_state], dim=-1
        )

        # dt: discretization step (controls how much state updates)
        dt = self.dt_proj(dt)  # [B, L, d_inner]
        dt = F.softplus(dt)    # Ensure positive

        # A: state transition (from log parameterization)
        A = -torch.exp(self.A_log)  # [d_inner, d_state], negative for stability

        # Selective scan (sequential, but hardware-optimized in practice)
        return self.selective_scan(x, dt, A, B_param, C_param)

    def selective_scan(self, x: torch.Tensor, dt: torch.Tensor,
                       A: torch.Tensor, B: torch.Tensor, C: torch.Tensor) -> torch.Tensor:
        """Scan operation: process sequence with input-dependent dynamics.

        h_t = A_bar * h_{t-1} + B_bar * x_t
        y_t = C_t * h_t + D * x_t
        """
        batch, seq_len, d_inner = x.shape
        d_state = A.shape[1]

        # Discretize A and B using dt
        # A_bar = exp(dt * A)
        dt_A = torch.einsum("bld,dn->bldn", dt, A)
        A_bar = torch.exp(dt_A)

        # B_bar = dt * B
        dt_B = torch.einsum("bld,bln->bldn", dt, B)

        # Sequential scan (in practice, use parallel scan or CUDA kernel)
        h = torch.zeros(batch, d_inner, d_state, device=x.device, dtype=x.dtype)
        outputs = []

        for t in range(seq_len):
            h = A_bar[:, t] * h + dt_B[:, t] * x[:, t].unsqueeze(-1)
            y_t = torch.einsum("bdn,bn->bd", h, C[:, t])
            outputs.append(y_t)

        y = torch.stack(outputs, dim=1)  # [B, L, d_inner]
        y = y + x * self.D  # Skip connection
        return y


class MambaBlock(nn.Module):
    """Single Mamba block with residual connection and normalization."""

    def __init__(self, d_model: int, d_state: int = 16, d_conv: int = 4, expand: int = 2):
        super().__init__()
        self.norm = nn.RMSNorm(d_model)
        self.mamba = SelectiveSSM(d_model, d_state, d_conv, expand)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.mamba(self.norm(x))


class MambaModel(nn.Module):
    """Full Mamba language model."""

    def __init__(self, vocab_size: int = 32000, d_model: int = 2560,
                 n_layers: int = 64, d_state: int = 16):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.layers = nn.ModuleList([
            MambaBlock(d_model, d_state) for _ in range(n_layers)
        ])
        self.norm_f = nn.RMSNorm(d_model)
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)
        self.lm_head.weight = self.embedding.weight  # Weight tying

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.embedding(input_ids)
        for layer in self.layers:
            x = layer(x)
        x = self.norm_f(x)
        return self.lm_head(x)
```

Mamba vs Transformer:

| Aspect | Transformer | Mamba |
|--------|------------|-------|
| **Complexity** | O(n²) attention | O(n) selective scan |
| **Memory** | O(n²) attention matrix | O(1) per step (recurrent) |
| **Long context** | Degrades or needs tricks | Native O(n) |
| **Inference** | KV-cache grows linearly | Fixed state size |
| **Parallelism** | Fully parallel | Parallel scan (slightly less) |
| **In-context learning** | Strong | Weaker (no explicit attention) |

Key patterns:
1. **Selective scan** — input-dependent A, B, C matrices allow content-based filtering (unlike fixed S4)
2. **HiPPO initialization** — A matrix initialized to approximate continuous-time history compression
3. **Gated architecture** — SiLU-gated output similar to GLU; x branch processes, z branch gates
4. **Log parameterization** — `A_log` ensures stability (A stays negative → state decays)
5. **Depthwise conv** — local context before SSM scan; replaces positional embeddings'''
    ),
    (
        "ai/hybrid-mamba-transformer",
        "Show hybrid Mamba-Transformer architectures: combining SSM layers with attention layers for the best of both worlds.",
        '''Hybrid Mamba-Transformer (Jamba-style):

```python
import torch
import torch.nn as nn
from typing import Optional


class HybridBlock(nn.Module):
    """Hybrid block: alternate between Mamba and Attention layers.

    Jamba architecture: Mamba layers for long-range + Attention layers
    for precise retrieval. Attention every N layers (e.g., every 4th).
    """

    def __init__(self, d_model: int, layer_idx: int,
                 attention_every: int = 4, num_heads: int = 32,
                 num_kv_heads: int = 8, d_state: int = 16):
        super().__init__()
        self.layer_idx = layer_idx
        self.use_attention = (layer_idx % attention_every == 0)

        self.norm = nn.RMSNorm(d_model)

        if self.use_attention:
            # Standard GQA attention (for precise recall)
            self.attn = GroupedQueryAttention(d_model, num_heads, num_kv_heads)
        else:
            # Mamba SSM (for long-range processing)
            self.mamba = SelectiveSSMSimple(d_model, d_state)

        # MLP (shared for both types)
        self.mlp_norm = nn.RMSNorm(d_model)
        self.mlp = SwiGLU(d_model)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        # Core layer (attention or mamba)
        residual = x
        x = self.norm(x)
        if self.use_attention:
            x = self.attn(x, mask=mask)
        else:
            x = self.mamba(x)
        x = residual + x

        # MLP
        residual = x
        x = self.mlp_norm(x)
        x = self.mlp(x)
        x = residual + x

        return x


class SelectiveSSMSimple(nn.Module):
    """Simplified selective SSM for hybrid architecture."""

    def __init__(self, d_model: int, d_state: int = 16, expand: int = 2):
        super().__init__()
        d_inner = d_model * expand

        self.in_proj = nn.Linear(d_model, d_inner * 2, bias=False)
        self.conv1d = nn.Conv1d(d_inner, d_inner, 4, padding=3, groups=d_inner)
        self.x_proj = nn.Linear(d_inner, d_state * 2 + d_inner, bias=False)
        self.out_proj = nn.Linear(d_inner, d_model, bias=False)
        self.D = nn.Parameter(torch.ones(d_inner))
        self.A_log = nn.Parameter(torch.log(torch.arange(1, d_state + 1).float().repeat(d_inner, 1)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, L, D = x.shape
        xz = self.in_proj(x)
        x_branch, z = xz.chunk(2, dim=-1)

        x_branch = self.conv1d(x_branch.transpose(1, 2))[:, :, :L].transpose(1, 2)
        x_branch = F.silu(x_branch)

        # Simplified selective scan
        params = self.x_proj(x_branch)
        B_param, C_param, dt = params.split(
            [self.A_log.shape[1], self.A_log.shape[1], x_branch.shape[-1]], dim=-1
        )
        dt = F.softplus(dt)
        A = -torch.exp(self.A_log)

        # Recurrent scan
        h = torch.zeros(B, x_branch.shape[-1], self.A_log.shape[1], device=x.device)
        outputs = []
        for t in range(L):
            h = torch.exp(dt[:, t].unsqueeze(-1) * A) * h + dt[:, t].unsqueeze(-1) * B_param[:, t].unsqueeze(1) * x_branch[:, t].unsqueeze(-1)
            y_t = (h * C_param[:, t].unsqueeze(1)).sum(-1)
            outputs.append(y_t)

        y = torch.stack(outputs, dim=1) + x_branch * self.D
        return self.out_proj(y * F.silu(z))


class GroupedQueryAttention(nn.Module):
    """GQA for attention layers in hybrid model."""

    def __init__(self, d_model: int, num_heads: int = 32, num_kv_heads: int = 8):
        super().__init__()
        self.num_heads = num_heads
        self.num_kv_heads = num_kv_heads
        self.head_dim = d_model // num_heads
        self.q_proj = nn.Linear(d_model, num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(d_model, num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(d_model, num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, L, _ = x.shape
        q = self.q_proj(x).view(B, L, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)
        k = k.repeat_interleave(self.num_heads // self.num_kv_heads, dim=1)
        v = v.repeat_interleave(self.num_heads // self.num_kv_heads, dim=1)
        out = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self.o_proj(out.transpose(1, 2).reshape(B, L, -1))


class SwiGLU(nn.Module):
    def __init__(self, d_model: int, expand: float = 8/3):
        super().__init__()
        hidden = int(d_model * expand)
        self.w1 = nn.Linear(d_model, hidden, bias=False)
        self.w2 = nn.Linear(hidden, d_model, bias=False)
        self.w3 = nn.Linear(d_model, hidden, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class JambaModel(nn.Module):
    """Jamba: hybrid Mamba-Transformer with MoE.

    Architecture: 52 layers total
    - Mamba layers: 45 layers (fast, O(n))
    - Attention layers: 7 layers (every 8th, precise retrieval)
    - MoE: 16 experts, top-2 routing (every other MLP)
    """

    def __init__(self, vocab_size: int = 65536, d_model: int = 4096,
                 n_layers: int = 52, attention_every: int = 8):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d_model)
        self.layers = nn.ModuleList([
            HybridBlock(d_model, i, attention_every) for i in range(n_layers)
        ])
        self.norm = nn.RMSNorm(d_model)
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.embed(input_ids)
        for layer in self.layers:
            x = layer(x)
        return self.lm_head(self.norm(x))
```

Hybrid architecture comparison:

| Model | Mamba layers | Attention layers | Context | Params |
|-------|-------------|-----------------|---------|--------|
| **Jamba** | 45 | 7 (every 8th) | 256K | 52B (12B active) |
| **Mamba-2** | All | 0 | Unlimited | 2.8B |
| **Zamba** | 6 | 1 (shared) | 4K+ | 7B |
| **Transformer** | 0 | All | Limited by O(n²) | Varies |

Key patterns:
1. **Attention for recall** — sparse attention layers (every Nth) handle precise information retrieval
2. **Mamba for processing** — majority of layers are SSM for efficient long-range modeling
3. **Hybrid KV-cache** — only attention layers need KV-cache; total cache is much smaller
4. **Best of both** — O(n) for most processing + O(n²) for occasional precise attention
5. **Shared attention** — some architectures (Zamba) share a single attention layer across all positions'''
    ),
]
