# HiveAI Upgrade Blueprint: Qwen 3 -> Qwen 3.5

## Status: WAITING FOR OPEN-WEIGHT MODELS (smaller sizes)

The 397B flagship is too large for our hardware (16GB VRAM).
We are waiting for: **Qwen3.5-9B** (dense) and/or **Qwen3.5-35B-A3B** (MoE).
Both exist in Alibaba's API but are NOT yet open-weight.

---

## Part 1: What Changed — Engineering Deep Dive

### 1.1 The Core Architecture Change

Qwen 3 is a standard transformer — every layer is identical softmax attention + dense MLP:

```
Every Layer: [RMSNorm -> Softmax Attention (GQA) -> RMSNorm -> Dense MLP]
```

Qwen 3.5 introduces a **hybrid decoder layer** that conditionally selects between two attention mechanisms:

```python
# Qwen3.5 layer selection — from modeling_qwen3_5.py
class Qwen3_5DecoderLayer:
    def __init__(self, config, layer_idx):
        self.layer_type = config.layer_types[layer_idx]

        if self.layer_type == "linear_attention":
            self.linear_attn = Qwen3_5GatedDeltaNet(config, layer_idx)  # NEW: O(n)
        elif self.layer_type == "full_attention":
            self.self_attn = Qwen3_5Attention(config, layer_idx)        # Standard: O(n^2)

        self.mlp = Qwen3_5MoEMLP(config)  # MoE replaces dense MLP
```

The `layer_types` array uses a 3:1 interleaving pattern:
```
15 x [linear, linear, linear, full_attention]  = 60 layers total
```

75% linear attention / 25% full attention = 8.6-19x throughput improvement.

### 1.2 Gated Delta Network — The Linear Attention Mechanism

Instead of computing an n x n attention matrix (O(n^2)), the Gated DeltaNet maintains a **fixed-size recurrent state matrix** S of shape (num_heads, head_dim, head_dim):

```
Standard Attention:  y = softmax(QK^T / sqrt(d)) * V    # O(n^2)

Gated DeltaNet:
    S_t = alpha_t * S_{t-1} + beta_t * (v_t - S_{t-1} * k_t) * k_t^T
    y_t = S_t * q_t                                      # O(1) per token

Where:
    alpha_t = exp(A_log + softplus(W_alpha(x_t)))   # decay gate (how fast to forget)
    beta_t  = sigmoid(W_beta(x_t))                  # update gate (how much to learn)
```

Key insight: The state S is a learned associative memory. The delta `(v_t - S_{t-1} * k_t)` is the error between what the state predicts and the actual value. This Hebbian update teaches the state to map keys to values.

**Two processing modes:**
- **Chunk-based** (training/prefill): Parallel processing within chunks, serial across chunks
- **Recurrent** (generation): Token-by-token state updates, constant memory

**Trade-off:** Linear attention compresses all past context into a fixed-size state (information bottleneck). The 3:1 hybrid ratio mitigates this — every 4th layer has full softmax attention that can directly reference any position.

### 1.3 MoE Changes

| | Qwen 3 (235B-A22B) | Qwen 3.5 (397B-A17B) |
|---|---|---|
| Total experts | 128 | **512** (4x more) |
| Active per token | 8 | **10 routed + 1 shared = 11** |
| Expert FFN size | 1,536 | **1,024** (smaller) |
| Shared expert | None | **1,024 intermediate** |
| Activation ratio | 6.25% | **2.1%** (ultra-sparse) |
| Active params | 22B | **17B** (cheaper to run) |

The shared expert processes EVERY token, capturing universal features. This is a "safety net" that prevents routing collapse.

### 1.4 Config-Level Differences

New parameters in Qwen3.5 that don't exist in Qwen3:

```python
# Linear attention (Gated DeltaNet)
linear_conv_kernel_dim = 4        # Depthwise conv kernel
linear_key_head_dim = 128         # Key head dim for linear attn
linear_value_head_dim = 128       # Value head dim for linear attn
linear_num_key_heads = 16         # QK heads in linear layers
linear_num_value_heads = 64       # V heads in linear layers

# Architecture control
layer_types = [...]               # "linear_attention" or "full_attention" per layer
attn_output_gate = True           # Gated attention output (prevents attention sinks)
partial_rotary_factor = 0.25      # Only 25% of dims get RoPE (rest position-agnostic)

# Multimodal RoPE
mrope_interleaved = True          # Multi-resolution position encoding
mrope_section = [11, 11, 10]      # [temporal, height, width] positions

# MoE
shared_expert_intermediate_size = 1024  # Dense expert runs on every token
```

### 1.5 Tokenizer Changes

| | Qwen 3 | Qwen 3.5 |
|---|---|---|
| Vocabulary | 151,936 | **248,320** (+63%) |
| Languages | 119 | **201** |
| Vision tokens | None | image, video, vision_start, vision_end |
| Context | 32K-128K | **256K** (extendable to 1M) |
| rope_theta | 1,000,000 | **10,000,000** |

### 1.6 Training Stability Innovations

1. **Zero-Centered RMSNorm**: `output = (x - mean(x)) * scale / RMS(x - mean(x))` — prevents unbounded growth
2. **Attention Output Gating**: `output = Attn(Q,K,V) * sigmoid(X @ W_gate) @ W_o` — eliminates attention sinks
3. **Fair Router Init**: Uniform initialization prevents expert routing collapse
4. **FP8 Training**: ~50% activation memory reduction, >10% speedup

### 1.7 Engineering Patterns to Learn

These are the reusable patterns we should internalize:

1. **Configurable Layer Types**: Use `layer_types[]` array to mix mechanisms. Single codebase, flexible architecture.
2. **Linear Attention as Drop-In**: Same input/output interface as softmax attention. Swap at the module level.
3. **Ultra-Sparse MoE + Shared Expert**: More experts, smaller each, shared expert for stability.
4. **Dual-Mode Processing**: Chunk-based for training, recurrent for generation.
5. **Stability First**: Zero-centered norms, output gating, fair init BEFORE scaling up.
6. **Vocabulary-First Multilingual**: Expand tokenizer before training.

---

## Part 2: HiveAI Codebase Audit — Every Qwen3 Touchpoint

### 2.1 Configuration Files (CRITICAL)

| File | Lines | Current | Change To | Risk |
|------|-------|---------|-----------|------|
| `.env` | 19-20 | `qwen3:32b`, `qwen3:14b` | `qwen3.5:Xb` equivalents | HIGH |
| `.env.example` | 103, 134-143 | qwen3 model table | qwen3.5 equivalents | LOW |
| `hiveai/config.py` | 34, 42-43 | `qwen3:14b`, `qwen3:8b` defaults | qwen3.5 defaults | HIGH |

### 2.2 Inference (Model Calls)

| File | Lines | What | Risk |
|------|-------|------|------|
| `hiveai/llm/client.py` | 231 | `"think": False` in stream_llm_call | HIGH — verify Qwen3.5 parameter |
| `scripts/brain_mine.py` | 506, 551 | `"think": False/True` | HIGH — verify compatibility |
| `scripts/run_eval.py` | 78 | `"think": False` in eval | HIGH — verify compatibility |
| `scripts/brain_mine.py` | 643-645 | Log messages ("qwen3:14b") | LOW — cosmetic |

### 2.3 LoRA Training (CRITICAL PATH)

| File | Lines | What | Risk |
|------|-------|------|------|
| `hiveai/lora/trainer.py` | 28-37 | `OLLAMA_TO_HF` model mapping | CRITICAL — need Unsloth Qwen3.5 models |
| `hiveai/lora/trainer.py` | 37 | `DEFAULT_BASE_MODEL` | CRITICAL |
| `hiveai/lora/trainer.py` | 42-52 | `LORA_CONFIG.target_modules` | HIGH — verify projection names match |
| `hiveai/lora/trainer.py` | 54-68 | `TRAINING_CONFIG` | MEDIUM — may need hyperparameter tuning |
| `hiveai/lora/trainer.py` | 71 | `MAX_SEQ_LENGTH = 2048` | MEDIUM — Qwen3.5 has 256K context |
| `hiveai/lora/trainer.py` | 73-82 | Alpaca prompt template | MEDIUM — check if Qwen3.5 uses different template |
| `hiveai/lora/benchmark.py` | 170-175 | Model loading | LOW — inherits from config |

### 2.4 Existing Trained Artifacts (DO NOT MODIFY)

| File | Content | Action |
|------|---------|--------|
| `loras/v1/adapter_config.json` | `Qwen3ForCausalLM`, `unsloth/qwen3-14b-bnb-4bit` | ARCHIVE — v1 stays on Qwen3 |
| `loras/v1/adapter_model.safetensors` | 257MB trained adapter | ARCHIVE — incompatible with Qwen3.5 |
| `loras/v1/training_meta.json` | Training metadata | ARCHIVE |
| `loras/training_data/v1.jsonl` | 1104 training pairs | REUSE — pairs are model-agnostic |

### 2.5 Documentation (LOW PRIORITY)

| File | Lines | Content |
|------|-------|---------|
| `README.md` | 43, 45, 78-90, 148-177, 228-229, 285, 408-409, 626, 645 | Qwen3 references |
| `BLUEPRINT.md` | 14, 29, 48-49, 57, 74, 94, 138, 181, 213, 228, 248, 265 | Qwen3 references |
| `scripts/brain_mine.py` | Docstrings throughout | Phase descriptions |
| `scripts/run_eval.py` | 10-12 | Docstring |
| `scripts/run_all_phases.py` | 46-53 | Phase descriptions |

---

## Part 3: The Migration Plan

### BLOCKING DEPENDENCIES (Must resolve before starting)

1. **Ollama must have Qwen3.5 models for local pull** (not just cloud tags)
   - Check: `ollama pull qwen3.5:9b` or `qwen3.5:14b`
   - Status: NOT YET AVAILABLE (only cloud tags exist as of Feb 24, 2026)

2. **Unsloth must support Qwen3.5 for LoRA training**
   - Check: `unsloth/Qwen3.5-*-bnb-4bit` on HuggingFace
   - Status: NOT YET AVAILABLE (inference only as of Feb 24, 2026)

3. **Open-weight smaller models must be released**
   - Need: Qwen3.5-9B or Qwen3.5-35B-A3B or Qwen3.5-27B
   - Status: API-only, expected within weeks

### Phase 0: Preparation (NOW — while waiting for blockers)

- [x] Study Qwen3.5 architecture (done)
- [x] Audit all Qwen3 touchpoints (done)
- [x] Complete LoRA v1 training on Qwen3 (done — loss 0.4312)
- [ ] Benchmark LoRA v1 against baseline
- [ ] Continue generating distillation pairs (target 5,000+)
- [ ] Export LoRA v1 to GGUF and benchmark
- [ ] Archive v1 artifacts in `loras/v1-qwen3/` (rename directory)

### Phase 1: Configuration Layer (30 min, LOW RISK)

Update model name strings. No logic changes.

```bash
# Files to update:
.env                          # Lines 19-20: model names
.env.example                  # Lines 103, 134-143: documentation
hiveai/config.py              # Lines 34, 42-43: defaults
```

### Phase 2: LoRA Training Infrastructure (2-4 hours, HIGH RISK)

This is the critical path. Must verify before proceeding:

```python
# trainer.py changes needed:

# 1. Model mapping (lines 28-37)
OLLAMA_TO_HF = {
    "qwen3.5:9b": "unsloth/Qwen3.5-9B-bnb-4bit",       # or Dense
    "qwen3.5:14b": "unsloth/Qwen3.5-14B-bnb-4bit",     # if released
    "qwen3.5:27b": "unsloth/Qwen3.5-27B-bnb-4bit",     # Dense
    "qwen3.5:35b-a3b": "unsloth/Qwen3.5-35B-A3B-bnb-4bit",  # MoE
    # KEEP old entries for backward compatibility
    "qwen3:14b": "unsloth/Qwen3-14B-bnb-4bit",
    "qwen3:32b": "unsloth/Qwen3-32B-bnb-4bit",
}

# 2. LoRA target modules — VERIFY THESE MATCH QWEN3.5
# For dense models: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
#   (LIKELY THE SAME — standard transformer projections)
# For hybrid models: linear attention layers have DIFFERENT projections
#   May need: q_proj, k_proj, v_proj, gate_proj, beta_proj, etc.
# CRITICAL: Must inspect actual Qwen3.5 model to confirm

# 3. Training config
MAX_SEQ_LENGTH = 4096  # Can increase from 2048 — Qwen3.5 has 256K context
# (4096 is conservative for 16GB VRAM, test higher if VRAM allows)

# 4. Prompt template — check Qwen3.5 tokenizer_config.json
# The Alpaca template may need updating to Qwen3.5's chat template
```

### Phase 3: Inference & Thinking Mode (1-2 hours, MEDIUM RISK)

```python
# Verify these work with Qwen3.5:
# client.py line 231: "think": False
# brain_mine.py line 506: "think": False
# brain_mine.py line 551: "think": True
# run_eval.py line 78: "think": False

# Test plan:
# 1. Start Ollama with Qwen3.5 model
# 2. Test: curl -X POST http://localhost:11434/api/chat \
#      -d '{"model":"qwen3.5:9b","messages":[{"role":"user","content":"Hello"}],"think":false}'
# 3. Verify response format matches Qwen3 format
# 4. Test streaming: same call with "stream": true
```

### Phase 4: Re-Export Training Data (1 hour, LOW RISK)

Our distillation pairs are instruction/response format — **model-agnostic**. We don't need to regenerate them.

```bash
# Re-export with updated tokenizer/template format
python -m hiveai.lora.exporter --version v2 --format qwen3.5
```

### Phase 5: Train LoRA v2 on Qwen3.5 (16-24 hours GPU time)

```bash
# Train new adapter on new base model
# Use ALL accumulated pairs (2,268+ and growing)
python -m hiveai.lora.trainer \
    --data loras/training_data/v2.jsonl \
    --output loras/v2-qwen35/ \
    --version v2.0 \
    --base-model "unsloth/Qwen3.5-9B-bnb-4bit"
```

### Phase 6: Benchmark & Validate (4-6 hours)

```bash
# Run eval harness on both models
python scripts/run_eval.py --model qwen3.5:9b                    # Base Qwen3.5
python scripts/run_eval.py --model hiveai-v2                       # LoRA v2 on Qwen3.5
python scripts/run_eval.py --compare evals/qwen3-14b_baseline.json evals/qwen35-9b_lora.json

# Also compare against our Qwen3 LoRA v1
python scripts/run_eval.py --compare evals/qwen3-14b_lora_v1.json evals/qwen35-9b_lora.json
```

### Phase 7: Update Documentation (30 min)

Update README.md, BLUEPRINT.md, docstrings with new model references.

---

## Part 4: What We DON'T Change (Preserve All Work)

| Asset | Action | Why |
|-------|--------|-----|
| `loras/v1/` directory | **RENAME to `loras/v1-qwen3/`** | Preserve Qwen3 adapter for comparison |
| `loras/training_data/v1.jsonl` | **KEEP** | Training data is model-agnostic |
| `scripts/claude_distill.py` | **KEEP** | Distillation pairs work on any model |
| All DB TrainingPairs | **KEEP** | `lora_version` column tracks which pairs trained which adapter |
| `evals/` reports | **KEEP** | Historical baseline for comparison |
| Brain-mined Golden Books | **KEEP** | Content is model-agnostic knowledge |

---

## Part 5: Hardware Planning

### Model Sizing for RTX 4070 Ti SUPER (16GB VRAM)

| Qwen3.5 Model | Type | FP16 Size | 4-bit Size | Fits 16GB? |
|------|------|-----------|------------|-----------|
| 9B (dense) | Dense | ~18GB | ~5GB | YES easily |
| 27B (dense) | Dense | ~54GB | ~14GB | YES tight |
| 35B-A3B (MoE) | MoE | ~70GB | ~18GB total, ~6-8GB active | MAYBE with offloading |
| 397B-A17B | MoE | ~800GB | ~214GB | NO |

### Recommended Configuration (when available)

```env
# Fast model: Qwen3.5-9B (dense, ~5GB at 4-bit)
OLLAMA_MODEL_FAST=qwen3.5:9b

# Reasoning model: Qwen3.5-27B (dense, ~14GB at 4-bit)
# OR: Qwen3.5-35B-A3B (MoE, ~6-8GB active)
OLLAMA_MODEL_REASONING=qwen3.5:27b

# Training: Qwen3.5-9B (same as fast, for LoRA training)
# This fits in 16GB VRAM with 4-bit quantization + LoRA overhead
```

### VRAM Budget

```
Qwen3.5-9B 4-bit:     ~5GB
LoRA adapter (r=16):   ~0.5GB
Training overhead:     ~4GB (gradients, optimizer states)
---
Total training:        ~9.5GB (fits 16GB with headroom!)

Inference (via Ollama):
  Fast (9B):           ~5GB
  Reasoning (27B):     ~14GB
  Embedding (bge-m3):  ~7GB
  WARNING: Can't run embedding + reasoning simultaneously (21GB > 16GB)
```

---

## Part 6: Risk Mitigation

### Risk 1: Unsloth doesn't support Qwen3.5 LoRA
**Mitigation**: Use HuggingFace PEFT + bitsandbytes directly. Slower training (~2x) but functional:
```python
from peft import get_peft_model, LoraConfig
from transformers import AutoModelForCausalLM
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-9B", load_in_4bit=True)
peft_model = get_peft_model(model, LoraConfig(r=16, target_modules=[...]))
```

### Risk 2: Ollama doesn't support Qwen3.5 locally
**Mitigation**: Use llama.cpp directly with GGUF download from HuggingFace:
```bash
# Download GGUF from HuggingFace
huggingface-cli download Qwen/Qwen3.5-9B-GGUF qwen3.5-9b-q4_k_m.gguf
# Run with llama.cpp server
llama-server -m qwen3.5-9b-q4_k_m.gguf -c 4096 --port 11434
```

### Risk 3: LoRA target_modules differ for hybrid attention
**Mitigation**: Only apply LoRA to modules that exist in BOTH linear and full attention layers (q_proj, v_proj, gate_proj, up_proj, down_proj). Skip linear-attention-specific modules initially.

### Risk 4: Thinking mode parameter changes
**Mitigation**: Make think parameter configurable in .env:
```python
OLLAMA_THINK_PARAM = os.environ.get("OLLAMA_THINK_PARAM", "think")
```

### Risk 5: Training data format incompatibility
**Mitigation**: Our pairs use a simple (instruction, response) format that's independent of the model's chat template. The exporter converts to the model-specific format at export time.

---

## Part 7: Architecture Learning — What We Now Know

### How to Upgrade a Model Architecture (Alibaba's Pattern)

1. **Define the hybrid mechanism first**: Create a new attention variant (Gated DeltaNet) that has the same input/output interface as the existing one.

2. **Make it configurable at the layer level**: Use a `layer_types` array so each layer can independently choose its mechanism. This enables experimentation with different ratios.

3. **Interleave for best of both worlds**: The 3:1 pattern (75% linear, 25% full) was empirically validated. Linear handles bulk processing efficiently; full attention handles precise long-range dependencies.

4. **Solve stability BEFORE scaling**: Zero-centered RMSNorm, attention output gating, fair router init, FP8 monitoring — all solved at small scale, then applied to the full model.

5. **Expand vocabulary before training**: The tokenizer expansion (152K -> 248K) happens BEFORE pre-training starts. More tokens = better compression = cheaper inference.

6. **Shared expert for MoE stability**: Adding one dense expert that processes every token prevents catastrophic routing collapse during training.

7. **Dual-mode cache management**: The hybrid cache stores constant-size state for linear layers and growing KV cache for full attention layers.

### What This Means for Future Upgrades

When Qwen 4, Llama 5, or any next-gen model drops, we now know the patterns:
- Check if it's a **new architecture** (hybrid, state-space, etc.) vs **same architecture + better training**
- If new architecture: check `layer_types`, `target_modules`, cache format, tokenizer
- If same architecture: usually just config changes + new model weights
- **Our training data is always preserved** — pairs are model-agnostic
- **LoRA adapters are always model-specific** — must retrain

---

## Monitoring Checklist (Weekly)

```bash
# Check Ollama for Qwen3.5 local models
ollama list | grep qwen3.5

# Check HuggingFace for open-weight releases
# https://huggingface.co/collections/Qwen/qwen35

# Check Unsloth for LoRA support
# https://github.com/unslothai/unsloth/releases

# Check pip for transformers updates
pip index versions transformers | head -5
```

---

## Timeline Estimate

| Phase | When | Duration | Depends On |
|-------|------|----------|------------|
| 0: Preparation | NOW | Ongoing | Nothing |
| 1: Config update | When models available | 30 min | Ollama Qwen3.5 |
| 2: Training infra | When models available | 2-4 hours | Unsloth Qwen3.5 |
| 3: Inference test | When models available | 1-2 hours | Ollama Qwen3.5 |
| 4: Re-export data | After Phase 2 | 1 hour | Phase 2 |
| 5: Train LoRA v2 | After Phase 4 | 16-24 hours | Phase 4 |
| 6: Benchmark | After Phase 5 | 4-6 hours | Phase 5 |
| 7: Documentation | After Phase 6 | 30 min | Phase 6 |
| **Total hands-on** | | **~10 hours** | |
| **Total wall clock** | | **~2-3 days** | |

---

*Generated: February 24, 2026*
*HiveAI Knowledge Refinery — Qwen 3.5 Upgrade Blueprint v1.0*
