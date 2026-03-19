# HiveAI Project Rules

## Core Philosophy — Non-Negotiable

**Greatness is taken, not given.** This project holds itself to the highest standard:

- **1% regression threshold is absolute** — never lower it, never "round down," never call it noise. If a domain drops >1%, the cycle fails. Period.
- **Never settle for "good enough"** — if something can be better with zero downside, we do it. Every time.
- **Iterate until solved** — when something fails, we diagnose, fix, and re-run. We don't lower the bar, we raise our game.
- **Zero information loss** — every domain must maintain or improve after every training cycle. No exceptions, no "noise tolerance."
- **Ship quality, not excuses** — if a feature is broken, fix it before moving on. Don't paper over problems.

## Context Management

Context is your most important resource. Proactively use subagents (Agent tool) to keep exploration, research, and verbose operations out of the main conversation.

**Default to spawning agents for:**
- Codebase exploration (reading 3+ files to answer a question)
- Research tasks (web searches, doc lookups, investigating how something works)
- Code review or analysis (produces verbose output)
- Any investigation where only the summary matters

**Stay in main context for:**
- Direct file edits the user requested
- Short, targeted reads (1-2 files)
- Conversations requiring back-and-forth
- Tasks where user needs intermediate steps

**Rule of thumb:** If a task will read more than ~3 files or produce output the user doesn't need to see verbatim, delegate it to a subagent and return a summary.

## Linux-Only Execution (CRITICAL)

**ALL operations run in WSL (Ubuntu-24.04). Windows is only for the Flask web UI.**

- Training, merging, quantizing, eval, llama-server — ALL run in WSL
- **NEVER** run model operations, training, or llama-server on Windows
- **NEVER** copy GGUFs to Windows — serve directly from WSL via `wsl.exe` or WSL llama-server
- **llama-server runs in WSL**: `/opt/hiveai/llama-cpp-build/build/bin/llama-server` (CUDA, native Linux)
- Flask app runs on Windows only because it serves the web UI — it calls llama-server via HTTP (localhost:11435)
- Source of truth for ALL files: `/opt/hiveai/project/` in WSL
- Windows `c:\Users\theyc\HiveAi\Hive-AI\` is the git repo for code edits only — sync scripts to WSL before running

### Auto-shop: Permanent tool cache
- All llama.cpp binaries cached at `/opt/hiveai/tools/` and `/opt/hiveai/llama-cpp-build/`
- `scripts/restore_llama_cpp.sh` auto-restores if `/tmp` gets wiped
- HF model cache at `/root/.cache/huggingface/hub/` — never needs re-download
- bf16 golden chain at `/opt/hiveai/project/models/training/` — permanent source of truth

## Disk Hygiene (CRITICAL)

### Never use Downloads folder
- **NEVER** reference `C:\Users\theyc\Downloads` or `/mnt/c/Users/theyc/Downloads` in any source file, config, or script
- Downloads is for temporary files and installers — NOT project data
- All project data lives under WSL `/opt/hiveai/project/`

### Model file management
- **WSL only**: All models live in `/opt/hiveai/project/models/` — no GGUFs on Windows
- **Delete failed experiments immediately** — do not leave broken/superseded model directories lying around
- Never save duplicate GGUFs (BF16, -fixed, -clean variants). One working GGUF per quant type is enough
- Keep max 2 bf16 checkpoints (original-bf16 + latest), max 3 GGUFs

### WSL2 vhdx management
- WSL2 ext4.vhdx **only grows, never shrinks automatically**
- After deleting large files in WSL, ALWAYS compact: `wsl --shutdown && diskpart /s scripts/compact_wsl.txt`
- Run `python scripts/disk_hygiene.py` periodically to check for bloat

### Caches to clear periodically
- `~/.cache/huggingface/hub/` — re-downloadable model cache
- `~/AppData/Local/pip/cache/` — pip package cache
- `~/AppData/Local/Temp/wsl-crashes/` — WSL crash dumps from segfaults

## Daily Learning Architecture — 4 Layers (Strategic Pivot, 2026-03-14)

**v5-think (94.65%) is FROZEN. Do not micro-train. Knowledge growth happens via RAG, not weights.**

The golden chain (sequential LoRA merge) hit its architectural ceiling. Going from 94% → 96%+ via
more SFT/merge cycles is the wrong tool. The product value is in the application layer.

- **Layer 0: Core Brain** — Frozen v5-think. Stable reasoning/coding core. Do not touch.
- **Layer 1: RAG/Retrieval** — Where the system learns every day. 928 BookSections enriched with
  contextual retrieval prefixes (Anthropic technique, 35-67% fewer retrieval failures). Hybrid search
  (BM25+semantic) with MMR diversity reranking (λ=0.7). Cross-encoder reranker (bge-reranker-v2-m3)
  actively filters low-confidence sections (suppress < 0.02) and boosts high-confidence ones (> 0.20).
  Verified chat responses auto-promote to retrievable BookSections. Skills, golden books, solved
  examples. No retraining needed.
- **Layer 2: Skill Buffer** — Verified training pairs accumulate passively from chat. NOT immediate
  training. Accumulate until repeated miss + verifiable + large headroom.
- **Layer 3: Rare Promotion** — Event-driven training only. ALL 4 conditions must be met:
  1. Repeated miss in real use (not one-off)
  2. Retrieval is too slow or insufficient (RAG can't cover it)
  3. Executable eval exists (compile/test/type-check, not keyword scoring)
  4. Big expected gain (>3% domain improvement)
  When Layer 3 fires, it uses community GPUs (HivePoA) for large-batch training, not local micro-cycles.

**Training policy**: Do NOT train because the model saw something new once. Train only when all 4
conditions align. The golden chain stays alive as a precision instrument, not the main roadmap.

## Layer 3: Continual Learning Pipeline (Reserved for Rare Promotion Events)

**WARNING: This pipeline is NOT the daily workflow. It executes only when Layer 3 criteria are met.
v5-think is frozen. The micro-training flywheel below is historical context (how v5-think was built)
and reference for the next Layer 3 event.**

**Architecture**: Train small LoRA → merge permanently into base → consolidate → eval → promote.
Knowledge stacks like legos — once merged, it can never be lost.
**12-layer defense** (6 weight-level + 6 representation-level) ensures zero domain regression.

**v3.0 Root Cause**: v5-agentic failed from STYLE contamination (not weight interference).
Agentic data shifted output style from direct-code to verbose walkthrough, killing keyword-heavy
probes. v3.0 adds 6 new representation-level defenses targeting this exact failure mode.

**bf16 Golden Chain**: HF bf16 weights are the source of truth for ALL merges. GGUF is derived
from HF output via `convert_hf_to_gguf.py` + `llama-quantize`. This eliminates quantization drift
from repeated merges. After 100 merges, zero accumulated noise.

**One-command cycle**:
```bash
bash scripts/run_full_cycle.sh <domain> <data.jsonl> <version> [prev_version]
# Example: bash scripts/run_full_cycle.sh hive datasets/hive_data.jsonl v1-hive v1.0
# With style protection: STYLE_TOKENS=1 bash scripts/run_full_cycle.sh ...
```

**Micro-training flywheel** (500 pairs at a time, test between batches):
```bash
# Split large dataset into 500-pair batches
python scripts/batch_splitter.py datasets/thinking_all.jsonl --batch-size 500

# Train each batch, test, repeat
bash scripts/run_full_cycle.sh thinking datasets/thinking_all_batch1.jsonl v2-think v1-hive
bash scripts/run_full_cycle.sh thinking datasets/thinking_all_batch2.jsonl v3-think v2-think
# ...keep going until the "lobe" is done, then move to next domain
```

**Pipeline steps** (each script can also run independently):
0. Auto-sync from Windows git repo + CRLF fix (baked into run_full_cycle.sh)
1. `preflight_check.py` — Automated pre-flight validator (7 checks: HF offline, metadata, CRLF, disk, GPU, base model, cache)
2. `replay_sampler.py` — SuRe NLL-scored surprise replay + domain-balanced sampling
3. `train_v5.py` — Train domain LoRA (rank 4-8, LoRA+, all 7 modules, EWC, style tokens, probe-aware loss)
4. `safe_merge.py` — Golden chain HF merge + per-layer alpha + convert + quantize (~15 min)
5. `consolidation_train.py` — Post-merge stabilization (rank 2, LR/20, 1 epoch, 100% replay, all 7 modules)
6. `regression_eval.py` — 60 domain probes (10/domain), fail if any drops >0.03. `--quick` for original 18.

**14-Layer Defense Stack**:

*Weight-level (v2.0):*

1. **60-Probe Eval** — 10 probes/domain eliminates measurement noise (±1% vs old ±5.6%)
2. **EWC-LoRA** — Fisher Information penalty prevents training from overwriting existing knowledge. Currently DISABLED — STM+SDFT+KeepLoRA provide better protection without the 5-15 min Fisher computation.
3. **Domain Probe Callback** — Mid-training regression detection every N steps; auto-reduces LR or halts
4. **DELLA Pruning** — **BROKEN** — 3.33x rescaling corrupts PEFT merges. DO NOT USE until fixed.
5. **Orthogonal LoRA Init** — New LoRA initialized orthogonal to previous task's subspace via SVD
6. **Domain-Balanced Replay** — Equal samples/domain + adaptive ratio boost for dropped domains

*Representation-level (v3.0 — all opt-in via CLI flags):*
7. **Conditional Style Prefixing** (`--style-tokens`) — `<direct>`/`<agentic>` tokens route output style during HF training. **GGUF limitation:** style tokens only work in HF Python inference; GGUF tokenizer splits `<direct>` into 3+ tokens causing garbage. Do NOT use `--style-prefix` in GGUF evals.
8. **Pre-training Style Shift Analysis** (`style_shift_analysis.py`) — Predicts contamination BEFORE training using few-shot injection (zero VRAM)
9. **Probe-Aware Training Loss** (`--probe-aware`) — KL-div on cached base-model log-probs during training (steers, not just halts)
10. **Hidden State Anchoring** (`--hidden-anchor`) — MSE on layer 24 hidden states protects representation routing
11. **CURLoRA Initialization** (`--curlora-init`) — CUR decomposition replaces broken orthogonal SVD init
12. **Dataset Retagging** (`retag_style.py`) — Adds style field to JSONL for conditional routing

*Anti-forgetting (v5.0 — ON by default in pipeline):*
13. **STM: Selective Token Masking** (`--stm`) — Masks high-PPL tokens in training loss (labels→-100). High-perplexity tokens cause gradient-rank explosion that kills keyword probes even when CKA stays high. Per-token PPL computed via base model (adapters disabled) each micro-batch. Threshold default 2.5. (NeurIPS 2025, arXiv 2501.14315)
14. **SDFT: Self-Distillation Fine-Tuning** (`--sdft`) — Replaces additive KL penalty with mixing formula: `(1-alpha)*CE + alpha*KL`. Uses reverse KL (mode-seeking) so student stays near its own distribution. Prevents the off-policy drift that causes "healthy metrics but failed eval." Default alpha=0.7. (MIT Jan 2026, arXiv 2601.19897)

**Key flags in train_v5.py**:
- `--rank N` — LoRA rank override (4-8 for continual learning)
- `--lr FLOAT` — Direct LR override
- `--lora-plus` — B matrix gets 16x higher LR (LoRA+, arXiv 2602.04998)
- `--replay-dir PATH` — Mix replay data from per-domain JSONL files
- `--replay-ratio FLOAT` — Fraction of replay in training mix (default 0.25, auto-boosted to 0.40 for dropped domains)
- `--consolidation-only` — Consolidation mode (1 epoch, LR/10)
- `--base-model-hf PATH` — Train on merged HF checkpoint (for cycle 2+)
- `--ewc-lambda FLOAT` — EWC penalty weight (default 0.5, 0=disabled)
- `--no-ewc` — Disable EWC penalty entirely
- `--fisher-path PATH` — Load Fisher matrix from previous cycle
- `--prev-lora PATH` — Previous LoRA adapter for orthogonal initialization
- `--style-tokens` — Enable `<direct>`/`<agentic>` style token system (v3.0)
- `--style-mode MODE` — Default style for untagged data: "direct" or "agentic" (v3.0)
- `--probe-aware` — Enable probe-anchoring KL loss during training (v3.0)
- `--hidden-anchor` — Enable mid-layer hidden state MSE anchoring (v3.0)
- `--probe-weight FLOAT` — Base weight for probe KL loss (default 0.1) (v3.0)
- `--anchor-weight FLOAT` — Weight for hidden MSE loss (default 0.05) (v3.0)
- `--anchor-layer INT` — Layer to anchor (default 24 = middle of 48-layer Qwen2.5) (v3.0)
- `--curlora-init` — CUR decomposition init (replaces orthogonal SVD) (v3.0)
- `--stm` — Enable STM per-token PPL masking (ON by default in pipeline) (v5.0)
- `--stm-threshold FLOAT` — PPL threshold for token masking (default 2.5) (v5.0)
- `--sdft` — Enable SDFT self-distillation loss mixing (ON by default in pipeline) (v5.0)
- `--sdft-alpha FLOAT` — SDFT mixing weight: alpha*KL + (1-alpha)*CE (default 0.7) (v5.0)
- `--use-dora` — Enable DoRA (Weight-Decomposed LoRA), +1-4% over standard LoRA. Default: enabled (v6.0)

**Key flags in safe_merge.py**:
- `--della-drop FLOAT` — DELLA pruning drop rate (default 0.0). **WARNING: DELLA is BROKEN for PEFT merge — 3.33x rescaling corrupts model weights. DO NOT USE until fixed. Use 0.0.**

**Key flags in replay_sampler.py**:
- `--domain-balanced` — Equal samples per domain (prevents domain starvation)
- `--style-tag TEXT` — Tag replay output with style field (v3.0, default: "direct")

**Key flags in regression_eval.py**:
- `--quick` — Use original 18 probes (fast, ~6 min) vs default 60 probes (precise, ~20 min)
- `--style-prefix TEXT` — Prepend style token to system prompt for probes (v3.0). **WARNING: Do NOT use with GGUF inference — the GGUF tokenizer doesn't have custom style tokens, so `<direct>` tokenizes as 3+ regular chars causing garbage output. Style tokens only work in HF Python inference.**

**Key env vars in run_full_cycle.sh**:

- `STYLE_TOKENS=1` — Enable full v3.0 style protection pipeline (threads flags to all scripts)
- `STM=1` — Enable STM per-token PPL masking (ON by default) (v5.0)
- `SDFT=1` — Enable SDFT self-distillation loss mixing (ON by default) (v5.0)
- `STM=0 SDFT=0` — Disable v5.0 defenses (for debugging/comparison)

**Scripts**:
- `probe_library.py` — Central probe definitions (60 probes, 6 domains, importable)
- `domain_probe_callback.py` — TRL TrainerCallback for mid-training regression detection
- `style_shift_analysis.py` — Pre-training contamination predictor (v3.0)
- `retag_style.py` — Add style field to JSONL training data (v3.0)

**Post-training automations** (no manual steps needed):

- Auto-syncs scripts from Windows git repo + CRLF fix before every cycle
- Auto-normalizes `adapter_config.json` (fixes absolute cache paths → `Qwen/Qwen2.5-Coder-14B-Instruct`)
- Auto-converts LoRA adapter to GGUF (`adapter.gguf` alongside PEFT files)
- Auto-runs preflight checks before training starts
- Auto-cleans old model versions after promotion (keeps 3 GGUFs, 2 bf16 checkpoints)
- Auto-computes and saves Fisher matrix after training (for next cycle's EWC)
- Auto-detects previous LoRA and Fisher paths from prev_version

**Folder layout** (Layer 3 staging — NOT used daily, consulted only for rare promotion events):
- `models/deploy/current_base.gguf` — Active inference GGUF (v5-think, frozen)
- `replay/*.jsonl` — Per-domain replay buffers (Layer 3 staging)
- `datasets/*.jsonl` — Training data (Layer 3 staging)
- `score_ledger.json` — Historical scores across all versions
- `logs/` — Per-cycle training logs with rich checkpoint state for resume
- `loras/<version>/fisher.pt` — Fisher matrix for EWC (auto-generated)
- `style_shift_history.json` — Historical style shift scores for threshold calibration (v3.0)

**Fully automated when Layer 3 fires**: No manual steps. Scripts auto-sync from Windows, CRLF auto-fixed, preflight auto-runs.

**Training data format**: Standard instruction/input/output JSONL (NO metadata field). Optional "style" field for v3.0 routing.

**Domain-balanced training data** (`loras/training_data/new_pairs_merged_512.jsonl`):
512 targeted pairs generated to fix catastrophic forgetting in underfitted domains:
- C++ (100 pairs): RAII, move semantics, C++20/23, templates, concurrency, error handling, systems
- Rust (104 pairs): tokio, traits, ownership, unsafe/FFI, serde, design patterns, macros, perf
- Go (100 pairs): channels, workers, context, goroutine safety, HTTP, generics, DB, CLI
- JS/TS (108 pairs): advanced types, async patterns, Node.js, React, security, cross-language design
- Python (50 pairs): metaclasses, async, type system, performance, testing, architecture
- Algo & Reasoning (50 pairs): DP, graphs, data structures, debugging, system design (100% `<think>` blocks)
Individual files preserved as `new_pairs_*.jsonl` for traceability.

## Training UI (Forge Mind Page) — Layer 3 Only

The Forge page (`/forge`) provides training controls for **rare Layer 3 promotion events**.
This is NOT for daily use. v5-think is frozen. Use only when all 4 Layer 3 criteria are met.
- **Launch Micro-Training**: Domain selector, data path, version — launches `run_full_cycle.sh` in WSL tmux
- **Training Monitor**: Live pipeline stage indicator (7 steps), progress bar, loss display, log tail, stop button
- **Score Ledger**: Domain scores across all versions displayed in Eval Arena (`/eval`)
- **System Health Bar**: All pages show LLM/Embedding/GPU/Training status (polls every 30s)

**Training API endpoints**:
- `POST /api/lora/micro-train` — Launch training cycle in WSL tmux session
- `GET /api/lora/training-status` — Poll training progress (step, loss, stage, log tail)
- `POST /api/lora/stop-training` — Kill training tmux session
- `POST /api/lora/prepare-batches` — Split JSONL into 500-pair micro-training batches
- `GET /api/eval/ledger` — Return score_ledger.json for visualization

## Memory Reuse System (Promotion Bridge) — LIVE

**Status**: Proven (Gate 6 + Gate 10 PASS). Bridge is FROZEN — do not add features until Gate 11.

**How it works**: Verified chat responses that pass quality + complexity gates get promoted from
`TrainingPair` (training sink) → `BookSection` (retrieval-indexed, same BGE-M3 embedding space).
Promoted examples live in a synthetic GoldenBook ("Solved Examples :: Verified Code") and are
automatically retrieved by the RAG pipeline on similar future queries.

**Promotion gates** (all must pass):
- `AUTO_PROMOTE_MIN_QUALITY` ≥ 0.82
- `AUTO_PROMOTE_MIN_CODE_LINES` ≥ 5
- Verification must have run (compile/execute/assertions)
- Content-hash dedupe (SHA256 of normalized prompt + sorted code)

**Retrieval bonus**: +0.05 hybrid_score for `source_type == "solved_example"` on code queries.

**Reuse tracking** (`GET /api/memory/scoreboard`):
- Per-example: times_retrieved, verified_pass/fail, rank history, times_reused
- Aggregate: hit_rate, total_retrievals, total_verified_pass/fail
- Chat response trace fields: `solved_example_retrieved`, `solved_example_count`, `solved_example_ids`

**Config flags** (env vars):
- `AUTO_PROMOTE_VERIFIED=true` — Enable/disable promotion bridge
- `AUTO_PROMOTE_MIN_QUALITY=0.82` — Minimum quality score for promotion
- `AUTO_PROMOTE_MIN_CODE_LINES=5` — Minimum code lines for promotion

**Gate 11 (next milestone)**: Collect 5-10 promoted examples organically, prove repeated reuse
at scale (≥50% retrieved on relevant follow-ups, measurable verification wins, no noise explosion).

## 3 Gems — Layer 3 Intelligence (Phase 0-3) — STRUCTURALLY COMPLETE

Three systems that make the rare Layer 3 training loop smarter when it fires. They do NOT drive
daily learning (that's Layer 1 RAG). All structurally complete, all non-operative (behavior gates
OFF). Empirical validation blocked on real closed critique data from future Layer 3 events.

**GEM 3 — Weakness Trending + Probe Telemetry** (Phase 0+1, commit d364136):
- `scripts/weakness_trend.py` — Per-probe trend classification (declining/resistant/improving/stable)
- `scripts/probe_library.py` — 60 probes, 6 domains, versioned classifier (`WEAKNESS_CLASSIFIER_VERSION=1`)
- Fixes: failed-run baseline contamination, language hardcoding, eval_mode mixing

**GEM 1 — Critique Pattern Memory** (Phase 2, commit 0830250):
- `scripts/critique_memory.py` — Open/close/abandon lifecycle for training fix attempts
- BookSection rows with `source_type="critique_pattern"`, `embedding=NULL` (no HNSW pollution)
- Queried by book_id + metadata only (never semantic similarity)
- `exclude_book_ids` enforced in ALL retrieval paths (primary, hop-2, book-ref, ref_book_ids)
- Closure by exact `attempt_id` only. Success threshold: `delta > 0.01`
- Attribution: `isolated`/`batched` stored for reporting, does NOT weight posteriors
- **Config**: `CRITIQUE_MEMORY_ENABLED=true`, `CRITIQUE_MEMORY_INFLUENCE=false`

**GEM 2 — Bayesian Confidence Calibration** (Phase 3, commit be04076):
- `scripts/confidence_calibrator.py` — Pure Bernoulli-Beta posteriors per 5-tuple bucket
- Bucket key: `(eval_mode, weakness_classifier_version, domain, weakness_type, template)`
- Prior: Beta(1,1). Zero-evidence: `source="prior_only"`, `usable=false`
- Time-based holdout + probe-level grouping prevents train/eval leakage
- Empirical harness: reliability diagram, ECE, Brier score (Gates 5-6, need 20+ holdout)
- Gate spec frozen: `docs/phase3_acceptance_gates.md`
- **Config**: `BAYESIAN_CALIBRATION_ENABLED=false`

**API endpoints** (all read-only inspection):
- `GET /api/eval/critique-patterns` — Critique patterns, filterable
- `GET /api/eval/critique-stats` — Summary counts
- `GET /api/eval/effective-templates` — Template success rates per domain
- `GET /api/eval/confidence` — Full calibration ledger with posteriors
- `GET /api/eval/confidence/reliability` — Reliability diagram data

**Phase 4+ (BLOCKED)**: Template weighting, pair allocation, prior injection — requires real closed
critique data, empirical Gates 5-6 passing, and representative strata. Do not enable behavior gates
until then.

## CATEGORY_LANGUAGE Mapping (Policy — Do Not Change Without Version Bump)

`CATEGORY_LANGUAGE` in `scripts/weakness_hunter.py` maps eval categories to their primary execution language.
This is **policy**, not heuristic — changes affect pair generation, replay composition, and domain targeting.

```text
python, algorithms, database, systems, design_patterns,
testing, security, hive_sdk, hive_architecture,
hive_economics, hive_security    → python

javascript, web, hive_layer2     → javascript

rust                             → rust
go                               → go
cpp                              → cpp
```

**Rule**: Do not add or change mappings without bumping `WEAKNESS_CLASSIFIER_VERSION` and updating this table.

## Eval Protocol — Work Smart Not Hard

**Base model evals are PUBLIC KNOWLEDGE** — hardcoded, never re-run. That's our floor.

**For continual learning cycles**: Use `regression_eval.py` (60 domain probes, or `--quick` for original 18).

**For quick LoRA checks**: Use `quick_eval.py` (20 prompts, ~5 min).

**Do NOT:**
- Run full 227-challenge eval for routine version checks (release milestones only)
- Re-eval the base model (scores: quick_eval=0.978, full_eval=0.766)
- Spend hours on eval when a simple A/B answers the question

## Debugging Protocol (4-Phase)

When debugging, follow this structured protocol instead of random trial-and-error:

### Phase 1: Root-Cause Trace

- Read the FULL error message/traceback — don't skip lines
- Identify the exact file, line, and variable where it fails
- Trace backwards: what called that function? What inputs did it receive?
- Check recent changes: `git diff` or `git log --oneline -5` to find what changed

### Phase 2: Hypothesize

- Form exactly 1-3 specific hypotheses about the cause
- Each hypothesis must be testable and falsifiable
- Rank by likelihood — test the most probable first
- Do NOT start fixing until you have a hypothesis

### Phase 3: Verify

- Test each hypothesis with the MINIMUM possible change
- Use targeted reads/greps, not shotgun searches
- If the hypothesis is wrong, cross it off and try the next one
- If all hypotheses are wrong, go back to Phase 1 with new data

### Phase 4: Fix

- Make the smallest fix that addresses the verified root cause
- Verify the fix doesn't break related functionality
- If the bug was in training/data: check if similar bugs exist elsewhere
- Document the lesson if it's a recurring pattern (add to memory)
- **3-attempt limit**: After 3 fix attempts on the same issue, STOP. Document what was tried and escalate to the user. Do not loop.

## Anti-Patterns (Hard Rules)

### Analysis Paralysis Guard

If you make 5+ consecutive Read/Grep/Glob calls without any Edit/Write/Bash action: STOP. State in one sentence why you haven't written anything yet. Either take action or ask the user for direction. Endless exploration without action is wasted context.

### Context Budget Awareness

AI output quality degrades as context fills up. Peak quality at 0-30% usage, degrading at 50-70%, poor at 70%+. This is why CLAUDE.md says to delegate to subagents. If you're deep into a complex task and notice you've read 10+ files, delegate remaining research to a subagent and work from the summary.
