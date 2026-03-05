"""Long-context LLMs — RoPE scaling, YaRN, efficient attention for 100K+ tokens."""

PAIRS = [
    (
        "ai/rope-scaling-yarn",
        "Explain RoPE (Rotary Position Embeddings) scaling techniques: NTK-aware interpolation, YaRN, and how to extend context length beyond training.",
        '''RoPE scaling and YaRN for extending context length:

```python
import torch
import math
from torch import nn, Tensor


# --- Standard RoPE (Rotary Position Embeddings) ---

class RotaryEmbedding(nn.Module):
    """RoPE: encodes position as rotation in 2D subspaces."""

    def __init__(self, dim: int, max_seq_len: int = 4096, base: float = 10000.0):
        super().__init__()
        self.dim = dim
        self.base = base
        self.max_seq_len = max_seq_len

        # Precompute frequency bands: theta_i = base^(-2i/d)
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq, persistent=False)

        # Cache cos/sin for all positions up to max_seq_len
        self._build_cache(max_seq_len)

    def _build_cache(self, seq_len: int):
        positions = torch.arange(seq_len, dtype=torch.float32)
        # Outer product: [seq_len] x [dim/2] -> [seq_len, dim/2]
        freqs = torch.outer(positions, self.inv_freq)
        # Duplicate for real/imaginary pairs: [seq_len, dim]
        emb = torch.cat([freqs, freqs], dim=-1)
        self.register_buffer("cos_cached", emb.cos(), persistent=False)
        self.register_buffer("sin_cached", emb.sin(), persistent=False)

    def forward(self, seq_len: int) -> tuple[Tensor, Tensor]:
        if seq_len > self.max_seq_len:
            self._build_cache(seq_len)
            self.max_seq_len = seq_len
        return self.cos_cached[:seq_len], self.sin_cached[:seq_len]


def apply_rotary_pos_emb(q: Tensor, k: Tensor, cos: Tensor, sin: Tensor) -> tuple[Tensor, Tensor]:
    """Apply RoPE rotation to query and key tensors."""
    def rotate_half(x: Tensor) -> Tensor:
        x1, x2 = x.chunk(2, dim=-1)
        return torch.cat([-x2, x1], dim=-1)

    # cos/sin shape: [seq_len, dim] -> broadcast to [1, 1, seq_len, dim]
    cos = cos.unsqueeze(0).unsqueeze(0)
    sin = sin.unsqueeze(0).unsqueeze(0)

    q_rotated = q * cos + rotate_half(q) * sin
    k_rotated = k * cos + rotate_half(k) * sin
    return q_rotated, k_rotated


# --- NTK-aware RoPE scaling (simple interpolation) ---

class NTKAwareRoPE(RotaryEmbedding):
    """Scale RoPE base frequency for longer contexts without fine-tuning.

    Key insight: instead of linearly interpolating positions (which
    compresses ALL frequencies), scale the base frequency so that
    high-frequency components are preserved while low-frequency
    components stretch to cover longer sequences.
    """

    def __init__(
        self,
        dim: int,
        max_seq_len: int = 4096,
        base: float = 10000.0,
        scale_factor: float = 4.0,  # 4x = 16K context from 4K training
    ):
        # NTK-aware: scale base by factor^(dim/(dim-2))
        scaled_base = base * scale_factor ** (dim / (dim - 2))
        super().__init__(dim, max_seq_len, base=scaled_base)
        self.scale_factor = scale_factor


# --- YaRN (Yet another RoPE extensioN) ---

class YaRNRoPE(nn.Module):
    """YaRN: state-of-the-art RoPE extension combining NTK + attention scaling.

    Three key innovations:
    1. NTK-by-parts: different scaling for different frequency bands
    2. Attention temperature scaling: sqrt(1/t) factor
    3. Dynamic NTK: adjusts scaling based on actual sequence length
    """

    def __init__(
        self,
        dim: int,
        max_seq_len: int = 4096,
        original_max_seq_len: int = 4096,
        base: float = 10000.0,
        scale_factor: float = 16.0,  # Target: 16x context extension
        beta_fast: float = 32.0,     # Frequency band boundaries
        beta_slow: float = 1.0,
    ):
        super().__init__()
        self.dim = dim
        self.original_max_seq_len = original_max_seq_len
        self.scale_factor = scale_factor

        # Compute per-dimension interpolation ratios (NTK-by-parts)
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        wavelengths = 2 * math.pi / inv_freq

        # Classify each frequency band
        low_freq_cutoff = original_max_seq_len / beta_slow
        high_freq_cutoff = original_max_seq_len / beta_fast

        # Ramp function: smooth transition between interpolated and original
        ramp = ((wavelengths / (2 * math.pi)) - beta_fast) / (beta_slow - beta_fast)
        ramp = ramp.clamp(0.0, 1.0)

        # Scale factors per frequency band:
        # - High frequency (short wavelength): keep original (ramp=0)
        # - Low frequency (long wavelength): full interpolation (ramp=1)
        # - Middle: smooth blend
        inv_freq_scaled = inv_freq / scale_factor
        inv_freq_yarn = inv_freq * (1 - ramp) + inv_freq_scaled * ramp

        self.register_buffer("inv_freq", inv_freq_yarn, persistent=False)

        # Attention temperature scaling: counteracts dilution from longer sequences
        # sqrt(0.1 * ln(scale_factor) + 1)
        self.attn_scale = math.sqrt(0.1 * math.log(scale_factor) + 1.0)

        self._build_cache(max_seq_len)

    def _build_cache(self, seq_len: int):
        positions = torch.arange(seq_len, dtype=torch.float32)
        freqs = torch.outer(positions, self.inv_freq)
        emb = torch.cat([freqs, freqs], dim=-1)
        self.register_buffer("cos_cached", emb.cos() * self.attn_scale, persistent=False)
        self.register_buffer("sin_cached", emb.sin() * self.attn_scale, persistent=False)
        self.max_seq_len = seq_len

    def forward(self, seq_len: int) -> tuple[Tensor, Tensor]:
        if seq_len > self.max_seq_len:
            self._build_cache(seq_len)
        return self.cos_cached[:seq_len], self.sin_cached[:seq_len]


# --- Usage: extending a 4K model to 64K ---

def create_extended_rope(
    dim: int = 128,
    original_context: int = 4096,
    target_context: int = 65536,
    method: str = "yarn",
) -> nn.Module:
    """Create RoPE with context extension."""
    scale_factor = target_context / original_context  # 16x

    if method == "linear":
        # Simple linear interpolation (worst quality)
        rope = RotaryEmbedding(dim, target_context)
        rope.inv_freq = rope.inv_freq / scale_factor
        return rope
    elif method == "ntk":
        return NTKAwareRoPE(dim, target_context, scale_factor=scale_factor)
    elif method == "yarn":
        return YaRNRoPE(
            dim, target_context,
            original_max_seq_len=original_context,
            scale_factor=scale_factor,
        )
    else:
        raise ValueError(f"Unknown method: {method}")


# --- Practical: patching HuggingFace models ---

def patch_model_for_long_context(model, target_length: int = 32768):
    """Patch a HuggingFace model's RoPE for longer context.

    Works with Llama, Mistral, Qwen, and similar architectures.
    """
    config = model.config
    original_length = config.max_position_embeddings
    scale = target_length / original_length

    # Update config
    config.max_position_embeddings = target_length
    config.rope_scaling = {
        "type": "yarn",
        "factor": scale,
        "original_max_position_embeddings": original_length,
    }

    # HuggingFace models with rope_scaling in config will
    # automatically use the scaled RoPE implementation
    # For manual patching, replace rotary_emb in each attention layer:
    for layer in model.model.layers:
        attn = layer.self_attn
        attn.rotary_emb = YaRNRoPE(
            dim=config.hidden_size // config.num_attention_heads,
            max_seq_len=target_length,
            original_max_seq_len=original_length,
            scale_factor=scale,
        )

    return model
```

RoPE scaling techniques compared:

| Method | Quality | Training needed | Complexity |
|--------|---------|----------------|------------|
| **Linear interpolation** | Poor at >2x | Fine-tune recommended | Trivial |
| **NTK-aware** | Good at 4-8x | Often works zero-shot | Low |
| **YaRN** | Best at 16-64x | Brief fine-tune ideal | Medium |
| **Dynamic NTK** | Good, adaptive | Zero-shot | Low |

Key concepts:
1. **RoPE** — encodes position as rotation angle; pairs of dimensions rotate at different frequencies
2. **NTK-aware scaling** — scales the base frequency rather than positions, preserving high-frequency detail
3. **YaRN NTK-by-parts** — treats frequency bands differently: high-freq unchanged, low-freq interpolated, middle blended
4. **Attention temperature** — `sqrt(0.1 * ln(s) + 1)` compensates for attention score dilution at longer contexts
5. **Practical rule** — YaRN with brief continued pre-training (100-1000 steps) gives best results for large extensions'''
    ),
    (
        "ai/efficient-long-context",
        "Show efficient attention patterns for 100K+ token contexts: sliding window, sparse attention, ring attention, and KV-cache compression.",
        '''Efficient attention for long-context LLMs:

```python
import torch
import torch.nn.functional as F
from torch import nn, Tensor
import math


# --- Sliding Window Attention (Mistral-style) ---

class SlidingWindowAttention(nn.Module):
    """Attend only to local window + sink tokens.

    Complexity: O(n * w) instead of O(n^2) where w = window_size.
    Used by Mistral, Gemma 2, and others.
    """

    def __init__(
        self,
        hidden_size: int,
        num_heads: int,
        window_size: int = 4096,
        num_sink_tokens: int = 4,  # Always-visible initial tokens
    ):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.window_size = window_size
        self.num_sink_tokens = num_sink_tokens

        self.qkv = nn.Linear(hidden_size, 3 * hidden_size, bias=False)
        self.out_proj = nn.Linear(hidden_size, hidden_size, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        B, L, _ = x.shape
        qkv = self.qkv(x).reshape(B, L, 3, self.num_heads, self.head_dim)
        q, k, v = qkv.unbind(dim=2)
        q, k, v = [t.transpose(1, 2) for t in (q, k, v)]  # [B, H, L, D]

        # Build sliding window mask
        mask = self._build_mask(L, x.device)

        scale = 1.0 / math.sqrt(self.head_dim)
        attn = torch.matmul(q, k.transpose(-2, -1)) * scale
        attn = attn.masked_fill(~mask, float("-inf"))
        attn = F.softmax(attn, dim=-1)

        out = torch.matmul(attn, v)
        out = out.transpose(1, 2).reshape(B, L, -1)
        return self.out_proj(out)

    def _build_mask(self, seq_len: int, device: torch.device) -> Tensor:
        """Causal mask with sliding window + sink tokens."""
        # Start with causal mask
        mask = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))

        # Apply sliding window
        for i in range(seq_len):
            window_start = max(self.num_sink_tokens, i - self.window_size + 1)
            # Zero out positions before window (but keep sink tokens)
            mask[i, self.num_sink_tokens:window_start] = False

        return mask.unsqueeze(0).unsqueeze(0)  # [1, 1, L, L]


# --- Grouped Query Attention (GQA) ---

class GroupedQueryAttention(nn.Module):
    """GQA: share KV heads across query head groups.

    Reduces KV-cache size by num_heads/num_kv_heads ratio.
    Used by Llama 3, Mistral, Qwen 2+.
    """

    def __init__(
        self,
        hidden_size: int,
        num_heads: int = 32,      # Query heads
        num_kv_heads: int = 8,    # KV heads (4x fewer = 4x smaller cache)
    ):
        super().__init__()
        self.num_heads = num_heads
        self.num_kv_heads = num_kv_heads
        self.head_dim = hidden_size // num_heads
        self.num_groups = num_heads // num_kv_heads

        self.q_proj = nn.Linear(hidden_size, num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(hidden_size, num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(hidden_size, num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(hidden_size, hidden_size, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        B, L, _ = x.shape

        q = self.q_proj(x).view(B, L, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)

        # Expand KV heads to match query heads by repeating
        # [B, num_kv_heads, L, D] -> [B, num_heads, L, D]
        k = k.repeat_interleave(self.num_groups, dim=1)
        v = v.repeat_interleave(self.num_groups, dim=1)

        # Standard scaled dot-product attention (uses Flash Attention if available)
        out = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        out = out.transpose(1, 2).reshape(B, L, -1)
        return self.o_proj(out)


# --- KV-Cache Quantization ---

class QuantizedKVCache:
    """Compress KV cache to INT8/INT4 for longer contexts.

    At 100K tokens with 32 layers, FP16 KV cache = ~25GB.
    INT4 quantization reduces to ~6GB.
    """

    def __init__(self, num_layers: int, num_heads: int, head_dim: int, bits: int = 4):
        self.bits = bits
        self.cache: dict[int, dict[str, Tensor]] = {}

    def quantize(self, tensor: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """Quantize FP16 tensor to INT with scale + zero-point."""
        flat = tensor.float()
        qmin, qmax = 0, (2 ** self.bits) - 1

        vmin = flat.amin(dim=-1, keepdim=True)
        vmax = flat.amax(dim=-1, keepdim=True)
        scale = (vmax - vmin) / qmax
        scale = scale.clamp(min=1e-8)
        zero_point = (-vmin / scale).round().clamp(qmin, qmax)

        quantized = ((flat / scale) + zero_point).round().clamp(qmin, qmax)
        return quantized.to(torch.uint8), scale.half(), zero_point.half()

    def dequantize(self, quantized: Tensor, scale: Tensor, zero_point: Tensor) -> Tensor:
        """Restore FP16 from quantized representation."""
        return ((quantized.float() - zero_point.float()) * scale.float()).half()

    def update(self, layer_idx: int, key: Tensor, value: Tensor):
        """Add new KV entries with quantization."""
        k_q, k_s, k_z = self.quantize(key)
        v_q, v_s, v_z = self.quantize(value)

        if layer_idx not in self.cache:
            self.cache[layer_idx] = {
                "k_q": k_q, "k_s": k_s, "k_z": k_z,
                "v_q": v_q, "v_s": v_s, "v_z": v_z,
            }
        else:
            c = self.cache[layer_idx]
            c["k_q"] = torch.cat([c["k_q"], k_q], dim=2)
            c["k_s"] = torch.cat([c["k_s"], k_s], dim=2)
            c["k_z"] = torch.cat([c["k_z"], k_z], dim=2)
            c["v_q"] = torch.cat([c["v_q"], v_q], dim=2)
            c["v_s"] = torch.cat([c["v_s"], v_s], dim=2)
            c["v_z"] = torch.cat([c["v_z"], v_z], dim=2)

    def get(self, layer_idx: int) -> tuple[Tensor, Tensor]:
        """Retrieve dequantized KV cache."""
        c = self.cache[layer_idx]
        k = self.dequantize(c["k_q"], c["k_s"], c["k_z"])
        v = self.dequantize(c["v_q"], c["v_s"], c["v_z"])
        return k, v


# --- Ring Attention (for distributed long context) ---

def ring_attention_step(
    q_chunk: Tensor,       # Local query chunk [B, H, chunk_len, D]
    k_chunk: Tensor,       # Current KV chunk (rotates between GPUs)
    v_chunk: Tensor,
    running_max: Tensor,   # Running softmax denominator
    running_sum: Tensor,   # Running output accumulator
    causal_offset: int,    # Position offset for causal masking
) -> tuple[Tensor, Tensor, Tensor]:
    """One step of ring attention: process one KV chunk.

    Ring attention distributes sequence across GPUs.
    Each GPU holds a chunk of Q and rotates K,V in a ring.
    Total context = num_gpus * chunk_size.
    """
    scale = 1.0 / math.sqrt(q_chunk.shape[-1])
    attn_scores = torch.matmul(q_chunk, k_chunk.transpose(-2, -1)) * scale

    # Apply causal mask based on chunk positions
    chunk_len = q_chunk.shape[2]
    mask = torch.ones_like(attn_scores, dtype=torch.bool)
    for i in range(chunk_len):
        for j in range(k_chunk.shape[2]):
            if causal_offset + j > i:
                mask[:, :, i, j] = False
    attn_scores = attn_scores.masked_fill(~mask, float("-inf"))

    # Online softmax: update running statistics
    chunk_max = attn_scores.amax(dim=-1, keepdim=True)
    new_max = torch.maximum(running_max, chunk_max)

    # Rescale old accumulator
    correction = torch.exp(running_max - new_max)
    running_sum = running_sum * correction

    # Add new chunk contribution
    exp_scores = torch.exp(attn_scores - new_max)
    running_sum = running_sum + torch.matmul(exp_scores, v_chunk)

    return running_sum, new_max, correction
```

Long-context efficiency techniques:

| Technique | KV cache reduction | Quality | Used by |
|-----------|-------------------|---------|---------|
| **GQA (8 KV heads)** | 4x | Lossless | Llama 3, Qwen 2.5 |
| **Sliding window** | O(n*w) vs O(n^2) | Near-lossless | Mistral, Gemma 2 |
| **KV quantization (INT4)** | 4x | <0.5% loss | Many inference engines |
| **Ring attention** | Linear in GPUs | Lossless | Training 1M+ contexts |
| **MLA (Multi-head Latent)** | 10-20x | Near-lossless | DeepSeek V2/V3 |

Key patterns:
1. **Sliding window + sink tokens** — local attention window plus always-visible initial tokens captures most information
2. **GQA** — share KV heads across query groups; reduces cache proportionally with minimal quality loss
3. **KV-cache quantization** — INT4/INT8 compression of cached keys/values enables 4x longer contexts in same VRAM
4. **Ring attention** — distribute sequence across GPUs in a ring topology; each GPU processes local queries against rotating KV chunks
5. **Online softmax** — accumulate attention incrementally without materializing the full attention matrix'''
    ),
]
"""
