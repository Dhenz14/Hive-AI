"""Speculative decoding and inference optimization — draft-verify, medusa heads, lookahead."""

PAIRS = [
    (
        "ai/speculative-decoding",
        "Show speculative decoding for LLM inference: draft model + verification, acceptance criteria, and speedup analysis.",
        '''Speculative decoding — faster LLM inference with draft+verify:

```python
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer


class SpeculativeDecoder:
    """Speculative decoding: use small draft model to propose tokens,
    large target model to verify in parallel.

    Key insight: verifying K tokens in parallel costs ~same as generating 1.
    If draft model matches target often, we get K tokens per forward pass.

    Expected speedup: ~2-3x for well-matched draft/target pairs.
    """

    def __init__(
        self,
        target_model_name: str = "Qwen/Qwen2.5-72B-Instruct",
        draft_model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
        num_speculative_tokens: int = 5,
    ):
        self.target = AutoModelForCausalLM.from_pretrained(
            target_model_name, torch_dtype=torch.bfloat16, device_map="auto"
        )
        self.draft = AutoModelForCausalLM.from_pretrained(
            draft_model_name, torch_dtype=torch.bfloat16, device_map="auto"
        )
        self.tokenizer = AutoTokenizer.from_pretrained(target_model_name)
        self.K = num_speculative_tokens

    @torch.no_grad()
    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        input_ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"].to(self.target.device)
        generated = input_ids.clone()

        tokens_generated = 0
        draft_accepts = 0
        total_draft = 0

        while tokens_generated < max_tokens:
            # Step 1: Draft model generates K speculative tokens
            draft_ids = generated.clone()
            draft_probs = []

            for _ in range(self.K):
                draft_out = self.draft(draft_ids)
                draft_logits = draft_out.logits[:, -1]

                if temperature > 0:
                    probs = F.softmax(draft_logits / temperature, dim=-1)
                    next_token = torch.multinomial(probs, 1)
                else:
                    probs = F.softmax(draft_logits, dim=-1)
                    next_token = draft_logits.argmax(dim=-1, keepdim=True)

                draft_probs.append(probs)
                draft_ids = torch.cat([draft_ids, next_token], dim=-1)

            speculative_tokens = draft_ids[:, generated.shape[1]:]  # [1, K]

            # Step 2: Target model verifies all K tokens in ONE forward pass
            candidate = torch.cat([generated, speculative_tokens], dim=-1)
            target_out = self.target(candidate)
            target_logits = target_out.logits[:, generated.shape[1]-1:-1]  # K+1 positions

            # Step 3: Accept/reject each speculative token
            num_accepted = 0
            for i in range(self.K):
                if temperature > 0:
                    target_probs = F.softmax(target_logits[:, i] / temperature, dim=-1)
                    draft_prob = draft_probs[i]
                    token = speculative_tokens[:, i]

                    # Acceptance criterion: p_target(x) / p_draft(x) >= uniform(0,1)
                    p_target = target_probs[0, token[0]].item()
                    p_draft = draft_prob[0, token[0]].item()
                    acceptance_ratio = min(1.0, p_target / max(p_draft, 1e-10))

                    if torch.rand(1).item() < acceptance_ratio:
                        num_accepted += 1
                    else:
                        # Reject: sample from adjusted distribution
                        adjusted = F.relu(target_probs - draft_prob)
                        adjusted = adjusted / adjusted.sum()
                        corrected_token = torch.multinomial(adjusted, 1)
                        generated = torch.cat([generated, speculative_tokens[:, :i], corrected_token], dim=-1)
                        break
                else:
                    # Greedy: accept if target agrees
                    target_token = target_logits[:, i].argmax(dim=-1)
                    if target_token == speculative_tokens[:, i]:
                        num_accepted += 1
                    else:
                        generated = torch.cat([generated, speculative_tokens[:, :i], target_token.unsqueeze(-1)], dim=-1)
                        break
            else:
                # All K accepted — also add the (K+1)th token from target
                bonus_token = target_logits[:, -1].argmax(dim=-1, keepdim=True)
                generated = torch.cat([generated, speculative_tokens, bonus_token], dim=-1)
                num_accepted += 1

            if num_accepted == 0 and i == 0:
                # First token rejected, use target's prediction
                pass

            tokens_generated += num_accepted
            draft_accepts += num_accepted
            total_draft += self.K

            # Check for EOS
            if self.tokenizer.eos_token_id in generated[0, input_ids.shape[1]:]:
                break

        acceptance_rate = draft_accepts / max(total_draft, 1)
        print(f"Acceptance rate: {acceptance_rate:.1%}, Speedup: ~{1 + acceptance_rate * (self.K - 1):.1f}x")

        return self.tokenizer.decode(generated[0, input_ids.shape[1]:], skip_special_tokens=True)


# === Medusa Heads (self-speculative) ===

class MedusaModel(torch.nn.Module):
    """Medusa: multiple prediction heads on the same model.

    Instead of a separate draft model, add extra "heads" to predict
    tokens 2, 3, 4, ... positions ahead simultaneously.
    No separate draft model needed.
    """

    def __init__(self, base_model: torch.nn.Module, vocab_size: int,
                 hidden_dim: int, num_heads: int = 4):
        super().__init__()
        self.base = base_model
        self.num_heads = num_heads

        # Medusa heads: predict future tokens from current hidden state
        self.medusa_heads = torch.nn.ModuleList([
            torch.nn.Sequential(
                torch.nn.Linear(hidden_dim, hidden_dim),
                torch.nn.SiLU(),
                torch.nn.Linear(hidden_dim, vocab_size),
            )
            for _ in range(num_heads)
        ])

    def forward(self, input_ids: torch.Tensor):
        # Base model forward
        outputs = self.base(input_ids, output_hidden_states=True)
        hidden = outputs.hidden_states[-1]  # Last hidden state

        # Standard next-token prediction
        base_logits = outputs.logits

        # Medusa predictions: tokens 2, 3, ..., K+1 positions ahead
        medusa_logits = [head(hidden) for head in self.medusa_heads]

        return base_logits, medusa_logits

    def generate_with_tree_attention(self, input_ids: torch.Tensor,
                                      max_tokens: int = 256) -> torch.Tensor:
        """Generate using tree-structured speculation.

        Instead of a single draft sequence, consider a tree of
        candidate continuations from all Medusa heads.
        """
        generated = input_ids.clone()

        for _ in range(max_tokens):
            base_logits, medusa_logits = self(generated)

            # Get top-k candidates from each head
            candidates = []
            base_token = base_logits[:, -1].argmax(dim=-1)
            candidates.append(base_token)

            for head_logits in medusa_logits:
                head_token = head_logits[:, -1].argmax(dim=-1)
                candidates.append(head_token)

            # Verify candidates using tree attention
            # (simplified: in practice, verify all candidates in one pass)
            generated = torch.cat([generated, base_token.unsqueeze(-1)], dim=-1)

            if base_token.item() == self.base.config.eos_token_id:
                break

        return generated
```

Speculative decoding methods:

| Method | Draft model | Speedup | Accuracy | Complexity |
|--------|-----------|---------|----------|-----------|
| **Draft+Verify** | Separate small model | 2-3x | Exact match | Two models in VRAM |
| **Medusa** | Same model + heads | 2-3x | Near-exact | Extra heads (~5% params) |
| **Eagle** | Same model + draft head | 2.5-3.5x | Exact | Autoregressive draft head |
| **Lookahead** | Jacobi iteration | 1.5-2x | Exact | No extra model |
| **Self-speculative** | Early exit | 1.5-2x | Near-exact | Layer skipping |

Key patterns:
1. **Draft+Verify** — small model proposes K tokens; large model verifies in one parallel pass; mathematically lossless
2. **Acceptance criterion** — `min(1, p_target/p_draft)` ensures the output distribution exactly matches the target model
3. **Medusa heads** — predict future tokens from current hidden state; no separate model needed
4. **Tree attention** — consider multiple candidate continuations simultaneously; accept longest matching path
5. **Acceptance rate** — higher acceptance = more speedup; well-matched draft/target pairs achieve 70-90% acceptance'''
    ),
    (
        "ai/quantization-advanced",
        "Show advanced LLM quantization: GPTQ, AWQ, GGUF formats, and calibration-based quantization.",
        '''Advanced LLM quantization for deployment:

```python
import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset


# === GPTQ Quantization ===

def quantize_gptq(
    model_name: str = "Qwen/Qwen2.5-7B",
    bits: int = 4,
    group_size: int = 128,
    calibration_samples: int = 128,
) -> str:
    """GPTQ: layer-wise quantization with calibration data.

    Uses second-order information (Hessian) to find optimal
    quantization that minimizes output error.
    """
    from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

    quantize_config = BaseQuantizeConfig(
        bits=bits,
        group_size=group_size,
        desc_act=True,          # Activation-order quantization (better quality)
        sym=True,               # Symmetric quantization
        true_sequential=True,   # Process layers in order
    )

    # Load model
    model = AutoGPTQForCausalLM.from_pretrained(
        model_name,
        quantize_config=quantize_config,
        torch_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Calibration data (representative samples)
    calibration_data = load_calibration_data(tokenizer, calibration_samples)

    # Quantize (layer by layer, using Hessian to minimize error)
    model.quantize(calibration_data)

    # Save quantized model
    output_dir = f"{model_name.split('/')[-1]}-GPTQ-{bits}bit"
    model.save_quantized(output_dir)
    tokenizer.save_pretrained(output_dir)

    return output_dir


# === AWQ Quantization ===

def quantize_awq(
    model_name: str = "Qwen/Qwen2.5-7B",
    bits: int = 4,
    group_size: int = 128,
) -> str:
    """AWQ: Activation-aware Weight Quantization.

    Key insight: not all weights are equally important.
    Weights connected to large activations matter more.
    Scale weights to protect important channels before quantizing.
    """
    from awq import AutoAWQForCausalLM

    model = AutoAWQForCausalLM.from_pretrained(model_name, torch_dtype=torch.float16)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    quant_config = {
        "zero_point": True,
        "q_group_size": group_size,
        "w_bit": bits,
        "version": "GEMM",  # GEMM kernel for inference
    }

    # Quantize with activation awareness
    model.quantize(tokenizer, quant_config=quant_config)

    output_dir = f"{model_name.split('/')[-1]}-AWQ-{bits}bit"
    model.save_quantized(output_dir)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def load_calibration_data(tokenizer, num_samples: int = 128) -> list:
    """Load calibration dataset for quantization."""
    dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="train")
    samples = []

    for i, sample in enumerate(dataset):
        if i >= num_samples:
            break
        text = sample["text"]
        if len(text) < 100:
            continue
        tokens = tokenizer(text, return_tensors="pt", max_length=2048, truncation=True)
        samples.append(tokens["input_ids"])

    return samples


# === GGUF Export for llama.cpp ===

def export_to_gguf(
    model_path: str,
    output_path: str,
    quantization: str = "Q4_K_M",
):
    """Export to GGUF format for llama.cpp inference.

    GGUF quant types (quality vs size tradeoff):
    - Q8_0: ~8 bits, best quality, largest
    - Q6_K: ~6.5 bits, great quality
    - Q5_K_M: ~5.5 bits, good quality
    - Q4_K_M: ~4.5 bits, recommended default
    - Q4_K_S: ~4.5 bits, slightly smaller
    - Q3_K_M: ~3.5 bits, acceptable quality
    - Q2_K: ~2.5 bits, significant quality loss
    - IQ4_XS: ~4 bits, importance matrix (best at 4-bit)
    """
    import subprocess

    # Step 1: Convert HF model to GGUF F16
    subprocess.run([
        "python", "llama.cpp/convert_hf_to_gguf.py",
        model_path,
        "--outfile", output_path.replace(".gguf", "-f16.gguf"),
        "--outtype", "f16",
    ], check=True)

    # Step 2: Quantize to target format
    subprocess.run([
        "llama.cpp/build/bin/llama-quantize",
        output_path.replace(".gguf", "-f16.gguf"),
        output_path,
        quantization,
    ], check=True)


# === Quantization-Aware Training (QAT) ===

class QuantizedLinear(nn.Module):
    """Simulated quantization for QAT (straight-through estimator)."""

    def __init__(self, in_features: int, out_features: int,
                 bits: int = 4, group_size: int = 128):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(out_features, in_features))
        self.bias = nn.Parameter(torch.zeros(out_features))
        self.bits = bits
        self.group_size = group_size

    def quantize_weight(self, weight: torch.Tensor) -> torch.Tensor:
        """Fake quantization: quantize and dequantize (STE for gradients)."""
        qmin = -(2 ** (self.bits - 1))
        qmax = 2 ** (self.bits - 1) - 1

        # Per-group quantization
        groups = weight.reshape(-1, self.group_size)
        scales = groups.abs().amax(dim=-1, keepdim=True) / qmax
        scales = scales.clamp(min=1e-8)

        # Quantize
        quantized = (groups / scales).round().clamp(qmin, qmax)

        # Dequantize (straight-through: gradients pass through round())
        dequantized = quantized * scales
        return dequantized.reshape_as(weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.training:
            # STE: forward uses quantized weights, backward uses FP weights
            w_quant = self.weight + (self.quantize_weight(self.weight) - self.weight).detach()
        else:
            w_quant = self.quantize_weight(self.weight)
        return F.linear(x, w_quant, self.bias)
```

Quantization format comparison:

| Format | Ecosystem | Speed | Quality at 4-bit | GPU support |
|--------|-----------|-------|-------------------|-------------|
| **GPTQ** | HuggingFace, vLLM | Fast (GPU) | Great | CUDA |
| **AWQ** | vLLM, TGI | Fastest (GPU) | Great | CUDA |
| **GGUF** | llama.cpp, Ollama | Good (CPU+GPU) | Good | Metal, CUDA, CPU |
| **bitsandbytes** | HuggingFace | Moderate | Good | CUDA |
| **EXL2** | ExLlamaV2 | Very fast | Best | CUDA |

Key patterns:
1. **GPTQ** — Hessian-based layer-wise quantization; calibration data minimizes output error
2. **AWQ** — identifies important weight channels via activation magnitudes; scales before quantizing
3. **GGUF** — portable format for llama.cpp; Q4_K_M is the recommended default (quality/size sweet spot)
4. **Group quantization** — quantize in groups of 128 weights sharing scale/zero-point; better than per-tensor
5. **QAT** — simulate quantization during training with straight-through estimator; model adapts to quantization noise'''
    ),
]
"""
