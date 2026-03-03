# Lessons Learned: v3 Training on Pruned Qwen3.5-35B-A3B

## Summary

v3 LoRA training ran for 34.1 hours (299 steps, final loss 1.16) on a Qwen3.5-35B-A3B model pruned to 128/256 experts per layer using L2-norm gate weight pruning. The training dynamics were healthy (loss curve, gradient norms, optimizer state all normal), but the resulting model produces garbage for coding tasks. The root cause is the pruned base model itself, not the LoRA adapter.

## What Went Wrong

### 1. L2-Norm Pruning Removed Coding-Essential Experts

**The mistake:** `prune_experts.py` was run with its default mode (L2-norm of gate weights) instead of passing `--activation-aware`.

**Why this matters:**
- L2-norm of a gate row measures how strongly the router *can* select that expert
- It does NOT measure how *often* the router actually selects that expert for coding tokens
- Many coding-essential experts had low gate weight norms but high activation frequency
- These experts were pruned, destroying the model's coding ability while preserving its ability to handle trivial tasks

**Evidence:**
- `pruning_meta.json`: `activation_aware: false`, `routing_capacity_retained: 0.5497`
- Base model (no LoRA) answers "2+2 is 4" correctly but produces repetitive garbage for coding prompts
- The `--activation-aware` flag already existed in the script but wasn't used

### 2. No Pre-Training Validation Gate

**The mistake:** We committed to a 34-hour training run without first verifying the pruned base model could generate coherent code.

**What should have happened:**
1. After pruning, run `serve_model.py --test` to verify coherent generation
2. If the base produces garbage, stop immediately and fix the pruning
3. Only commit to the long training run after the base passes validation

**Time wasted:** 34.1 hours of GPU time

### 3. BnB 4-Bit + DoRA Merge Corruption

**The mistake:** Initial inference testing used `merge_and_unload()` to merge the LoRA back into the base weights. This corrupted the model because:
- BnB 4-bit quantized weights are stored in NF4 format
- DoRA adds magnitude vectors on top of LoRA
- Merging back into quantized weights introduces rounding/precision errors
- The merged model produced repetitive garbage even when the adapter was fine

**Fix:** Keep LoRA as an active PEFT adapter during inference (no merge). This is slower (~0.4 tok/s vs ~2.1 tok/s) but correct.

### 4. GGUF/llama.cpp Incompatibility

**The issue:** llama.cpp cannot currently run Qwen3.5-35B-A3B correctly due to:
- mxfp4 tensor type (80 expert weight tensors) has known bugs — Unsloth is retiring this format
- DeltaNet SSM kernels (30/40 layers use Gated Delta Networks) are missing from the CUDA backend
- This causes CPU fallback and corrupted hidden states

**Workaround:** Use Python-based inference (`scripts/serve_model.py`) with BnB 4-bit quantization instead of llama-server + GGUF.

## What Went Right

### 1. Training Dynamics Were Healthy
- Loss: 2.04 → 1.07 (by step 100), plateau at 1.03-1.16
- Gradient norms: stable, 0.18 → 0.05
- No NaN values, no OOM crashes
- VRAM: peaked at ~16GB as predicted (11.3GB model + training overhead)
- Conclusion: the SFT process itself was correct; the base model was the problem

### 2. Training Data Is Fully Reusable
- `loras/training_data/v3.jsonl` — 2,385 pairs at quality >= 0.70
- ChatML format, curriculum-sorted, NEFTune-compatible
- Can be reused directly for v3.5 training on a properly pruned base

### 3. Monkey-Patch Infrastructure Works
- `patch_experts_for_quantization()` correctly unfuses MoE experts from 3D tensors to per-expert nn.Linear
- `disable_expert_fusing_converter()` prevents transformers from re-fusing during load
- BnB 4-bit quantization + LoRA attachment works correctly
- This infrastructure is validated and can be reused for v3.5

### 4. Python Inference Server Works
- `scripts/serve_model.py` provides OpenAI-compatible `/v1/chat/completions`
- Compatible with `scripts/run_eval.py --base-url`
- Generation with active PEFT adapter produces correct outputs (when base model is good)

## Key Numbers

| Metric | Value |
| --- | --- |
| Training time | 34.1 hours |
| Training steps | 299 |
| Final loss | 1.1600 |
| Training pairs | 2,385 |
| VRAM usage | 11.3GB model + ~5GB training |
| Base model inference | garbage for coding, OK for trivial |
| Experts pruned | 128/256 per layer (50%) |
| Routing capacity retained | 55% |
| Pruning method | L2-norm (should have been activation-aware) |
| Super experts protected | 3 (should have been 8+) |

## Additional Findings (2026-03-01 through 2026-03-02)

### Definitive L2-Pruned Model Test

Tested with multiple repetition_penalty values (1.0, 1.3, 1.5, 2.0), both thinking modes, 64-2048 token limits:
- **rp=1.0**: Pure "```python" repetition (512 tokens of the same string)
- **rp=1.3**: Garbled characters ("isPalindrome = String (S) -> bool" then alphabet cycling)
- **Trivial test**: `**Add**: \`def\` **a**, $B$: Return. $A+ B\`` — model UNDERSTANDS code concepts but CANNOT write syntax
- **Conclusion**: This is NOT a sampler issue. The model fundamentally lost code syntax generation capability.

### llama.cpp DeltaNet Bugs (CONFIRMED)

- GitHub issue #19957: Vulkan completely broken — missing `ggml_ssm_conv` and `ggml_ssm_scan` kernels
- GitHub issue #19894: CUDA implementation 35% slower, incomplete kernel support
- ALL repetition/garbage from llama-server is caused by broken DeltaNet kernels, not sampling parameters
- This architecture has 30 DeltaNet (Gated Delta Networks) layers out of 40 total

### BF16 Full Model + device_map="auto" Failures

- Forward pass produces non-NaN logits (range -11.6 to 12.2) but garbage predictions
- Top-1 predictions are random characters ("phy", "投", "伦") for "Say hello" prompt
- RAM shows only 1.8 GiB for a 70 GB model — mmap lazy loading leaves CPU params uninitialized
- `device_map="auto"` fundamentally broken for this model when CPU offloading is needed

### vLLM Incompatibility

- vLLM 0.16.0 requires `transformers<5,>=4.56.0`
- Qwen3.5-35B-A3B requires `transformers>=5.2.0`
- Version conflict: cannot use vLLM 0.16.0 with this architecture
- Need vLLM update or SGLang as alternative (both claim 20-50 tok/s)

## Corrective Actions for v3.5

1. **Use activation-based pruning** (`--activation-aware`) — selects experts by actual firing frequency on coding tokens
2. **Increase super expert count** from 3 to 8 — protects more critical experts from being pruned
3. **Merge calibration prompts** from `select_experts_esft.py` — 28 diverse coding+general prompts (already done)
4. **Validate before training** — run `serve_model.py --test` after pruning, before committing to training
5. **10-step smoke test** — verify loss decreases, no OOM, no NaN before full training run
6. **Keep LoRA as PEFT adapter** — never merge into BnB 4-bit weights for inference
7. **Use Python inference** — avoid GGUF/llama.cpp for this architecture until upstream support lands
