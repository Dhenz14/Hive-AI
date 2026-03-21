---
name: hiveai-system
description: Expert knowledge on the HiveAI Knowledge Refinery — architecture, RAG pipeline, training system, GPU scaling, and operational patterns. Use when building features, debugging, or extending any part of the Hive-AI system.
user-invocable: true
argument-hint: [component]
---

# HiveAI System Expert

You are an expert on the HiveAI Knowledge Refinery system. Apply this knowledge when
working on, debugging, or extending any part of the Hive-AI codebase.

## System Overview — The Expert Plumber

Think of HiveAI as an expert plumber:

- **The Plumber's Brain (Layer 0)** = v5-think (14B model, frozen at 94.65%). Knows HOW to
  think about code — patterns, logic, debugging instincts. Never retrained casually.
- **The Plumber's Notebook (Layer 1)** = RAG with 12,000+ verified solutions. Perfectly
  organized, language-routed, reranked. New knowledge flows in like a faucet.
- **The "I Keep Looking This Up" List (Layer 2)** = Skill Buffer. Tracks repeated misses.
- **The Study Session (Layer 3)** = Rare Training. Only when ALL 4 conditions met.

## Architecture Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Chat API | `hiveai/app.py` | Flask endpoints, sync + streaming |
| Orchestrator | `hiveai/orchestrator.py` | Intent classification, routing |
| RAG Search | `hiveai/chat.py` | Hybrid search, multi-hop, HyDE |
| Vector Store | `hiveai/vectorstore.py` | BM25 + semantic, language routing |
| LLM Client | `hiveai/llm/client.py` | Backend routing, caching, circuit breaker |
| Verification | `hiveai/sandbox.py` | Code execution (Python/JS/C++/Rust/Go) |
| Telemetry | `hiveai/telemetry.py` | 3-arm experiment, async writer |
| Models/DB | `hiveai/models.py` | SQLAlchemy schema, migrations |
| Config | `hiveai/config.py` | All env vars, validation |
| Compute | `hiveai/compute/` | GPU pooling, tiers, Spirit Bomb |

## RAG Pipeline (The Notebook)

Every query flows through this pipeline:

```
User Query
  → Classify (orchestrator.py: intent, language, retrieval mode)
  → Expand short queries (chat.py: abbreviation expansion)
  → Embed query (BGE-M3, 1024 dims)
  → Hybrid Search (vectorstore.py: vector + BM25 with IDF)
  → Language Routing (boost matching-language sections +0.08)
  → HyDE supplementation (if top results weak, generate hypothetical answer)
  → Query Decomposition (if complex, split into sub-queries, merge via RRF)
  → Multi-hop Entity Search (extract entities, search for related sections)
  → Cross-encoder Reranking (bge-reranker-v2-m3, suppress < 0.02, boost > 0.20)
  → MMR Diversity (prevent redundant top-k results, λ=0.7)
  → CRAG Judge (assess retrieval quality: correct/ambiguous/incorrect)
  → Confidence Gate (rewrite query if confidence < 0.50)
  → Context Budget (fit sections into token budget, paragraph filtering)
  → Build Messages (system prompt + RAG context + user message)
  → LLM Generation (v5-think via llama-server)
  → Verification (if code present: compile + execute in sandbox)
  → Revision (if verification fails + error is fixable: retry once)
  → Auto-promote (if verified: stage as training pair, promote to RAG)
  → Telemetry (log event to 3-arm experiment)
```

## Key Operational Rules

### NEVER Do
- Run model operations on Windows (all in WSL)
- Copy GGUFs to Windows
- Use `wsl --shutdown` without safe_wsl_shutdown.sh
- Lower the 1% regression threshold
- Train v5-think without ALL 4 Layer 3 conditions met
- Use DELLA pruning (broken — 3.33x rescaling corrupts merges)
- Use EWC v1 (broken — 3 compounding bugs)

### ALWAYS Do
- CRLF fix after Windows→WSL sync: `sed -i 's/\r$//'`
- Run 60-probe eval after any training
- Use bf16 HF weights as source of truth (not GGUF)
- Use `--flash-attn auto -t 12` for llama-server
- Keep max 2 bf16 checkpoints, max 3 GGUFs

## Model Serving

### LLM Backend Priority
1. **llama-server** (preferred, serves v5-think): port 11435
2. **Ollama** (fallback): port 11434
3. **OpenRouter** (cloud fallback, if API key set)

Config: `LLM_BACKEND=llama-server` in `.env` bypasses auto-detect.

### Runtime Modes
- **chat_rag**: ctx-size 8192, full RAG pipeline
- **campaign_probe**: ctx-size 4096, eval probes only

## GPU Scaling (Elastic Brain)

| Tier | GPUs | What Changes |
|------|------|-------------|
| **Solo** | 1 | v5-think Q5_K_M, 8K context |
| **Pool** | 2-4 | Same model, higher throughput, best-of-N |
| **Cluster** | 5+ | Bigger model or MoA consensus |

Key files: `hiveai/compute/tier_autoscaler.py`, `community_coordinator.py`, `distributed_inference.py`

## Training Pipeline (Layer 3 — Rare Events Only)

```bash
# One-command cycle (ONLY when all 4 conditions met):
bash scripts/run_full_cycle.sh <domain> <data.jsonl> <version> [prev_version]
```

Steps: preflight → replay_sampler → train_v5 → safe_merge → consolidation → regression_eval

### 14-Layer Defense Stack
- **Working**: 60-probe eval, domain-balanced replay, STM, SDFT
- **Broken**: EWC v1, DELLA, orthogonal SVD
- **Tested & failed**: Probe-aware KL (didn't rescue fragile probes)
- **Untested**: Style tokens, hidden anchoring

### Fragility Map
- **cpp-variadic**: Universal fragility — drops under ANY training
- **py-metaclass**: Reverts to design floor under Python/C++ training
- **js-generics**: Evaluation-unstable, excluded from conclusions

## Database

- **SQLite** (local, `hiveai.db`)
- Key tables: `book_sections` (RAG), `training_pairs`, `telemetry_events`, `chat_sessions`
- Migrations: `_migrate_add_columns()` in models.py (idempotent, runs on startup)

## Telemetry Experiment

3-arm factorial: treatment (70%) / holdout_surface (15%) / no_injection (15%)
- Treatment: RAG injected + surface shown
- Holdout: RAG injected + surface hidden
- No-injection: RAG NOT injected + surface hidden

5 validation gates must pass before reading treatment effects.

## Common Debugging

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| 503 on chat | llama-server down or Ollama competing for GPU | Kill Ollama, restart llama-server |
| Telemetry not recording | Missing columns in DB | Check `_migrate_add_columns()` ran |
| RAG returns irrelevant results | IDF cache stale or language routing off | Check `_refresh_idf_stats()`, verify `language` passed |
| Training loss explodes | EWC penalty domination or LR too high | Disable EWC, check effective LR (base × LoRA+ multiplier) |
| GGUF inference garbage | Style tokens in GGUF (unsupported) | Never use `--style-prefix` with GGUF |
| cpp-variadic drops on eval | Missing `--flash-attn auto` | Always use flash attention |
