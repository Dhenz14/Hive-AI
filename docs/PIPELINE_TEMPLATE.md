# Continual Learning Pipeline — Template (v1.1)

## Proven Method (v1-hive cycle, 2026-03-08)
Zero data loss, measurable improvement, 36-minute cycle time.

## v1.1 Changes (2026-03-08)
- Auto llama-server management (no manual restart between steps)
- Step checkpointing — resume from last completed step on failure
- Disk space pre-flight check (60GB minimum)
- All paths via env vars (no hardcoded user paths)
- Improved eval scoring (code-block-aware, structural quality signals)
- 30-minute timeout on regression eval

## Quick Start
```bash
# 1. Prepare data (clean JSONL: instruction/input/output only)
# 2. Set env vars (or add to .env)
export LLAMA_CPP_DIR=/tmp/llama.cpp
export HF_BASE_CACHE=~/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/<hash>

# 3. Kill llama-server (frees GPU)
taskkill /IM "llama-server.exe" /F

# 4. Run the cycle (v1.1: auto-manages llama-server for eval)
bash scripts/run_full_cycle.sh <domain> <data.jsonl> <version> [prev_version]

# Example:
bash scripts/run_full_cycle.sh thinking datasets/thinking_pairs.jsonl v2-think v1-hive

# Resume after failure (automatically skips completed steps):
bash scripts/run_full_cycle.sh thinking datasets/thinking_pairs.jsonl v2-think v1-hive
```

## Pipeline Steps

### Step 1: Prepare Data
- Clean JSONL with only `instruction`, `input`, `output` fields
- Strip all metadata (pyarrow crashes on mixed types)
- No duplicates, no empty outputs

### Step 2: Replay Buffer (automatic)
`replay_sampler.py` selects 500 highest-surprise samples from `replay/` directory.
Falls back to diversity sampling if llama-server is offline.

### Step 3: Train LoRA
```
train_v5.py --rank 8 --lora-plus --attn-only --no-kl --epochs 2
            --replay-dir replay --replay-ratio 0.25
```
- **rank 8**: Small enough to merge cleanly, big enough to learn
- **LoRA+**: B matrix gets 16x higher LR (faster convergence)
- **attn-only**: Train q/k/v/o_proj, freeze MLP (less interference)
- **replay 25%**: Forgetting insurance

### Step 4: Convert & Merge
```bash
# Convert adapter to GGUF
python /tmp/llama.cpp/convert_lora_to_gguf.py --base <HF_CACHE> <adapter_dir> --outfile <lora.gguf>

# Alpha grid search merge
python scripts/safe_merge.py --base-gguf <base> --lora-gguf <lora> \
    --output-dir models/deploy/<version> --validation-data replay/sampled.jsonl \
    --alphas "0.75,0.85,0.95,1.0"
```

### Step 5: Regression Eval
In v1.1, `run_full_cycle.sh` auto-starts llama-server for eval. For manual runs:
```bash
# Start merged model
llama-server.exe -m models/deploy/<version>/merged.gguf --port 11435 \
    --flash-attn on --cache-type-k q8_0 --cache-type-v q4_0 --ctx-size 8192 -ngl 99

# Run 18-probe eval (scoring: 70% keyword + 30% structural quality)
python scripts/regression_eval.py --model-version <version> --threshold 0.03
```
- PASS: promote as new base
- FAIL: increase replay ratio or reduce rank

### Step 6: Promote
```bash
cp models/deploy/<version>/merged.gguf models/deploy/current_base.gguf
```

## Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `LLAMA_CPP_DIR` | `/tmp/llama.cpp` | Path to llama.cpp directory |
| `LLAMA_SERVER_PORT` | `11435` | Port for auto-started llama-server |
| `HF_BASE_CACHE` | Auto-detected | HF snapshot for GGUF conversion |
| `HIVEAI_PROJECT_ROOT` | Auto-detected | Override project root |
| `TRAINING_BASE_DIR` | `/opt/hiveai/project/models/training` | Base dir for HF checkpoints |

## Pre-flight Checklist
- [ ] Kill llama-server before training (frees 10GB VRAM)
- [ ] Data has only instruction/input/output (no metadata)
- [ ] Cycle 1: use default Unsloth base. Cycle 2+: use `--base-model-hf`
- [ ] Clear caches: `rm -rf ~/.cache/huggingface/datasets/* unsloth_compiled_cache/*`
- [ ] CRLF fix if copying scripts to WSL
- [ ] At least 60GB free disk space

## Key Numbers from v1-hive
| Metric | Value |
|--------|-------|
| Training time | 36 min (76 steps) |
| Data size | 480 domain + 160 replay = 640 pairs |
| Loss | 1.11 → 0.63 |
| Merged GGUF size | 14GB (base layers Q5_K_M + LoRA layers F16) |
| Regression eval | 0.935 overall, all domains ≥0.857 |
| Net improvement | +2% on target domain, 0% loss elsewhere |

## When to Use This Pipeline
- **DO train**: Domains the base doesn't know (Hive, thinking/reasoning, custom protocols)
- **DON'T train**: C++, Go, Rust, Python, JS — base already scores 85-100% on these
- **Rule**: If base scores >80% on a domain, training is redundant

## Folder Layout
```
models/deploy/current_base.gguf   — Active GGUF (promoted after each cycle)
replay/*.jsonl                     — Per-domain replay buffers
datasets/*.jsonl                   — Training data per cycle
score_ledger.json                  — Historical regression scores
logs/                              — Per-cycle logs
```

## Stacking Cycles
Each cycle builds on the previous base:
```
Qwen2.5-Coder-14B (v1.0)
  → + Hive LoRA merged (v1-hive)
    → + Think LoRA merged (v2-think)
      → + Next domain merged (v3-xxx)
        → ... forever, zero loss
```
