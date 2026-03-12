# HiveAI Refinery — Continual Learning Pipeline

## Overview

HiveAI is a self-improving AI knowledge refinery built on Qwen2.5-Coder-14B-Instruct. It uses a **merge-then-freeze** architecture where trained LoRA adapters are permanently merged into the base model weights after each learning cycle. Once merged, knowledge can never be lost — it becomes part of the model's permanent weights.

The system runs entirely on local hardware (single RTX 4070 Ti SUPER, 16GB VRAM) with zero cloud dependency.

## Core Architecture: Merge-Then-Freeze

Traditional LoRA fine-tuning stacks adapters that can conflict and degrade. HiveAI takes a fundamentally different approach:

1. **Train** a small LoRA adapter (rank 4-8) on new domain knowledge
2. **Merge** the adapter permanently into the base model weights via PEFT `merge_and_unload()`
3. **Consolidate** the merge with a stabilization epoch (rank 2, LR/20, 100% replay)
4. **Evaluate** with 18-probe regression testing across all domains
5. **Promote** the merged model as the new base — knowledge is now permanent

This is like welding new components onto a structure rather than bolting them on. Each cycle makes the foundation stronger.

## The 7-Step Pipeline

The complete cycle is orchestrated by `run_full_cycle.sh`:

### Step 1: Replay Sampling (replay_sampler.py)

Before training new knowledge, the system selects replay data from past domains to prevent forgetting. Uses **SuRe (Surprise-driven Replay)** — the model's own loss function identifies which past knowledge it has most forgotten (highest NLL scores), and those samples are prioritized.

```
# SuRe sampling: score each replay candidate by surprise (NLL loss)
# Higher loss = model has forgotten this more = higher replay priority
scores = compute_nll_per_sample(model, replay_candidates)
selected = top_k_by_score(scores, k=replay_budget)
```

Falls back to diversity-based stratified sampling if the inference server is unavailable.

### Step 2: Training (train_v5.py)

QLoRA training with multiple innovations stacked:

- **LoRA+**: B matrix gets 16x higher learning rate than A matrix (arXiv 2602.04998). 40-60% faster convergence.
- **Response-only loss masking**: Only trains on response tokens via `DataCollatorForCompletionOnlyLM`. Prevents memorizing questions.
- **RSLoRA**: Rank-stabilized scaling ensures consistent quality at any LoRA rank.
- **NEFTune**: Calibrated noise injection during training, consistently +0.5-1% quality.
- **KL regularization**: Optional anchor loss preventing catastrophic forgetting during aggressive training.
- **Replay mixing**: 25% of each training batch is replay data from past domains.

```python
# LoRA+ configuration
optimizer_cls_and_kwargs = (
    "adamw_8bit",
    {"lr": base_lr, "weight_decay": 0.01}
)
# B matrix gets 16x higher LR via create_loraplus_optimizer
```

Key flags: `--rank 4-8`, `--lora-plus`, `--replay-ratio 0.25`, `--base-model-hf <path>`

### Step 3: GGUF Conversion (auto, post-training)

After training, the PEFT adapter is automatically converted to GGUF format via llama.cpp's `convert_lora_to_gguf.py`. Both formats are kept: PEFT for the golden chain, GGUF for fast inference evaluation.

### Step 4: Safe Merge with Alpha Grid Search (safe_merge.py)

The merge strength (alpha) determines how much of the LoRA's changes are applied. Too high risks overwriting existing knowledge; too low wastes training effort.

```
Alpha grid: [0.75, 0.85, 0.95, 1.0]
For each alpha:
  1. Merge LoRA into base at this alpha
  2. Compute perplexity on validation data
  3. Record score
Pick alpha with lowest perplexity
```

The merge happens through the **bf16 golden chain**:
- HF bf16 weights are the canonical source of truth
- PEFT `merge_and_unload()` at the chosen alpha
- GGUF is derived via `convert_hf_to_gguf.py` + `llama-quantize` (Q5_K_M)
- This eliminates quantization drift — even after 100+ merges, zero accumulated rounding noise

### Step 5: Consolidation (consolidation_train.py)

Post-merge stabilization inspired by ProgLoRA (ACL 2025) and Online-LoRA (WACV 2025):

- **Rank 2** LoRA (minimal — just smoothing artifacts)
- **LR/20** (1e-5 default — very gentle)
- **1 epoch** only
- **100% replay data** (the anchor IS the training data)
- Trains all 7 LoRA modules (q/k/v/o_proj + gate/up/down_proj)

This is the annealing step — it smooths out discontinuities from the merge while reinforcing all existing knowledge.

### Step 6: Regression Evaluation (regression_eval.py)

18 domain probes (3 per domain across 6 domains):

| Domain | Example Probes |
|--------|---------------|
| Python | Decorator patterns, async generators, metaclasses |
| Rust | Ownership semantics, trait implementations, lifetime bounds |
| Go | Goroutine patterns, interface composition, channel orchestration |
| C++ | RAII/smart pointers, template metaprogramming, move semantics |
| JavaScript | Promise chains, TypeScript generics, event loop mechanics |
| Hive | Custom JSON operations, DHive SDK usage, RC system management |

Each probe is scored against historical best (from `score_ledger.json`). If ANY domain drops more than 0.03, the merge is **rejected** and the cycle fails.

On failure, `weakness_hunter.py` is automatically triggered to generate targeted training pairs for the weak domains.

### Step 7: Promote

The merged, consolidated, and validated model becomes the new base:
- Q5_K_M GGUF deployed to `models/deploy/current_base.gguf`
- bf16 HF checkpoint saved to `models/golden/<version>-hf/`
- Score ledger updated with new domain scores
- Old intermediate files cleaned up (keep 3 GGUF versions, 2 bf16 checkpoints)

## The Golden Chain

The bf16 golden chain solves a subtle but critical problem: quantization drift.

**The problem**: Each GGUF merge via `llama-export-lora` introduces tiny rounding noise (~0.0002 per merge). After 10 merges, ~0.002 accumulated drift. After 100 merges, potentially noticeable degradation.

**The solution**: Keep bf16 HuggingFace weights as the canonical source of truth. Only quantize to GGUF once at deployment time.

```
Merge chain:
  Original bf16 → + v1-hive LoRA → v1-hive bf16
                                        → + v2-think LoRA → v2-think bf16
                                                                → + v3-X LoRA → ...
                                                                        ↓ (only at deploy)
                                                                   quantize to Q5_K_M GGUF
```

The permanent bf16 base lives at `models/golden/original-bf16/` and is never deleted. Each merged checkpoint becomes the base for the next cycle.

## Micro-Training Philosophy

HiveAI uses micro-cycles instead of bulk training:

- **500 pairs per batch** (not 5,000 or 10,000)
- **~30 minutes per cycle** (not 10 hours)
- **Evaluate between each batch** (catch problems early)
- **Merge and freeze** after each successful batch
- **Move to next domain** when current domain is mastered

This means:
- A bad batch wastes 30 minutes, not 10 hours
- Each merge is small and low-risk
- The model improves incrementally with constant quality verification
- Multiple domains can be trained in a single day

## Data Sources

HiveAI has 7 automated data sources:

1. **Multi-Provider Miner** (`hiveai/lora/miner.py`): Rotates through Gemini, OpenRouter, Groq, Cerebras, DeepSeek, Mistral, HuggingFace APIs to generate coding pairs 24/7
2. **Self-Distillation** (`hiveai/lora/distiller.py`): 7 template patterns (implement, correct_way, why_exists, mistakes, internals, compare, test_driven)
3. **Skills-to-Pairs** (`scripts/skills_to_pairs.py`): 22 SKILL.md modules → 734+ training pairs
4. **Distill Batches** (`scripts/load_batches.py`): 6,395 pairs from 1,210+ batch files
5. **Weakness Hunter** (`scripts/weakness_hunter.py`): Auto-generates pairs for weak domains after eval failure
6. **Chat Feedback** (`hiveai/app.py`): User thumbs-up/down stages verified pairs
7. **9-Source Consolidator** (`scripts/build_training_dataset.py`): Merges all sources with dedup

## Quality Gates

### Tiered Deduplication (hiveai/lora/dedup.py)
- EXACT (>0.95 cosine similarity): Always rejected
- PARAPHRASE (0.85-0.95): Only accepted with significant quality improvement
- NEAR (0.75-0.85): Accepted if covering different angles
- UNIQUE (<0.75): Always accepted

### Pre-Flight Validator (scripts/preflight_check.py)
7 checks before training: HF_HUB_OFFLINE mode, metadata fields, CRLF line endings, disk space (>20GB), GPU VRAM availability, base model integrity, HF cache verification.

### 18-Probe Regression Gate
Threshold-based: reject if any domain drops >0.03 from historical best. Auto-triggers weakness_hunter on failure.

## Inference Features

- **Circuit Breakers**: Per-backend failure isolation (llama, ollama, openrouter, embedding) with threshold → cooldown → half-open recovery
- **MoLoRA Router** (`hiveai/lora/molora.py`): Domain-aware query routing with keyword classification and 1.5x Hive domain boost
- **LoRA Hot-Swap**: Runtime adapter swapping via `POST /api/lora/adapters` without server restart
- **Auto-Improve Daemon**: Background worker triggers micro-training when 50+ verified pairs accumulate
- **Context Compression** (`hiveai/chat.py`): RAG with token budgets, BM25 reranking, 30-min TTL cache

## Decentralized Distribution

- **IPFS Brain Export** (`hiveai/lora/brain_export.py`): Pin trained adapter GGUF to local IPFS, get content-addressed CID
- **Hive Blockchain Publishing**: Publish model metadata (version, CID, hash) as custom_json for peer discovery
- **Proof of Authority** (`hiveai/pipeline/authority.py`): Validate knowledge claims against Hive blockchain history

## Key Configuration

```python
# Continual learning defaults
LORA_RANK = 4            # Small rank for incremental merges
LORA_ALPHA = 8           # 2x rank
REPLAY_RATIO = 0.25      # 25% replay in each batch
CONSOLIDATION_LR = 1e-5  # LR/20 for post-merge stabilization
CONSOLIDATION_RANK = 2   # Minimal rank for smoothing
REGRESSION_THRESHOLD = 0.03  # Max allowed per-domain score drop
MICRO_BATCH_SIZE = 500   # Pairs per micro-training cycle
```

## File Map

| Component | File | Purpose |
|-----------|------|---------|
| Orchestrator | `scripts/run_full_cycle.sh` | 7-step cycle with checkpointing |
| Training | `scripts/train_v5.py` | QLoRA with LoRA+, replay, NEFTune |
| Merge | `scripts/safe_merge.py` | Alpha grid search + golden chain |
| Consolidation | `scripts/consolidation_train.py` | Post-merge stabilization |
| Eval | `scripts/regression_eval.py` | 18-probe regression gate |
| Quick Eval | `scripts/quick_eval.py` | 20-prompt fast check |
| Replay | `scripts/replay_sampler.py` | SuRe NLL-scored sampling |
| Preflight | `scripts/preflight_check.py` | 7 pre-training checks |
| Batch Split | `scripts/batch_splitter.py` | 500-pair micro-batches |
| Score Ledger | `score_ledger.json` | Historical domain scores |
| Golden Base | `models/golden/<version>-hf/` | bf16 source of truth |
| Deploy GGUF | `models/deploy/current_base.gguf` | Active inference model |

## Current Results

v1-hive (first merge cycle): overall 0.935
- JavaScript: 1.000, Go: 0.952, Hive: 0.952, Rust: 0.952, Python: 0.897, C++: 0.857

The base Qwen2.5-Coder-14B already scored 0.978 on general coding. The merge-then-freeze architecture added Hive blockchain expertise while maintaining strong performance across all existing domains.
