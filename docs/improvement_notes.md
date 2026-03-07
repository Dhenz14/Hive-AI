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

## 9. Qwen-Agent Framework — Architecture Patterns for Local Agents

**Source**: https://github.com/QwenLM/Qwen-Agent (Alibaba/Qwen team, Apache 2.0)

**What it is**: Production agent framework powering Qwen Chat. Multi-agent orchestration, tool registry, parallel document QA, function calling templates.

### Virtual Memory Pattern (IMPLEMENTED)
The `VirtualMemoryAgent` prepends retrieved knowledge into the **system message** instead of appending to user messages. Transformer attention weights the start of context more heavily, so putting knowledge in system position = better recall for the same token budget.

**Applied to HiveAI**: Restructured both sync and streaming chat endpoints to use rich system prompts (instructions + skills + knowledge) with clean user messages (conversation + question). Previously everything was in a single user blob with a generic system prompt.

### LLM-Powered Keyword Extraction (FUTURE)
`GenKeyword` agent: dedicated LLM call generates bilingual search keywords + semantically related terms not in the original query. User asks "core formula" → LLM generates `["formula", "equation", "derivation"]`. Much better retrieval than naive word-splitting.

**Trade-off**: Extra LLM roundtrip (~1-2s latency). Worth it for knowledge-heavy queries, overkill for simple chat. Could implement as optional for "complex" difficulty queries only.

### Parallel Document QA (FUTURE — Phase 5)
`ParallelDocQA`: chunks documents → spawns parallel worker agents (ThreadPoolExecutor with jitter) → each worker answers independently → filters "none" responses → RAG retrieves from combined results → summary agent synthesizes final answer.

This is the RLM pattern (see Section 8) but production-grade. Key implementation details:
- `PARALLEL_CHUNK_SIZE = 1000` tokens per chunk
- `MAX_RAG_TOKEN_SIZE = 4500` for retrieval results
- Workers return `{"res": "ans"|"none", "content": "..."}` JSON
- Up to 4 retries if all workers return "none" (needed for smaller models)
- Jitter between thread submissions to avoid rate limits

### Tool Registry Decorator Pattern (REFERENCE ONLY)
```python
@register_tool('my_tool')
class MyTool(BaseTool):
    description = '...'
    parameters = [{'name': 'prompt', 'type': 'string', 'required': True}]
    def call(self, params, **kwargs): ...
```
Global `TOOL_REGISTRY` dict. Clean but our regex-based skill loader works well for markdown injection without needing Python tool classes. Not worth migrating.

### FnCallAgent Loop Pattern (REFERENCE)
Simple while loop with safety cap: `while num_calls > 0: call_llm → detect_tool → call_tool → append_result → yield`. `MAX_LLM_CALL_PER_RUN` prevents infinite loops. Uses `<tool_call>` XML tags. The "nous" template is Qwen's default for function calling.

### Key Takeaway
The biggest win from Qwen-Agent is **knowledge positioning** — where you place retrieved context in the prompt matters as much as what you retrieve. System position > user position for attention-critical information.

---

## 10. LangWatch — LLM Evaluation Patterns

**Source**: https://github.com/langwatch/langwatch (Apache 2.0)

**What it is**: LLM evaluation and monitoring platform. The gems are in their evaluator implementations, not the platform itself.

### LLM-as-Judge with Forced Function Calling (FUTURE)

The key pattern: instead of asking the LLM to output a score as text (unreliable parsing), use `tool_choice` to **force** structured output:

```python
tools=[{
    "function": {
        "name": "evaluation",
        "parameters": {
            "properties": {
                "reasoning": {"type": "string"},  # think BEFORE scoring
                "final_score": {"type": "number"}
            },
            "required": ["reasoning", "final_score"]
        }
    }
}],
tool_choice={"type": "function", "function": {"name": "evaluation"}}
```

**Why it matters**: The `reasoning` field forces chain-of-thought BEFORE the score. The model must explain its evaluation before committing to a number. This produces better-calibrated scores than "rate this 0-10" in plain text.

**Applicable to HiveAI**: Could improve `run_eval.py` scorer reliability. However, llama-server's `tool_choice` support needs testing first. Fallback: use structured `<reasoning>...</reasoning><score>...</score>` XML tags in the prompt (no function calling needed).

### Valid Format Evaluator (REFERENCE)

Uses actual parsers for format validation: `ast.parse()` for Python, `json.loads()` for JSON, `sqlglot.parse()` for SQL. Our v3 scorer already does similar structural analysis for non-Python code. Clean pattern to reference if we expand format checking.

### Off-Topic Detection Guardrail (FUTURE)

LLM-based intent classification with allowed topics list. Define topics → model classifies → reject if "other". Could prevent HiveAI from going off-rails. Low priority — our knowledge-gated RAG naturally constrains topics.

### Embedding Similarity Guardrail (FUTURE)

Cosine similarity between output and target values to detect copypasta responses or off-topic drift. Uses embedding model for semantic comparison. Could be useful for detecting when LoRA training produces repetitive outputs.

### Composable Evaluator Framework (REFERENCE)

`BaseEvaluator[Entry, Settings, Result]` with typed generics. Each evaluator is independent with a clean `evaluate(entry) -> result` interface. Our eval pipeline is simpler and doesn't need this abstraction yet, but worth noting for when we scale up evaluation.

### Key Takeaway

The biggest win from LangWatch is **"reasoning before scoring"** — forcing the evaluator to explain its reasoning before committing to a score produces better-calibrated evaluations. This applies whether using function calling or structured XML prompts.

---

## 11. Meta-Lessons Across All Research

1. **Quality > quantity** in training data (Jackrong: 4K pairs beat larger noisy sets)
2. **Optimizer config can make or break training** (QAD: 4.52 dB from optimizer alone)
3. **Don't train everything — freeze what's already good** (QAD: 3.2 dB improvement)
4. **Pre-compute expensive operations offline** (QAD: teacher outputs, Upskill: agent traces)
5. **Test the trained result, not just the starting point** (QAD: rankings invert)
6. **Simple approaches often win** (QAD: simple MSE beat complex KL; Upskill: 500 tokens of context beat fine-tuning)
7. **Separate query from context** (RLM: context in environment, model interacts through tools — prevents attention dilution)
8. **Let the model decide decomposition** (RLM: emergent strategy beats scripted workflows — the model adapts to data structure)
9. **Knowledge positioning matters** (Qwen-Agent: system message position gets stronger attention than user message — same content, better recall)
10. **Force reasoning before scoring** (LangWatch: structured "reasoning" field before "score" field produces better-calibrated LLM-as-judge evaluations)
11. **Compaction is a core primitive** (Codex CLI: intelligent summarization of older conversation turns preserves continuity at fraction of token cost — naive truncation loses state, full history is unsustainable)

---

## 12. Context Compaction — Architecture Patterns (from OpenAI Codex CLI Research)

**Source**: Kangwook Lee's reverse-engineering of OpenAI Codex CLI compaction (March 2026)

### Implemented: LLM-Based Conversation Compaction (DONE)

When chat history exceeds 10 messages, older turns are summarized via LLM into a structured handoff blob. Last 4 messages stay verbatim. Compaction results are cached by content hash to avoid redundant LLM calls. See `hiveai/chat.py:compact_conversation()`.

### Dual-Path Compaction Architecture (REFERENCE)

Codex CLI uses two paths: open-source (local LLM summarizer with visible prompts) and proprietary (server-side encrypted blob). Our implementation follows the open path — full transparency, no encryption needed since we're local-only.

### Structured Handoff Prompts (IMPLEMENTED)

The key insight: don't just summarize — prepend a structured "handoff" that frames the compact summary for the next model turn. This preserves intent, decisions, and task state across compaction boundaries. Our implementation uses `COMPACTION_HANDOFF` in `hiveai/llm/prompts.py`.

### Multi-Turn Injection via Compacted Memory (FUTURE SECURITY)

Compacted memory is an attack surface for indirect prompt injection. An adversary could craft messages that, when compacted, inject instructions into the summary. Mitigation: validate compaction output for instruction-like patterns, or use a separate model for compaction vs. generation. Low priority for local-only deployment but worth noting for any future API exposure.

### Encrypted Blob Pattern (REFERENCE ONLY)

Server-side compaction returns AES-encrypted blobs — keys stay on server. Client never sees the summary. Useful for multi-tenant SaaS where you don't want clients to see internal reasoning. Not applicable to our local-only architecture.

### Compaction Quality Metrics (FUTURE)

Track compaction effectiveness: token savings ratio, continuity score (does the model maintain context after compaction?), information loss (are key decisions preserved?). Could be integrated into our eval harness as a long-conversation test suite.

---

## 13. Unsloth Optimization Patterns (March 2026)

**Source**: https://unsloth.ai/docs/models/qwen3.5/fine-tune + Unsloth GitHub

### Implemented: Zero Dropout for Unsloth Kernels (DONE)

Changed `lora_dropout` from 0.1 to 0.0 in `scripts/train_v5.py`. Unsloth's Triton kernels are specifically optimized for zero dropout — all their official examples use `dropout=0`. Non-zero dropout adds computational overhead without clear benefit when using Unsloth's fused kernels.

### Implemented: Chat Template / EOS Token Verification (DONE)

Verified our LoRA deployment uses correct ChatML format (`<|im_start|>` / `<|im_end|>`) with EOS token `<|im_end|>` (id 151645). Unsloth warns: "If the exported model behaves worse in another runtime, the most common cause is wrong chat template / EOS token at inference time." Our setup is correct.

### QLoRA Warning for Qwen3.5 (REFERENCE)

Unsloth explicitly warns: "It is not recommended to do QLoRA (4-bit) training on the Qwen3.5 models due to higher than normal quantization differences." We use Qwen 2.5 Coder with bf16 LoRA (not QLoRA), so this doesn't apply, but keep in mind if upgrading base model to Qwen 3.5.

### GRPO — Group Relative Policy Optimization (FUTURE)

Next frontier after SFT. Instead of just showing the model good outputs, generate multiple outputs per prompt and train on relative quality rankings. Unsloth supports GRPO with 7x longer context and 50% less VRAM. Also supports GSPO, DrGRPO, and DAPO variants. Would require:
- A reward model or LLM-as-judge scorer
- Multiple candidate generation per training prompt
- Significantly more compute than SFT
- Best applied after SFT establishes baseline quality

### Vision Fine-Tuning (FUTURE)

`FastVisionModel` supports selective fine-tuning of vision layers, language layers, attention, and MLP independently. Could be useful for:
- Training the model to understand architecture diagrams
- Processing screenshots of code/errors in the knowledge pipeline
- Multi-image understanding for documentation analysis

Requires `UnslothVisionDataCollator` and specific SFTConfig flags:
```python
remove_unused_columns = False
dataset_text_field = ""
dataset_kwargs = {"skip_prepare_dataset": True}
```

### Dynamic 4-bit Quantization (FUTURE)

Uses <10% more VRAM than BnB 4-bit but recovers ~70% of accuracy lost in standard quantization. Could enable running larger base models (27B+) on our 16GB GPU. Requires testing against our eval harness.

### MoE Training Optimization (REFERENCE)

12x faster MoE training with 35% less VRAM and 6x longer context. Router-layer fine-tuning disabled by default for stability. Relevant if we upgrade to Qwen3.5-35B-A3B (MoE) or similar.
