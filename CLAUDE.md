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

## Disk Hygiene (CRITICAL)

### Never use Downloads folder
- **NEVER** reference `C:\Users\theyc\Downloads` or `/mnt/c/Users/theyc/Downloads` in any source file, config, or script
- Downloads is for temporary files and installers — NOT project data
- All project data lives under `c:\Users\theyc\HiveAi\Hive-AI\` or WSL `/opt/hiveai/project/`

### Model file management
- **Windows**: Only keep `models/qwen3.5-35b-a3b/Qwen3.5-35B-A3B-Q4_K_M.gguf` (the active GGUF for llama-server)
- **WSL**: Only keep `qwen3.5-35b-a3b` (original) and the current best rebuild in `/opt/hiveai/project/models/`
- **Delete failed experiments immediately** — do not leave broken/superseded model directories lying around
- Never save duplicate GGUFs (BF16, -fixed, -clean variants). One working GGUF per quant type is enough
- Never keep the raw HF safetensors on Windows (`hf/` subdirectory) — originals live in WSL

### WSL2 vhdx management
- WSL2 ext4.vhdx **only grows, never shrinks automatically**
- After deleting large files in WSL, ALWAYS compact: `wsl --shutdown && diskpart /s scripts/compact_wsl.txt`
- Run `python scripts/disk_hygiene.py` periodically to check for bloat

### Caches to clear periodically
- `~/.cache/huggingface/hub/` — re-downloadable model cache
- `~/AppData/Local/pip/cache/` — pip package cache
- `~/AppData/Local/Temp/wsl-crashes/` — WSL crash dumps from segfaults

## Continual Learning Pipeline v1.2 (Merge-then-Freeze + Golden Chain)

**Architecture**: Train small LoRA → merge permanently into base → consolidate → eval → promote.
Knowledge stacks like legos — once merged, it can never be lost.

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
2. `replay_sampler.py` — SuRe NLL-scored surprise replay (fallback: diversity sampling)
3. `train_v5.py` — Train domain LoRA (rank 4-8, LoRA+, all 7 modules)
4. `safe_merge.py` — Alpha grid search [0.75-1.0], pick lowest perplexity, golden chain HF→GGUF
5. `consolidation_train.py` — Post-merge stabilization (rank 2, LR/20, 1 epoch, 100% replay, all 7 modules)
6. `regression_eval.py` — 18 domain probes, fail if any drops >0.03

**Key flags in train_v5.py**:
- `--rank N` — LoRA rank override (4-8 for continual learning)
- `--lr FLOAT` — Direct LR override
- `--lora-plus` — B matrix gets 16x higher LR (LoRA+, arXiv 2602.04998)
- `--replay-dir PATH` — Mix replay data from per-domain JSONL files
- `--replay-ratio FLOAT` — Fraction of replay in training mix (default 0.25)
- `--consolidation-only` — Consolidation mode (1 epoch, LR/10)
- `--base-model-hf PATH` — Train on merged HF checkpoint (for cycle 2+)
- `--attn-only` — Train q/k/v/o_proj only (freeze MLP) — NOT used in consolidation

**Post-training automations** (no manual steps needed):
- Auto-normalizes `adapter_config.json` (fixes absolute cache paths → `Qwen/Qwen2.5-Coder-14B-Instruct`)
- Auto-converts LoRA adapter to GGUF (`adapter.gguf` alongside PEFT files)
- Auto-runs preflight checks before training starts
- Auto-cleans old model versions after promotion (keeps 3 GGUFs, 2 bf16 checkpoints)

**Folder layout**:
- `models/deploy/current_base.gguf` — Active inference GGUF
- `replay/*.jsonl` — Per-domain replay buffers (hive, cpp, rust, go, js, general_coding)
- `datasets/*.jsonl` — Training data for new domains
- `score_ledger.json` — Historical scores across all versions
- `logs/` — Per-cycle training logs with rich checkpoint state for resume

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

**For continual learning cycles**: Use `regression_eval.py` (18 domain probes, automated).

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
