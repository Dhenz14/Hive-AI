# HiveAI Master Plan — The Knowledge Refinery

## Vision

Turn Qwen2.5-Coder-14B into the best local coding AI for Hive blockchain development
and general software engineering. Not by switching models, but by building a
self-improving knowledge pipeline on top of a stable base.

```
                    ┌─────────────────────────────────┐
                    │     PRODUCTION (llama-server)     │
                    │                                   │
                    │  Base GGUF (Q5_K_M)               │
                    │    + Runtime LoRA (latest)         │
                    │    + Agent Skills (per-session)    │
                    │                                   │
                    └──────────┬────────────────────────┘
                               │ serves users
                               ▼
                    ┌─────────────────────────────────┐
                    │     FEEDBACK LOOP                 │
                    │                                   │
                    │  User conversations → scored      │
                    │  Failures extracted → training     │
                    │  Skills auto-updated               │
                    │                                   │
                    └──────────┬────────────────────────┘
                               │ feeds
                               ▼
                    ┌─────────────────────────────────┐
                    │     TRAINING PIPELINE (WSL2)     │
                    │                                   │
                    │  Merge prev LoRA → new base       │
                    │  Train new LoRA (failures only)   │
                    │  Eval on hard suite → gate deploy │
                    │                                   │
                    └─────────────────────────────────┘
```

---

## Phase 1: v7 Completion (NOW — today)

**Status**: Training at step ~400/714, ~3.5h remaining

### Steps
1. Wait for training to complete (~714 steps, ~9h total)
2. Convert adapter to GGUF:
   ```bash
   cd /opt/hiveai/project
   python /opt/hiveai/project/scripts/convert_lora_to_gguf.py \
     loras/v7 \
     --base /root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d \
     --outfile models/hiveai-v7-lora-f16.gguf --outtype f16
   ```
3. Start llama-server with v7 LoRA
4. Run NEW hard quick_eval (20 prompts) — establishes v7 baseline scores
5. Run full hard eval (50 challenges from eval_challenges_hard.json)
6. If no degradation on easy prompts + improvement on hard prompts → deploy
7. Clean up 13 individual subject GGUF files from models/

### Success Criteria
- Zero degradation on Python/algorithms (easy tier)
- Measurable improvement on Hive prompts (14-16)
- No crashes or garbage output on any prompt

### Deliverables
- `models/hiveai-v7-lora-f16.gguf` — production LoRA
- `evals/v7_hard_baseline.json` — hard eval results (our new ground truth)

---

## Phase 2: Failure Mining + Data Curation (Day 2)

**Goal**: Find every weakness in v7, build targeted v8 training data

### Step 2a: Mine Failures
```bash
# Run failure mining on all 215 challenges (165 regular + 50 hard)
python scripts/mine_failures.py \
  --base-url http://localhost:11435 \
  --threshold 0.7 \
  --output loras/training_data/v8_failures.jsonl
```

Expected output: A JSONL of every challenge v7 scores below 0.7 on, with:
- The challenge instruction
- The model's actual (bad) response
- Which scoring dimensions failed
- The category and difficulty

### Step 2b: Generate Training Pairs for Failures

For each failure, generate a Claude-quality training pair:
1. Take the failed challenge instruction
2. Generate an ideal response with deep `<think>` reasoning
3. Format as instruction/output JSONL
4. Quality-check: every pair must have genuine reasoning, not filler

This is the "Robin Hood" principle — Claude does the thinking once, local model benefits forever.

### Step 2c: Merge with Second Team's Data

Second team is generating:
- 450 pairs across 9 categories (Hive x5, Rust, Go, C++, JS)
- Claude-distilled reasoning traces with `<think>` blocks
- Focus on our weak areas

Combine: `v8_failures.jsonl` + second team's pairs + `v8_research_pairs.jsonl` (9 pairs already created)

### Step 2d: Importance Scoring

Score every training pair 0-1:
- **1.0**: Model completely fails at this (critical failure from mine_failures)
- **0.8**: Model produces mediocre output (failure from mine_failures)
- **0.5**: New domain knowledge model doesn't have (Hive, research techniques)
- **0.2**: Reinforcement of existing capability (drop these — v7 already handles them)

Only train on pairs scoring >= 0.5. Quality over quantity.

### Deliverables
- `loras/training_data/v8_failures.jsonl` — mined failure data
- `loras/training_data/v8_targeted.jsonl` — Claude-generated pairs for failures
- `loras/training_data/v8_combined.jsonl` — final curated training set

---

## Phase 3: v8 Training — Continual, Not From Scratch (Day 2-3)

**Goal**: Train v8 LoRA on v7-merged base with ONLY new data

### Step 3a: Merge v7 into Base
```bash
# In WSL
cd /opt/hiveai/project
python scripts/merge_lora.py \
  --lora-dir loras/v7/ \
  --output-dir models/v7-merged/ \
  --force
```

This bakes v7 knowledge into the base weights. v8 LoRA only needs to learn NEW things.

### Step 3b: Train v8 LoRA

Key changes from v7 based on research:

| Setting | v7 | v8 (proposed) | Why |
|---------|-----|---------------|-----|
| Base model | Original Qwen2.5-Coder-14B | v7-merged | Continual learning |
| Data | 5,998 pairs (everything) | ~500-1000 pairs (failures + new only) | Quality > quantity |
| Target modules | All linear layers | Attention only (q,k,v,o_proj) | Freezing MLP improves quality (QAD finding) |
| LoRA rank | r=16 | r=16 | Keep same for compatibility |
| Epochs | 2 | 3 | Smaller dataset needs more passes |
| KL regularization | OFF | ON (lambda=0.3) | Prevent forgetting v7-merged knowledge |
| Optimizer | AdamW + cosine | AdamW + cosine + 5% warmup | Validated by QAD research |
| Loss | Cross-entropy | Cross-entropy + KL hybrid | Soft labels preserve behavior |

```bash
python scripts/train_v5.py \
  --data loras/training_data/v8_combined.jsonl \
  --output-dir loras/v8/ \
  --epochs 3 \
  --force-unsloth
```

### Step 3c: Ablation — Attention-Only vs All Layers

Based on QAD research (freezing MLP = +3.2 dB), run TWO experiments:

**Experiment A**: LoRA on attention layers only (q_proj, k_proj, v_proj, o_proj)
**Experiment B**: LoRA on all layers (current default)

Compare on hard eval. Use whichever scores higher. This is how the QAD team found their best config — 228 experiments. We do at least 2.

### Step 3d: Eval Gate

v8 must pass ALL of these before deployment:
1. Hard quick_eval (20 prompts) >= v7 scores on every category
2. Hard eval (50 challenges) >= v7 scores overall
3. Hive-specific prompts (14-16) show measurable improvement
4. Zero degradation on easy Python/algorithms prompts
5. No garbage output on any prompt

If ANY gate fails → do not deploy. Investigate, fix data, retrain.

### Deliverables
- `loras/v8/` — trained PEFT adapter
- `models/hiveai-v8-lora-f16.gguf` — production LoRA
- `evals/v8_hard_eval.json` — eval results with comparison to v7

### Expected Training Time
- ~500-1000 pairs at 2048 seq_len, batch 1, grad_accum 16
- ~60-125 steps per epoch, 3 epochs = 180-375 steps
- At ~40s/step = 2-4 hours (vs v7's 9 hours)

---

## Phase 4: Agent Skills Layer (Day 3, parallel with Phase 3)

**Goal**: Immediate quality boost with zero training cost

### Skills to Create

| Skill | Tokens | Impact |
|-------|--------|--------|
| `hive-blockchain-ops.md` | ~500 | Teaches custom_json, key hierarchy, authority rules |
| `hive-engine-tokens.md` | ~400 | Hive Engine token ops, ssc-mainnet-hive patterns |
| `hive-economics.md` | ~400 | Reward pool, vesting, delegation APR formulas |
| `rust-async-patterns.md` | ~400 | Tokio, Semaphore, error handling chains |
| `go-concurrency.md` | ~400 | Goroutines, channels, context cancellation |
| `debugging-patterns.md` | ~300 | Common bug categories, systematic diagnosis approach |

### Integration

```python
# In hiveai/llm/prompts.py — inject relevant skill based on query topic
def get_system_prompt(user_query: str) -> str:
    base_prompt = CODING_SYSTEM_PROMPT

    # Detect topic and inject relevant skill
    skill = detect_and_load_skill(user_query)
    if skill:
        base_prompt += f"\n\n{skill}"

    return base_prompt
```

### Evaluation
Use `upskill eval` to measure skill lift on each skill file.
Target: >= 20% improvement on domain-specific prompts.

### Deliverables
- `skills/` directory with 6 skill files
- `hiveai/skills.py` — skill detection and injection module
- Skill lift measurements for each

---

## Phase 5: Self-Improving Consolidation Loop (Week 2+)

**Goal**: The model improves itself over time with minimal human intervention

### Architecture

```
User Query → HiveAI Response → Score Response → Store in DB
                                                      │
                                                      ▼
                                        ┌──────────────────────┐
                                        │  Consolidation Agent  │
                                        │  (runs every 24h)     │
                                        │                       │
                                        │  1. Review responses   │
                                        │  2. Score quality 0-1  │
                                        │  3. Extract failures   │
                                        │  4. Generate pairs     │
                                        │  5. Update skills      │
                                        │  6. Flag for retrain   │
                                        └──────────────────────┘
                                                      │
                                              when enough failures
                                              accumulate (>100)
                                                      ▼
                                        ┌──────────────────────┐
                                        │  Auto-Retrain Trigger │
                                        │                       │
                                        │  merge_lora → train   │
                                        │  → eval → deploy      │
                                        └──────────────────────┘
```

### Components

**Response Logger** (add to Flask app):
- Every model response gets stored with the query, response, and timestamp
- Lightweight — just append to SQLite

**Quality Scorer** (background job):
- Run scoring functions from run_eval.py on stored responses
- Flag responses scoring below 0.7

**Consolidation Agent** (daily cron):
- Reviews all flagged responses from the past 24h
- Groups failures by category
- Generates training pair candidates
- Updates agent skill files if patterns emerge
- Triggers retrain when failure count exceeds threshold

**Auto-Retrain Pipeline**:
- merge current LoRA → train on accumulated failures → eval gate → deploy if passes
- Fully automated, human only reviews the eval report

### Deliverables
- `hiveai/consolidation.py` — consolidation agent
- `hiveai/response_logger.py` — response storage
- `scripts/auto_retrain.sh` — automated retrain pipeline
- SQLite schema for response storage

---

## Phase 6: Future Base Model Evaluation (Month 2+)

**Goal**: Determine if we should upgrade from Qwen2.5-Coder-14B

### Candidates to Evaluate
- **Qwen3.5-Coder-14B** (if released) — direct successor, same size
- **Qwen3.5-27B at Q4_K_M** — fits in 16GB VRAM? Benchmark vs 14B
- **DeepSeek-Coder-V3** — if available in our size range
- **Starcoder3** — pure code model alternative

### Evaluation Criteria
1. Run hard eval suite on each candidate (50 challenges, zero-shot)
2. Must score higher than v8 LoRA on general coding
3. Must fit in 16GB VRAM with room for LoRA + agent skills
4. Must be supported by Unsloth for LoRA training
5. Must have GGUF conversion support in llama.cpp

### Decision Rule
Only switch base if:
- New base scores > current v8 LoRA on hard eval by >= 10%
- All tooling (Unsloth, llama.cpp, GGUF) supports it
- LoRA training validated on new base (no loss divergence)

---

## Timeline Summary

| Phase | What | When | Time |
|-------|------|------|------|
| 1 | v7 completion + deploy | Today | ~4h remaining |
| 2 | Failure mining + data curation | Tomorrow | 4-6h |
| 3 | v8 training (continual) | Day 2-3 | 2-4h training + eval |
| 4 | Agent skills (parallel) | Day 3 | 3-4h |
| 5 | Consolidation loop | Week 2 | 1-2 days build |
| 6 | Base model eval | Month 2+ | As needed |

## Hardware Budget

| Resource | Current | Needed |
|----------|---------|--------|
| GPU VRAM | 16GB RTX 4070 Ti Super | Sufficient for all phases |
| System RAM | 63.4GB | Sufficient |
| WSL2 Disk | Monitor vhdx growth | Compact after each training run |
| Training time per version | 9h (v7) → 2-4h (v8) | Improving each iteration |

## Research Applied

Every phase incorporates findings from our research:

| Finding | Source | Applied In |
|---------|--------|-----------|
| Quality > quantity | Jackrong distillation | Phase 2 (importance scoring) |
| Freeze MLP layers | QAD (AliesTaha) | Phase 3 (attention-only LoRA ablation) |
| AdamW + cosine + warmup | QAD (AliesTaha) | Phase 3 (optimizer config) |
| Agent skills for instant boost | HuggingFace Upskill | Phase 4 |
| Pre-compute teacher outputs | QAD (AliesTaha) | Phase 2 (Claude-generated pairs) |
| Consolidation loop | Google Memory Agent | Phase 5 |
| Robin Hood principle | All research | Phase 2 (Claude generates, local benefits) |
| Simple beats complex | QAD, Upskill | All phases (SQLite, MSE, markdown skills) |
