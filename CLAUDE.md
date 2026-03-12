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

## Continual Learning Pipeline v3.0 (Lossless Zero-Forgetting + Style Protection)

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

**12-Layer Defense Stack**:

*Weight-level (v2.0):*

1. **60-Probe Eval** — 10 probes/domain eliminates measurement noise (±1% vs old ±5.6%)
2. **EWC-LoRA** — Fisher Information penalty prevents training from overwriting existing knowledge. Fisher is auto-normalized (max→1.0) at load time. Post-training Fisher uses `trainer.train_dataset` (tokenized). `--compute-fisher-only` loads trained adapter if available.
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

**Folder layout**:
- `models/deploy/current_base.gguf` — Active inference GGUF
- `replay/*.jsonl` — Per-domain replay buffers (hive, cpp, rust, go, js, general_coding)
- `datasets/*.jsonl` — Training data for new domains
- `score_ledger.json` — Historical scores across all versions
- `logs/` — Per-cycle training logs with rich checkpoint state for resume
- `loras/<version>/fisher.pt` — Fisher matrix for EWC (auto-generated)
- `style_shift_history.json` — Historical style shift scores for threshold calibration (v3.0)

**Fully automated**: No manual steps. Scripts auto-sync from Windows, CRLF auto-fixed, preflight auto-runs.

**Training data format**: Standard instruction/input/output JSONL (NO metadata field). Optional "style" field for v3.0 routing.

## Training UI (Forge Mind Page)

The Forge page (`/forge`) provides one-click training controls:
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
