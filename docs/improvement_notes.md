# HiveAI Improvement Notes

Research findings and actionable ideas for future upgrades.

---

## 1. Reasoning Distillation (from Jackrong's Qwen3.5-27B-Claude-Distilled)

**Source**: https://huggingface.co/Jackrong/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled

**What they did**: Fine-tuned Qwen3.5-27B on ~4,000 Claude 4.6 Opus reasoning traces using LoRA + SFT (Unsloth + Transformers 5.2.0 — same stack as us).

**Key technique**: `train_on_responses_only` with loss computed specifically over `<think>{reasoning}</think>{answer}` sequences. This teaches the model HOW to reason, not just what to answer.

**Datasets used**:
- [Opus-4.6-Reasoning-3000x-filtered](https://huggingface.co/datasets/nohurry/Opus-4.6-Reasoning-3000x-filtered) — 3,000 heavily curated reasoning trajectories
- [claude-4.5-opus-high-reasoning-250x](https://huggingface.co/datasets/TeichAI/claude-4.5-opus-high-reasoning-250x) — 250 high-intensity reasoning instances
- [Qwen3.5-reasoning-700x](https://huggingface.co/datasets/Jackrong/Qwen3.5-reasoning-700x) — 700 curated step-by-step samples

**Results**: 9+ minutes autonomous coding, self-correction, proper tool waiting, auto-documentation. Base model stalled/froze on same tasks.

**Actionable for us**:
- Generate Claude-quality `<think>` block reasoning for our hardest training pairs
- Use those public reasoning datasets to supplement our training data
- Quality of reasoning traces matters more than quantity (~4,000 beat larger noisy datasets)

---

## 2. Agent Skills — Zero-Training Knowledge Transfer (from HuggingFace "Upskill")

**Source**: https://huggingface.co/blog/upskill

**What they did**: Instead of fine-tuning, package expertise as "agent skills" — a ~500 token markdown file with domain instructions + test cases. Inject as context at inference time.

**Results**: GLM-4.7-Flash (tiny model) went from 40% to 85% accuracy on CUDA kernel writing with just a skill file in context. No training needed.

**How it works**:
1. Expert model (Claude Opus) solves a domain task, generates a trace
2. `upskill generate` distills the trace into a compact SKILL.md (~500 tokens)
3. SKILL.md gets injected as system context for any model
4. `upskill eval` measures "skill lift" (accuracy with vs without skill)

**Skill file structure**:
```
./skills/{skill-name}/
  SKILL.md           # ~500 tokens of domain instructions
  skill_meta.json    # Test cases for evaluation
```

**Tool**: `pip install upskill` (open source CLI)

**Actionable for us**:
- Create Hive blockchain agent skills (SDK usage, custom_json ops, economics, etc.)
- Create coding best-practices skills for weak languages (Rust, Go, C++)
- Skills complement LoRA: LoRA = permanent weight changes, Skills = per-session context injection
- Can test skills immediately without any training time

---

## 3. Combined Strategy for HiveAI

```
Qwen2.5-Coder-14B (frozen base)
  +-- v7+ LoRA (baked-in knowledge from training)
  +-- Agent Skills (injected at inference time)
```

**Priority upgrades**:
1. [HIGH] Create Hive agent skills for immediate quality boost (no training needed)
2. [HIGH] Generate Claude-quality reasoning traces for v8 training data
3. [MED] Incorporate public reasoning datasets (Opus-4.6-Reasoning-3000x-filtered)
4. [LOW] Evaluate if Qwen3.5-27B (with Q4 quant) fits in 16GB VRAM as future base upgrade

---

## 4. Quantization-Aware Distillation (QAD) — Lessons from AliesTaha / Qwen Image Team

**Source**: https://x.com/AliesTaha/status/2030074784894308770

**What they did**: Quantized EVERY linear layer in a 20B-param Qwen Image diffusion model to FP4 (4-bit). Used a teacher-student distillation setup where the BF16 teacher guides the FP4 student. Only 1 out of 7 team members could tell the quantized output from full precision.

**Key findings directly applicable to our LoRA training:**

### Optimizer choice is EVERYTHING
- **4.52 dB swing** from optimizer alone (same architecture, same data)
- Naive Adam + constant LR = destructive (17.82 dB, worse than no training)
- **AdamW + cosine schedule + 5% warmup + weight decay** = best results (22.34 dB)
- We currently use AdamW with cosine in v7 — this validates our choice
- **Lesson**: If v8 training seems to not converge, check optimizer FIRST

### Freezing layers beats training everything
- Freezing MLP layers and only training attention/modulation: 22.34 dB
- Training everything: 19.12 dB (WORSE by 3.2 dB!)
- The reason: gradient noise accumulates through many layers (STE chain)
- **Actionable for us**: In v8, experiment with freezing some LoRA layers. Don't assume training all layers is optimal. Try `modules_to_save` selectively.

### Pre-compute teacher outputs offline
- Running teacher+student every step = 2x memory, 2x time
- Solution: Run teacher ONCE on all data, save intermediate outputs to disk
- Then train student against saved targets — single forward pass per step
- **Actionable for us**: For KL distillation in v8, pre-generate Claude outputs for all training prompts, save to JSONL, then train against them. We're already doing this with our training pairs!

### Intermediate layer matching >> output-only matching
- MSE on just the final output: decent but not great
- MSE on ALL 60 intermediate layer outputs: massive quality jump
- "You cannot use 1 MSE function... you have to use 61 MSE functions"
- **Actionable for us**: If we ever do true distillation (not just SFT), match intermediate hidden states, not just the final token logits. This is a research direction for v9+.

### Loss function matters more than you think
- Latent MSE: 22.34 dB
- Velocity MSE (mathematically equivalent!): 18.27 dB
- **4 dB gap from the same information, different formulation**
- **Lesson**: If training isn't converging, try reformulating the loss. KL vs MSE vs Huber can make or break a run.

### Quantization-specific but conceptually universal
- Asymmetric quantization has "frozen bias drift" — bias computed at init drifts during training
- Rankings INVERT between PTQ and QAD (best static config != best trained config)
- **Lesson**: Don't assume the best starting point gives the best endpoint. Test the trained result.

### Numbers that matter
- 228 experimental runs to find the right config
- 529 total GPU-hours across all ablations
- The winning config was NOT the most complex — it was simple MSE + frozen MLP + AdamW + cosine

---

## 5. Key Principle: "Robin Hood"

Use expensive frontier models (Claude) to generate high-quality reasoning traces and skills, then deploy with cheap/local models. The expensive model does the thinking ONCE, the local model benefits FOREVER.

---

## 6. Always-On Memory Consolidation (from Google's Always-On Memory Agent)

**Source**: https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent

**What they did**: Three-agent system (Ingest → Consolidate → Query) that runs continuously. The key innovation is the **ConsolidateAgent** — a background process that periodically reviews all stored memories, finds cross-cutting connections, generates meta-insights, and compresses redundant information. Mimics human sleep-based memory consolidation.

**Architecture**: No vector DB, no RAG. Just SQLite with structured metadata (entities, topics, importance scores 0-1). Simple beats complex.

**Actionable for HiveAI**:
- **Auto-curation agent**: Background job reviews past model responses, scores quality, identifies patterns where the model fails, auto-generates training pair candidates
- **Importance scoring for training data**: Score each pair 0-1 for difficulty/novelty. Drop easy/redundant pairs. Keep hard/unique ones. This is automated `mine_failures.py`
- **Consolidation for agent skills**: Periodically review conversation logs, extract recurring domain patterns, auto-update SKILL.md files
- **Self-improving loop**: Model serves users → responses are scored → failures become training data → retrain → model improves → cycle repeats

---

## 8. Recursive Language Models (RLMs) — Solving Context Rot

**Source**: MIT research by Alex L. Zhang, Tim Kraska, Omar Khattab (March 2026)
**Paper**: https://arxiv.org/abs/2512.24601v1
**Library**: https://github.com/alexzhang13/rlm (`pip install rlms`)

**The Problem (Context Rot)**: Even when context windows aren't exceeded, LLM accuracy degrades on reasoning tasks as input length grows. Attention mechanisms dilute focus; the model gets "dumber" with more context. This affects counting, classification, and multi-hop reasoning over large inputs.

**The Fix**: Separate query from context. Context lives in an external REPL environment. Model gets tools (peek, grep, partition, recursive_call) and discovers the decomposition strategy dynamically — no hardcoded workflow.

**Key Results**:
- Accuracy holds regardless of document size (no context rot)
- Handles inputs up to 100x beyond context windows
- +34 points vs base GPT-5-mini on retrieval-heavy benchmarks (OOLONG)
- No special training needed — frontier models already know how to grep/partition
- Fully interpretable (every tool call is logged)

**Actionable for HiveAI**:
- **NOW**: Add query-focused context filtering to chat pipeline (lightweight RLM). Instead of dumping all 12 sections into the prompt, filter sections by query relevance and budget total context to prevent dilution.
- **NOW**: Create agent skill teaching the model about RLM patterns for architecture queries.
- **LATER**: Full RLM integration for Phase 5 consolidation (analyzing batches of stored responses recursively).
- **LATER**: Benchmark RLM decomposition vs current RAG on our growing knowledge base.

**Limitations**:
- Latency: recursive calls add seconds-to-minutes per query
- Weak models produce bad decompositions (bad regex → bad filtering → amplified errors)
- Not worth it for short contexts (<10K tokens)
- Text-focused; current implementations don't handle non-text data

**Comparison**:
| Approach | Scales | Best For |
|----------|--------|----------|
| RAG | Lookup speed | Factual Q&A, docs search |
| Agents | Task complexity | Multi-step workflows |
| Chain-of-thought | Reasoning depth | Math, logic, short context |
| **RLMs** | Context breadth | Large document analysis, counting, multi-hop |

---

## 9. Meta-Lessons Across All Research

1. **Quality > quantity** in training data (Jackrong: 4K pairs beat larger noisy sets)
2. **Optimizer config can make or break training** (QAD: 4.52 dB from optimizer alone)
3. **Don't train everything — freeze what's already good** (QAD: 3.2 dB improvement)
4. **Pre-compute expensive operations offline** (QAD: teacher outputs, Upskill: agent traces)
5. **Test the trained result, not just the starting point** (QAD: rankings invert)
6. **Simple approaches often win** (QAD: simple MSE beat complex KL; Upskill: 500 tokens of context beat fine-tuning)
7. **Separate query from context** (RLM: context in environment, model interacts through tools — prevents attention dilution)
8. **Let the model decide decomposition** (RLM: emergent strategy beats scripted workflows — the model adapts to data structure)
