# The Elastic Brain — Design Document

**Version:** 1.0
**Date:** 2026-03-20
**Authors:** Claude (Hive-AI), with research input from GPT (HivePoA)
**Status:** Phase 1 in progress, Phase 2-4 designed

---

## The Expert Plumber, Revisited

An expert plumber knows HOW to think about plumbing. He carries a perfectly organized
notebook of verified solutions. But right now, he works alone — one brain, one set of
hands, one speed.

The Elastic Brain gives the plumber **superpowers that scale with his team size**:

- **Working alone (1 GPU):** Smart plumber with his notebook. Gets the job done.
- **With a partner (2 GPUs):** Same plumber, but now he can think with higher precision
  AND flip through his notebook twice as fast.
- **With a crew (4-8 GPUs):** Plumber consults with 4 versions of himself, they debate,
  and the best answer wins. Demonstrably better than working alone.
- **With a company (40+ GPUs):** The plumber's brain physically grows — more neural
  pathways, more specialized knowledge activated per problem. A fundamentally
  more capable thinker.

Each level builds on the last. No level requires throwing away what came before.

---

## Architecture Overview

```
                           THE ELASTIC BRAIN
                    (scales intelligence with GPU count)

 Phase 1 (NOW)          Phase 2 (Month 2)       Phase 3 (Month 3-4)      Phase 4 (Month 6+)
 ──────────────         ────────────────        ─────────────────       ─────────────────
 Dynamic Quant          Best-of-N               Mixture of Agents       Sparse Upcycling
 + Context Scale        Sampling                + Long Context          to MoE + EMoE

 Same model,            Same model,             Multiple copies         New MoE checkpoint
 sharper glasses        pick best answer        debate & converge       with variable k'

 Quality: +5-10%        Quality: +15-30%        Quality: +20-40%        Quality: +50-100%
 Training: ZERO         Training: ZERO          Training: ZERO          Training: MASSIVE
 Effort: TRIVIAL        Effort: LOW             Effort: MEDIUM          Effort: HIGH
```

---

## Phase 1: Dynamic Scaling (ZERO TRAINING)

**Goal:** Same v5-think checkpoint, quality scales with available VRAM/GPUs.
**Status:** Partially live, needs completion.

### 1A. Dynamic Quantization

The same bf16 weights quantized to different precision levels. More GPU memory =
higher precision = closer to the model's true capability.

| Quant | GGUF Size | VRAM | Quality vs FP16 | GPUs Needed |
|-------|-----------|------|-----------------|-------------|
| Q2_K | 5.8 GB | ~6 GB | -15% (emergency fallback) | 1 (any GPU) |
| Q3_K_M | 7.3 GB | ~8 GB | -5% (degraded but usable) | 1 (8GB+) |
| Q4_K_M | 9.0 GB | ~9.5 GB | -2% (good daily driver) | 1 (12GB+) |
| Q5_K_M | 10.5 GB | ~11 GB | -0.3% (current deploy) | 1 (16GB) |
| Q6_K | 12.1 GB | ~13 GB | -0.1% (near-perfect) | 1 (16GB, tight) |
| Q8_0 | 15.7 GB | ~16 GB | -0.05% (essentially FP16) | 1 (16GB, no ctx) |
| FP16 | 29.5 GB | ~30 GB | baseline (ceiling) | 2 (16GB each) |

**How it works at runtime:**
```python
def select_quantization(available_vram_gb: float, context_needed: int) -> str:
    """Pick the best quant that fits available VRAM with room for KV cache."""
    kv_cache_gb = (context_needed * 0.000192)  # ~192KB per token
    model_budget = available_vram_gb - kv_cache_gb - 1.0  # 1GB overhead

    if model_budget >= 28: return "f16"      # 2+ GPUs
    if model_budget >= 15: return "q8_0"     # 1 GPU, minimal context
    if model_budget >= 12: return "q6_k"     # 1 GPU, short context
    if model_budget >= 10: return "q5_k_m"   # 1 GPU, 8K context (current)
    if model_budget >= 8:  return "q4_k_m"   # 1 GPU, 16K+ context
    if model_budget >= 7:  return "q3_k_m"   # constrained GPU
    return "q2_k"                             # emergency mode
```

#### Checklist — Phase 1A

- [x] bf16 source of truth exists (`/opt/hiveai/project/models/training/v5-think/hf/`)
- [x] Q5_K_M GGUF deployed as current_base (10.5 GB)
- [x] `convert_hf_to_gguf.py` + `llama-quantize` pipeline validated
- [x] Flash attention enabled (mandatory for quality — cpp-variadic drops without it)
- [x] Context scaling: 4K (campaign) / 8K (chat_rag) modes working
- [ ] Generate Q2_K GGUF from bf16 (emergency fallback)
- [ ] Generate Q3_K_M GGUF from bf16 (degraded mode)
- [ ] Generate Q4_K_M GGUF from bf16 (light mode)
- [ ] Generate Q6_K GGUF from bf16 (enhanced mode)
- [ ] Generate Q8_0 GGUF from bf16 (near-perfect mode)
- [ ] Generate FP16 GGUF from bf16 (max precision, 2-GPU mode)
- [ ] Build quant selector: given available VRAM + context needs, pick best quant
- [ ] Wire quant selector into tier_autoscaler.py (Solo → Pool transition)
- [ ] Store all GGUFs in `/opt/hiveai/project/models/deploy/` with naming convention
- [ ] Validate each quant with quick 18-probe eval (one-time baseline)
- [ ] Document probe score deltas per quant level in score_ledger.json

### 1B. Context Window Scaling

More VRAM = bigger context = more RAG sections injected = smarter responses.

| Context | KV Cache (Q8+Q4) | Max RAG Sections | Use Case |
|---------|------------------|-------------------|----------|
| 4,096 | ~384 MB | 4-5 sections | Campaign probes, simple queries |
| 8,192 | ~768 MB | 8-10 sections | Chat RAG (current default) |
| 16,384 | ~1.5 GB | 15-20 sections | Deep code analysis |
| 32,768 | ~3.0 GB | 30-40 sections | Full codebase context |
| 65,536 | ~6.0 GB | 60+ sections | Comprehensive architecture review |

#### Checklist — Phase 1B

- [x] 4K context mode (campaign_probe) working
- [x] 8K context mode (chat_rag) working
- [x] Quantized KV cache flags supported (--cache-type-k q8_0 --cache-type-v q4_0)
- [x] Runtime mode switching via env vars (no .env editing)
- [x] Language-aware RAG routing (C++ query → C++ sections boosted)
- [x] 12,062 searchable sections (11,136 solved examples + 926 golden book)
- [ ] 16K context mode configuration
- [ ] 32K context mode configuration (for 2-GPU Pool)
- [ ] Adjust `budget_context()` max_tokens to scale with available context
- [ ] Wire context_size into tier_autoscaler.py (more GPU → bigger context)

---

## Phase 2: Best-of-N Sampling (ZERO TRAINING)

**Goal:** Generate multiple candidate responses, verify each, return the best.
**Quality improvement:** +15-30% on complex coding tasks.
**Mechanism:** Same model, same weights — test-time compute scaling.

This is what OpenAI o1/o3 and DeepSeek-R1 use internally. More compute at
inference time = better answers, without touching the model weights.

### How It Works

```
User asks: "Implement a lock-free queue in C++"

1 GPU (N=1):   Generate 1 response → return it
               Quality: baseline

4 GPUs (N=4):  Generate 4 responses in parallel (temp=0.3, 0.5, 0.7, 0.9)
               → Verify each (compile, run tests)
               → Score each (code quality, completeness, correctness)
               → Return the best
               Quality: significantly better — weak responses filtered out

8 GPUs (N=8):  Generate 8 responses
               → Verify all
               → Pick top 2, ask model to synthesize best parts of both
               → Return synthesized answer
               Quality: exceeds any single generation
```

### Why This Works

- Verification is our strength — we already have Python/JS/C++/Rust/Go sandboxes
- Each candidate is independent — trivially parallelizable across pool nodes
- Bad responses are caught by verification — only proven code survives
- The model's variance works FOR us — different temperatures explore different solutions

### Integration with Pool Mode

```
HivePoA receives query
  → Routes to N pool nodes simultaneously (one query each, different temp)
  → Collects N responses
  → Runs verification on each (can distribute across nodes too)
  → Picks best by: verification_pass > code_lines > response_quality
  → Returns winner to user
```

#### Checklist — Phase 2

- [x] Pool mode endpoints working (`/api/compute/inference`, `/api/compute/inference/rag`)
- [x] Code verification pipeline (Python, JS, C++, Rust, Go sandboxes)
- [x] Pool health monitoring (`/ready`, `/api/compute/status`)
- [x] Load-balanced routing (HivePoA routes to lowest-load node)
- [ ] Add `temperature` param to `/api/compute/inference`
- [ ] Build best-of-N coordinator in HivePoA (send query to N nodes)
- [ ] Build response scorer (verification_passed > code_quality > completeness)
- [ ] Build response synthesizer (merge best parts of top-2 responses)
- [ ] Add `candidates` field to inference response (how many were generated)
- [ ] Add `selection_method` to response trace (best-of-N, synthesis, single)
- [ ] Benchmark: measure quality delta between N=1, N=3, N=5, N=8
- [ ] Wire into tier_autoscaler: Pool mode auto-enables best-of-N when spare GPU exists
- [ ] Dashboard: show "N candidates evaluated" in response metadata

---

## Phase 3: Mixture of Agents (ZERO TRAINING)

**Goal:** Multiple copies of the model debate and converge on the best answer.
**Quality improvement:** +20-40% on complex multi-step problems.
**Mechanism:** Agents see each other's drafts and refine. Consensus > any individual.

### How It Works

Unlike best-of-N (independent parallel generation), Mixture of Agents is iterative:

```
Round 1: 4 agents each generate an answer independently
Round 2: Each agent sees ALL other agents' Round 1 answers
         → Each refines their answer incorporating the best ideas
Round 3: Aggregator synthesizes the 4 refined answers into one final response

Result: Demonstrably exceeds any single model's capability.
        Like 4 senior engineers reviewing each other's code.
```

### Research Basis

Wang et al. "Mixture-of-Agents Surpasses GPT-4o" — showed that even weak models
collaborating via this pattern outperform single strong models. The key insight:
LLMs are better at refining others' work than generating from scratch.

### Integration Architecture

```
                    HivePoA Coordinator
                          │
           ┌──────────────┼──────────────┐
           │              │              │
       Node A          Node B         Node C
    (v5-think)       (v5-think)     (v5-think)
           │              │              │
    Round 1: Generate  Generate      Generate
           │              │              │
           └──────┬───────┴──────┬───────┘
                  │    Share     │
           ┌──────┴───────┬─────┴────────┐
           │              │              │
    Round 2: Refine     Refine        Refine
           │              │              │
           └──────┬───────┴──────┬───────┘
                  │  Aggregate   │
                  ▼
            Final Answer
      (synthesized from all 3)
```

#### Checklist — Phase 3

- [x] Pool infrastructure (nodes can communicate via HivePoA coordinator)
- [x] RAG pipeline (each agent gets the same knowledge context)
- [ ] Build MoA coordinator endpoint in HivePoA
- [ ] Build "refine with context of other answers" prompt template
- [ ] Build aggregation/synthesis step
- [ ] Define convergence criteria (when to stop iterating)
- [ ] Benchmark: MoA with 3 agents vs best-of-3 vs single agent
- [ ] Latency budget: 2-round MoA should complete in <3 minutes
- [ ] Wire into tier system: Cluster mode auto-enables MoA for complex queries
- [ ] Dashboard: show "3 agents collaborated" in response metadata

---

## Phase 4: Sparse Upcycling + EMoE (REQUIRES MAJOR TRAINING)

**Goal:** Convert v5-think from dense to MoE. True elastic intelligence.
**Quality improvement:** +50-100% scaling range (k=2 on 1 GPU → k=8 on 8 GPUs).
**Mechanism:** Real mixture-of-experts with dynamic expert activation.

### Why This Is the Holy Grail

This is the ONLY approach where the model itself becomes genuinely smarter with
more GPU — not faster, not more candidates, but a fundamentally more capable
forward pass with more parameters active per token.

### The Science

**Sparse Upcycling** (Google, arXiv 2212.05055):
- Take a dense model's FFN layers
- Duplicate each into N experts (initialized from original weights + noise)
- Add a learned router network
- Continue training (~50% of original pretrain compute)
- Result: MoE model that outperforms both the dense original AND MoE trained from scratch

**EMoE** (arXiv 2509.21892):
- Train with stochastic co-activation sampling
- Router learns to handle variable k' (active experts) at inference
- Train with k=4, safely infer at k'=4 to k'=12
- More active experts = more parameters per token = smarter

**Qwen Proved It** (Qwen1.5-MoE-A2.7B):
- Upcycled from dense Qwen-1.8B
- 64 experts (4 active per token)
- Matched Qwen1.5-7B quality with only 2.7B active params
- 75% reduction in training cost vs from-scratch MoE

### The Architecture

```
v5-think (14B dense)
    │
    ▼ Sparse Upcycling
    │
v6-think-MoE (14B base + 8×14B-FFN experts = ~70B total, 14B active)
    │
    ▼ EMoE Training (variable k')
    │
Elastic Brain Checkpoint
    │
    ├── 1 GPU (k'=2):  14B active params → Solo quality
    ├── 4 GPUs (k'=4): 28B active params → Pool quality
    ├── 8 GPUs (k'=6): 42B active params → Enhanced quality
    └── 16+ GPUs (k'=8): 56B active params → Full Brain quality
```

### Prerequisites

- [ ] 40+ community GPUs available via HivePoA (for training compute)
- [ ] v5-think bf16 weights accessible on training cluster
- [ ] Training data: all 12,000+ solved examples + deep reasoning pairs as JSONL
- [ ] EMoE training recipe implemented (stochastic co-activation + router loss)
- [ ] vLLM with Expert Parallelism configured for serving

### Training Plan (When Prerequisites Met)

1. **Upcycle v5-think to 8-expert MoE** (~1 week of GPU-hours on 40+ GPUs)
   - Duplicate each FFN into 8 copies with random noise
   - Initialize router with uniform weights
   - Continue training on full dataset (all JSONL pairs + pretraining data)

2. **Apply EMoE recipe** (~1 week additional)
   - Stochastic co-activation during training (randomly activate 2-6 experts)
   - Hierarchical router loss for balanced expert utilization
   - Validate k' range: test k'=2 through k'=8

3. **Re-fine-tune domain knowledge** (~2-3 days)
   - Apply v5-think's training data to the upcycled model
   - Verify 60-probe eval scores match or exceed v5-think baseline
   - Layer 3 criteria: must not regress >1% on any domain

4. **Deploy as elastic checkpoint** (~1 day)
   - Serve via vLLM with Expert Parallelism
   - Wire k' selection into tier_autoscaler
   - Validate quality at each k' level

#### Checklist — Phase 4

- [x] bf16 golden chain maintained (source of truth for upcycling)
- [x] Training pipeline exists (train_v5.py, safe_merge.py, consolidation)
- [x] 14-layer defense stack for training safety
- [x] 60-probe eval gate (must pass after upcycling)
- [x] HivePoA distributed compute infrastructure
- [x] elastic_moe.py exists (needs EMoE training integration)
- [ ] Community GPU pool reaches 40+ GPUs (HivePoA milestone)
- [ ] Implement sparse upcycling script (FFN duplication + router init)
- [ ] Implement EMoE training recipe (stochastic co-activation)
- [ ] Run upcycling training job on community GPU cluster
- [ ] Validate k' range (2-8) with 60-probe eval at each level
- [ ] Re-fine-tune domain knowledge post-upcycling
- [ ] Deploy elastic checkpoint via vLLM EP
- [ ] Wire k' selection into tier_autoscaler.py
- [ ] Benchmark: quality curve from k'=2 to k'=8
- [ ] Update score_ledger.json with per-k' scores

---

## Cross-Phase Integration

### How Phases Stack

The phases are additive — each builds on and enhances the previous:

```
Phase 1 alone:     v5-think Q5_K_M, 8K context
                   Quality: 94.65% (baseline)

Phase 1+2:         v5-think FP16, 32K context, best-of-4
                   Quality: ~97%+ (higher precision + longer RAG + filtered candidates)

Phase 1+2+3:       v5-think FP16, 32K context, 3-agent MoA consensus
                   Quality: ~98%+ (agent collaboration exceeds individual)

Phase 1+2+3+4:     v6-MoE k'=8, 64K context, 3-agent MoA consensus
                   Quality: maximum achievable (elastic brain + full RAG + consensus)
```

### RAG Is the Constant

Across ALL phases, the RAG notebook stays the same:
- 12,062+ sections, growing daily (faucet always on)
- Language-aware routing
- Cross-encoder reranking
- Verified solved examples with quality gates

The brain gets smarter. The notebook stays organized. The plumber upgrades
from working solo to having a crew, but his reference notebook is always
with him.

### Tier Mapping

| Tier | GPUs | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|------|---------|---------|---------|---------|
| **Solo** | 1 | Q5_K_M, 8K ctx | N=1 (no spare GPU) | N/A | k'=2 |
| **Pool** | 2-4 | FP16, 32K ctx | Best-of-N (N=GPU count) | N/A | k'=4 |
| **Pool+** | 5-15 | FP16, 64K ctx | Best-of-5 | 3-agent MoA | k'=6 |
| **Cluster** | 16+ | FP16, 128K ctx | Best-of-8 | 5-agent MoA | k'=8 |

---

## Metrics & Quality Tracking

### Per-Phase Quality Benchmarks

Each phase must demonstrate measurable improvement:

| Metric | How Measured | Target |
|--------|-------------|--------|
| **Probe score** | 60-probe regression_eval.py | Must not regress >1% |
| **Code verification rate** | % of responses that compile+run | Higher is better |
| **Best-of-N lift** | Quality delta between N=1 and N=best | >10% on complex queries |
| **MoA consensus quality** | Blind comparison: single vs consensus | Consensus preferred >60% |
| **Elastic k' curve** | Probe scores at each k' level | Monotonically increasing |

### Dashboard Requirements

- Live tier display: "Solo (1 GPU)" / "Pool (4 GPUs, best-of-4)" / "Cluster (MoA active)"
- Quality indicator: confidence band from RAG + verification status
- GPU count + utilization per node
- Throughput: queries/minute across pool
- RAG stats: sections searched, examples matched, language routing hits

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Phase 2 best-of-N doesn't improve quality | Low | Medium | Verification catches bad candidates; even N=2 should help |
| Phase 3 MoA adds latency without quality | Medium | Medium | Set latency budget (3 min max); fall back to best-of-N |
| Phase 4 upcycling destroys v5-think knowledge | High | Critical | Keep v5-think bf16 as golden backup; must pass 60-probe gate |
| Phase 4 requires more compute than available | Medium | High | Start with 4 experts instead of 8; reduce training scope |
| GPU churn destabilizes pool during inference | Medium | Medium | 7-day cooldown + hysteresis already implemented |
| Ollama competes for GPU with llama-server | Known | High | LLM_BACKEND=llama-server bypasses Ollama (already fixed) |

---

## File Map

| Phase | Key Files | Status |
|-------|-----------|--------|
| 1A | `models/deploy/*.gguf`, `safe_merge.py` | Partially done |
| 1B | `config.py` (LLM_CTX_SIZE), `chat.py` (budget_context) | Live |
| 2 | `distributed_inference.py`, `app.py` (compute endpoints) | Infrastructure ready |
| 3 | New: `hiveai/compute/mixture_of_agents.py` | Not started |
| 4 | `elastic_moe.py`, `train_v5.py`, `tier_autoscaler.py` | Structure exists |
| All | `vectorstore.py`, `chat.py` (RAG pipeline) | Live, hardened |
| All | `community_coordinator.py`, `tier_autoscaler.py` | Live |

---

## Timeline

| Phase | Duration | Prerequisites | Outcome |
|-------|----------|---------------|---------|
| **Phase 1** | 1-2 weeks | v5-think bf16 (have it) | Multiple quant levels + context scaling |
| **Phase 2** | 2-3 weeks | Pool mode working (testing now) | Best-of-N with verification |
| **Phase 3** | 3-4 weeks | Phase 2 + 5+ pool nodes | Multi-agent consensus |
| **Phase 4** | 2-3 months | 40+ community GPUs | True elastic MoE brain |

**Total to elastic MVP (Phase 1-3):** 6-9 weeks, zero model training.
**Total to true elastic brain (Phase 4):** 4-6 months, requires community GPU cluster.

---

## Summary

The Elastic Brain is not one technique — it is four stacked phases that each make the
system genuinely smarter with more GPU. Each phase is independently valuable:

- **Phase 1**: Same brain, sharper glasses. Works today.
- **Phase 2**: Same brain, picks the best answer from multiple attempts. Cheap and effective.
- **Phase 3**: Same brain times N, they debate. Exceeds any single model.
- **Phase 4**: Brain physically grows with GPU count. The holy grail.

The faucet (RAG) runs through all phases. The notebook grows every day. The plumber
gets smarter tools, then a team, then a bigger brain — in that order.
