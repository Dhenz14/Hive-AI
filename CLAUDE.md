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

## Eval Protocol — Work Smart Not Hard

**Base model (v1) evals are PUBLIC KNOWLEDGE** — hardcoded, never re-run. That's our floor.

**How we test new LoRA versions:**
1. Start llama-server with the new LoRA
2. Run `quick_eval.py` (20 prompts, ~5 min) — this is the primary gate
3. Compare v(new) quick_eval score against v7 baseline (0.971) and base (0.978)
4. If quick_eval passes: DONE. Ship it.
5. If quick_eval shows regression: investigate which categories dropped, fix, retrain

**Do NOT:**
- Run full 227-challenge eval for routine version checks (that's for release milestones only)
- Re-eval the base model (scores are hardcoded: quick_eval=0.978, full_eval=0.766)
- Spend hours on eval infrastructure when a simple A/B answers the question

**Quick sanity check (even faster):** Pick 3-5 prompts by hand, ask base and LoRA, compare answers visually. If LoRA is clearly better, that's signal enough for iteration.

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
