# HiveAI — LoRA Pipeline Blueprint

**Goal:** Turn HiveAI into a coding-only knowledge engine whose final output is a LoRA adapter
stored locally (and eventually on Hive). The SQLite database is the staging area. LoRA is the
only permanent artifact.

**Current status:** Phase 2 active. LoRA v1 proven (+15% over baseline). Merge cycling and
MoLoRA domain routing implemented. LoRA v5 (dense Qwen3.5-9B) in progress.

---

## The Core Loop

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: MINE                                              │
│  Qwen3 self-generates + web crawl → triples + Golden Books  │
│  Everything lands in SQLite (local staging = "Hive local")  │
└─────────────────────┬───────────────────────────────────────┘
                      │ quality gate ≥ 0.75, enough unique pairs?
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: REFINE                                            │
│  Export training pairs (JSONL) from SQLite                  │
│  Deduplicate via embeddings (tiered: exact/paraphrase/near) │
│  Quality scoring v5 (code cap, no-code gate, MIN_CODE_BLOCKS)│
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: FORGE (LoRA training)                             │
│  Fine-tune on coding training pairs (PEFT + trl)            │
│  Merge cycling: train → merge into base → repeat            │
│  Domain specialists via MoLoRA routing                      │
│  LoRA adapter saved locally (~200-400MB)                    │
│  THIS IS THE GOLDEN BOOK                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │ eval passes threshold? (115 challenges)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 4: PUBLISH                                           │
│  Store LoRA adapter locally (permanent)                     │
│  Publish metadata to Hive: model config, training hashes,   │
│  benchmark scores, version number                           │
│  DBC: on-chain pair proposals, HP-weighted voting, epochs   │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Self-Distillation (COMPLETE)

16 prompt templates (10 standard + 6 O1-style reasoning) generate training pairs from the
model's own knowledge. Genetic expansion (5 mutation operators) multiplies top pairs for
data diversity.

**Implementation:** `hiveai/lora/distiller.py`

**Training data accumulated:**

| Dataset | Pairs | Source |
|---------|-------|--------|
| v1.jsonl | 1,104 | Self-distillation + web crawl |
| v2.jsonl | 982 | Expanded distillation |
| v2_expanded.jsonl | 1,999 | Genetic expansion |
| v3.jsonl | 2,385 | v2 + DBC + MoE research |
| v4.jsonl | 2,414 | v3 + MoE-aware pairs |
| v5.jsonl | 2,529 | Dense model, code-focused |
| dbc_pairs.jsonl | 17 | DBC expert pairs |
| claude_distill_v2 | 1,001 | Claude Opus 4.6 distillation (284 batch files, 50+ domains) |

**Quality gates (scorer v5):**
- Code quality cap: 0.35 (prevents overrating non-working code)
- No-code gate: pairs without MIN_CODE_BLOCKS code blocks cap at 0.49
- MIN_TRAINING_QUALITY: 0.80
- LORA_EXPORT_QUALITY: 0.75
- Tiered dedup: exact (0.95) → paraphrase (0.85) → near (0.75)

---

## Phase 1: Web Crawl (COMPLETE)

Mining complete: 187/187 topics processed. 3,201 total pairs in database (avg quality 0.794).

---

## Phase 2: Training (ACTIVE)

### LoRA Version History

| Version | Base Model | Status | Pairs | Eval | Notes |
|---------|-----------|--------|-------|------|-------|
| v1 | Qwen3-14B | Ready | 1,104 | 0.853 (+15%) | Proven, deployed via llama-server |
| v1.5 | Qwen3-14B | Cancelled | — | — | Superseded by v2 |
| v2 | Qwen3.5-35B-A3B | Killed | — | — | Superseded by v3 |
| v3 | Qwen3.5-35B-A3B (pruned) | Failed | 2,385 | — | Gate-expert alignment bug |
| v4 | Qwen3.5-35B-A3B (pruned) | Blocked | 2,414 | — | MoE-aware ESFT + KL-anchored SFT |
| v5 | Qwen3.5-9B (dense) | In Progress | 2,529 | — | Dense model, maxed-out r=64 |

### Why Dense (v5)

The MoE (Qwen3.5-35B-A3B) approach hit fundamental problems:
- Gate-expert alignment bug corrupted all pruned models (v3, v3.5, etc.)
- Expert pruning → unfusing → training pipeline too fragile
- MoE training requires specialized tooling (ESFT, gate hooks, KL anchoring)

Dense Qwen3.5-9B avoids all of this:
- 9B ALL active parameters per token (vs 3B active in MoE)
- Standard PEFT/LoRA, no gate issues
- Fits 16GB GPU at 4-bit (~6.5GB VRAM)
- Standard llama.cpp GGUF export

### Training Config (v5)

```python
{
    "model": "Qwen/Qwen3.5-9B",
    "r": 64,              # maxed out for 16GB VRAM
    "lora_alpha": 128,    # 2x rank
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    "lora_dropout": 0.05,
    "use_dora": True,
    "neftune_noise_alpha": 5.0,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 8,
    "num_train_epochs": 3,
    "learning_rate": 2e-4,
    "lr_scheduler_type": "cosine",
    "bf16": True,
}
```

### Merge Cycling

After each training run, the LoRA is merged into the base model to create an improved
foundation for the next cycle:

```
Qwen3.5-9B (original) → train v5 LoRA → merge → qwen3.5-9b-cycle1
                                                       ↓
                               train v5.1 LoRA → merge → qwen3.5-9b-cycle2
                                                              ↓
                                          train v5.2 LoRA → merge → ...
```

Each cycle bakes the specialization deeper into the core weights, so subsequent LoRAs
learn on an already-improved foundation. Proven technique used by OpenChat and WizardCoder.

**Implementation:** `hiveai/lora/merge_cycle.py`, `scripts/auto_cycle.py`

**History tracked in:** `loras/merge_history.json`

### MoLoRA (Mixture of LoRA Experts)

Domain-specialized LoRAs with intelligent query routing:

| Domain | Keywords | Ollama Model |
|--------|----------|-------------|
| Python | python, pip, django, flask, pandas, numpy, pytest | hiveai-v5-python |
| Hive | hive, hivemind, hbd, beem, dhive, appbase | hiveai-v5-hive |
| JavaScript | javascript, typescript, node, react, vue, npm | hiveai-v5-js |
| Rust | rust, cargo, tokio, serde, axum | hiveai-v5-rust |
| C++ | c++, cpp, cmake, boost, stl | hiveai-v5-cpp |
| Go | golang, goroutine, gin, cobra | hiveai-v5-go |
| General | (fallback) | hiveai-v5 |

`smart_call()` classifies query domain → routes to specialized model → falls back to
generalist if domain model unavailable.

**Implementation:** `hiveai/lora/molora.py`, integrated into `hiveai/llm/client.py`

**Config:** `MOLORA_ENABLED=true` in `.env` (off by default)

### Domain Training Pipeline

```bash
# Filter training data by domain keywords
python scripts/train_domain.py --domain python --dry-run

# Train domain LoRA (in WSL2)
python scripts/train_domain.py --domain python --base models/qwen3.5-9b-cycle1

# Deploy as separate Ollama model
python scripts/deploy_domain.py --domain python
```

---

## Phase 3: Eval (IMPLEMENTED)

115 coding challenges across 4 dimensions:
- Code correctness: 30%
- Test quality: 30%
- Conceptual depth: 20%
- Explanation quality: 20%

Plus 18 domain-specific anchor sets in `evals/anchors/`.

**Results:**
- Baseline (qwen3:14b): 0.741
- hiveai-v1: 0.853 (+15.1%)

**Implementation:** `scripts/run_eval.py`, `scripts/calibrate_eval.py`

---

## Phase 4: Deployment (IMPLEMENTED)

### Multi-Backend Architecture

```
Query → smart_call() → MoLoRA domain routing (if enabled)
                     → Difficulty classification
                     → Route to appropriate backend:
                        ├── Ollama (standard models)
                        ├── llama-server (LoRA adapters)
                        └── OpenRouter (cloud models)
```

**Confidence routing:** `estimate_query_difficulty()` classifies queries as trivial/simple
(→ fast model) or moderate/complex (→ reasoning model). 60-70% of queries use the fast
model, saving compute.

**llama-server:** Serves LoRA adapters that Ollama can't load natively. Runs on port 11435.

### Deployment Pipeline

```bash
# Deploy v5 (after training)
python scripts/deploy_v5.py

# Steps: verify adapter → merge → GGUF export → Ollama create → eval
```

---

## Phase 5: On-Chain (DBC — BUILT, NOT YET LIVE)

The Decentralized Brain Collective enables on-chain knowledge sharing:

- Nodes propose training pairs via Hive custom_json
- HP-weighted voting prevents sybil attacks
- Epoch-based timeout ensures liveness
- Pair encoding: gzip + base64 (fits Hive's 8KB custom_json limit)
- Secrets scanner: 10 patterns prevent credential leaks
- RC hysteresis: auto-pause at floor, resume at ceiling
- HivePoA: IPFS + GitHub Releases for adapter storage

**Implementation:** `hiveai/dbc/` (2,119 lines, 56 tests passing)

**Config:** `DBC_ENABLED=true`, `DBC_ACCOUNT`, `DBC_POSTING_KEY`

---

## File Layout

```
hiveai/
├── lora/
│   ├── distiller.py       # 16 templates, genetic expansion, scorer v5
│   ├── trainer.py         # LoRA training wrapper (r=32/r=8 micro, DoRA)
│   ├── adapter_manager.py # Runtime multi-LoRA hot-swap
│   ├── merge_cycle.py     # Merge cycling: train → merge → repeat
│   ├── molora.py          # MoLoRA domain router (7 domains)
│   ├── brain_export.py    # IPFS + Hive LoRA publication
│   ├── exporter.py        # Golden Books → training pairs
│   ├── dedup.py           # Embedding-based deduplication
│   └── benchmark.py       # Held-out evaluation
├── dbc/
│   ├── chain.py           # Hive abstraction, pair encoding, protocol
│   ├── node.py            # DBC daemon + MockChain
│   └── hivepoa.py         # IPFS/GitHub adapter storage
├── llm/
│   ├── client.py          # Multi-backend routing, smart_call(), MoLoRA
│   └── prompts.py         # System prompts, CODING_SYSTEM_PROMPT
├── sandbox.py             # Secure code execution (Python + JS)
loras/
├── training_data/         # JSONL datasets (v1-v5, DBC, MoE, domains)
├── v1/                    # LoRA v1 adapter (proven)
├── domains/               # Domain-specialized adapters
└── merge_history.json     # Merge cycle tracking
scripts/
├── train_v5.py            # v5 training (dense Qwen3.5-9B)
├── deploy_v5.py           # Post-training deployment
├── auto_cycle.py          # Merge cycling CLI
├── train_domain.py        # Domain-filtered training
├── deploy_domain.py       # Domain adapter deployment
├── run_eval.py            # 115-challenge eval harness
├── download_model.sh      # Reliable HF model download (XET-safe)
├── calibrate_eval.py      # Eval anchor calibration
├── claude_distill.py      # Claude distillation v1
├── claude_distill_v2.py   # Claude Opus 4.6 distillation v2 (batch loader)
├── distill_batches/       # 284 batch files (1,001 expert-curated pairs)
└── distill_multilang.py   # Multi-language distillation
evals/
└── anchors/               # 18 domain-specific anchor sets
```

---

## Summary

| What | Where | Status |
|------|-------|--------|
| Raw triples + books | SQLite (staging) | 3,201 pairs, 187 topics mined |
| Training pairs | SQLite + JSONL exports | v1-v5 datasets ready |
| Claude distillation | `scripts/distill_batches/` | 1,001 pairs, 284 files, 50+ domains |
| LoRA v1 adapter | `loras/v1/` | Proven (+15%), deployed |
| LoRA v5 adapter | (in progress) | Dense Qwen3.5-9B, r=64 |
| Merge cycling | `hiveai/lora/merge_cycle.py` | Implemented, ready |
| MoLoRA routing | `hiveai/lora/molora.py` | Implemented, off by default |
| DBC protocol | `hiveai/dbc/` | Built (2,119 lines, 56 tests) |
| Eval system | `scripts/run_eval.py` | 115 challenges, calibrated |
| Provenance record | Hive blockchain | Ready (DBC Phase 1 built) |
