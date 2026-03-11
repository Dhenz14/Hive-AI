# HiveAI Project Rules

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

## Continual Learning Pipeline v2.0 (Lossless Zero-Forgetting)

**Architecture**: Train small LoRA → merge permanently into base → consolidate → eval → promote.
Knowledge stacks like legos — once merged, it can never be lost.
**6-layer lossless defense** ensures zero domain regression across cycles.

**bf16 Golden Chain**: HF bf16 weights are the source of truth for ALL merges. GGUF is derived
from HF output via `convert_hf_to_gguf.py` + `llama-quantize`. This eliminates quantization drift
from repeated merges. After 100 merges, zero accumulated noise.

**One-command cycle**:
```bash
bash scripts/run_full_cycle.sh <domain> <data.jsonl> <version> [prev_version]
# Example: bash scripts/run_full_cycle.sh hive datasets/hive_data.jsonl v1-hive v1.0
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
1. `preflight_check.py` — Automated pre-flight validator (7 checks: HF offline, metadata, CRLF, disk, GPU, base model, cache)
2. `replay_sampler.py` — SuRe NLL-scored surprise replay + domain-balanced sampling
3. `train_v5.py` — Train domain LoRA (rank 4-8, LoRA+, all 7 modules, EWC penalty, orthogonal init)
4. `safe_merge.py` — DELLA pruning + alpha grid search [0.75-1.0], golden chain HF→GGUF
5. `consolidation_train.py` — Post-merge stabilization (rank 2, LR/20, 1 epoch, 100% replay, all 7 modules)
6. `regression_eval.py` — 60 domain probes (10/domain), fail if any drops >0.03. `--quick` for original 18.

**6-Layer Lossless Defense**:
1. **60-Probe Eval** (Layer 1) — 10 probes/domain eliminates measurement noise (±1% vs old ±5.6%)
2. **EWC-LoRA** (Layer 2) — Fisher Information penalty prevents training from overwriting existing knowledge
3. **Domain Probe Callback** (Layer 3) — Mid-training regression detection every N steps; auto-reduces LR or halts
4. **DELLA Pruning** (Layer 4) — Drop 70% low-magnitude delta params before merge, keep only what matters
5. **Orthogonal LoRA Init** (Layer 5) — New LoRA initialized orthogonal to previous task's subspace via SVD
6. **Domain-Balanced Replay** (Layer 6) — Equal samples/domain + adaptive ratio boost for dropped domains

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

**Key flags in safe_merge.py**:
- `--della-drop FLOAT` — DELLA pruning drop rate (default 0.0, recommended 0.7)

**Key flags in replay_sampler.py**:
- `--domain-balanced` — Equal samples per domain (prevents domain starvation)

**Key flags in regression_eval.py**:
- `--quick` — Use original 18 probes (fast, ~6 min) vs default 60 probes (precise, ~20 min)

**New scripts**:
- `probe_library.py` — Central probe definitions (60 probes, 6 domains, importable)
- `domain_probe_callback.py` — TRL TrainerCallback for mid-training regression detection

**Post-training automations** (no manual steps needed):
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

**Pre-flight is now automated**: `scripts/preflight_check.py` runs at the start of every cycle.
Manual pre-flight is no longer needed. The only remaining manual step: CRLF-fix after syncing to WSL.

**Training data format**: Standard instruction/input/output JSONL (NO metadata field).

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
