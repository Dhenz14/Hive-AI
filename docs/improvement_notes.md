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

## 4. Key Principle: "Robin Hood"

Use expensive frontier models (Claude) to generate high-quality reasoning traces and skills, then deploy with cheap/local models. The expensive model does the thinking ONCE, the local model benefits FOREVER.
