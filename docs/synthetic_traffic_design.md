# Synthetic Traffic Bootstrap — Master Design Document

**Date**: 2026-03-18
**Status**: Implementation-ready
**Purpose**: Bootstrap calibration data for blocked features using public datasets as placeholder traffic until real users accumulate organically.

---

## Problem Statement

Five features are instrumented but blocked on data volume:

| Feature | What It Needs | Minimum N | Current N |
|---------|--------------|-----------|-----------|
| Shadow reranker calibration | Retrieval traces with cross-encoder scores | 50-100 | ~0 usable |
| 3-arm telemetry experiment | Chat turns with arm assignment | 50 gate pass, ~700 significance | ~118 total |
| Query normalizer validation | Diverse query types with before/after scores | 20-30 per class | 0 (not built) |
| Confidence gate thresholds | Queries with varying retrieval difficulty | 50+ | ~0 calibrated |
| Promotion bridge Gate 11 | Retrieved solved examples on follow-ups | 50%+ hit rate | untracked |

Single-user organic traffic cannot fill these volumes in a reasonable timeframe.
Public coding Q&A datasets provide realistic, labeled placeholder data.

---

## Public Dataset Selection

### Tier 1: Direct Use (query + code + relevance labels)

**CoSQA** (Code Search Query Answering)
- Source: `huggingface.co/datasets/gonglinyuan/CoSQA`
- Size: 20,604 examples (20k train, 604 dev)
- Fields: `query` (NL), `code` (Python), `label` (binary 0/1 relevance), `idx`
- License: MIT
- Use: Reranker calibration — has exact (query, passage, relevance) triples
- Preprocessing: Filter by label for positive/negative pairs

**MTEB CoSQA** (IR-formatted)
- Source: `huggingface.co/datasets/mteb/cosqa`
- Size: 500 test queries with qrels + 20.6k corpus
- Fields: queries, corpus, qrels (binary relevance scores)
- License: MIT
- Use: Confidence gate threshold calibration — already structured as retrieval eval

**CQADupStack-Programmers** (StackExchange)
- Source: `huggingface.co/datasets/mteb/cqadupstack-programmers`
- Size: 876 queries, 32.2k corpus, 1.68k relevance pairs
- Fields: queries, corpus, qrels
- License: Apache 2.0
- Use: Sparse relevance testing (avg 1.91 relevant docs/query) — tests suppress threshold

### Tier 2: High-Quality Pairs (no explicit labels)

**StaQC** (Stack Overflow Question-Code)
- Source: `huggingface.co/datasets/koutch/staqc`
- Size: 85k Python question-code pairs (sca_python subset)
- Fields: `question` (NL), `snippet` (code), `question_id`
- License: CC-BY-4.0
- Use: Realistic chat traffic — real SO titles, natural and varied

**CoNaLa-Mined** (NL-to-Code with raw + rewritten)
- Source: `huggingface.co/datasets/codeparrot/conala-mined-curated`
- Size: 594k pairs
- Fields: `intent` (raw SO title), `rewritten_intent` (cleaned NL), `snippet`, `prob`
- License: CC-BY-SA
- Use: Query normalizer hypothesis testing — raw vs cleaned intent pairs

**CodeSearchNet**
- Source: `huggingface.co/datasets/code-search-net/code_search_net`
- Size: 2.07M across 6 languages (Python, Java, JS, Go, PHP, Ruby)
- Fields: `func_documentation_string`, `func_code_string`, `language`
- License: Research use
- Use: Multi-language query diversity at volume

### Tier 3: Corpus Sources

**code-rag-bench/stackoverflow-posts**
- Source: `huggingface.co/datasets/code-rag-bench/stackoverflow-posts`
- Size: 1.97M posts
- License: CC-BY-SA 4.0
- Use: Retrieval corpus stand-in if needed

---

## Architecture

### Three Scripts, Clean Separation

```
scripts/bootstrap_datasets.py   — Download + prepare datasets (run once)
scripts/synthetic_traffic.py    — Send queries through /api/chat (run N times)
scripts/calibrate_reranker.py   — Analyze accumulated traces (run after traffic)
```

### Data Flow

```
Public Datasets (HuggingFace)
    │
    ▼
bootstrap_datasets.py
    │  Downloads CoSQA, StaQC, CoNaLa
    │  Samples + classifies queries
    │  Writes data/synthetic_queries.jsonl
    ▼
synthetic_traffic.py
    │  Reads synthetic_queries.jsonl
    │  Sends each query to POST /api/chat
    │  Tags is_internal=true via X-Internal header
    │  Logs response traces to data/synthetic_results.jsonl
    ▼
telemetry_events table
    │  retrieval_trace_json populated
    │  Shadow reranker scores accumulated
    │  3-arm experiment events assigned
    ▼
calibrate_reranker.py
    │  Reads telemetry_events via SQLite
    │  Computes score distributions
    │  Recommends threshold adjustments
    │  Outputs calibration report
    ▼
Threshold decisions (human-reviewed)
```

### Query Classification

Each synthetic query is tagged with a query class for per-class analysis:

| Class | Source | Purpose |
|-------|--------|---------|
| `paraphrase` | CoNaLa (rewritten_intent) | Best-case for normalizer |
| `syntax_heavy` | CodeSearchNet (docstrings with code refs) | Over-smoothing failure mode |
| `error_text` | StaQC (questions containing "error", "exception") | Precision on discriminative cues |
| `short_ambiguous` | StaQC (questions < 8 words) | False-positive normalization |
| `direct_how` | CoSQA (starts with "how to") | Standard coding queries |
| `conceptual` | CQADupStack (design/architecture questions) | Off-domain for code RAG |

### Tagging Strategy

All synthetic traffic is marked `is_internal=true` so it can be:
- Included in calibration analysis
- Excluded from product telemetry experiment (treatment effects must come from real users)
- Filtered out of any user-facing metrics

### Volume Targets

| Phase | Queries | Purpose |
|-------|---------|---------|
| Phase 1: Smoke | 20 | Verify pipeline works, traces persist |
| Phase 2: Calibration | 200 | Shadow reranker score distributions |
| Phase 3: Full | 500 | Statistical power for threshold decisions |

---

## Implementation Details

### bootstrap_datasets.py

```
Inputs:  HuggingFace dataset names
Outputs: data/synthetic_queries.jsonl

Each line: {
    "query": "how to sort a dictionary by value in python",
    "source": "cosqa",
    "query_class": "direct_how",
    "has_label": true,
    "relevance_label": 1,
    "gold_code": "sorted(d.items(), key=lambda x: x[1])",
    "idx": 42
}
```

Sampling strategy:
- 50 from CoSQA (labeled, for reranker ground truth)
- 50 from StaQC (realistic SO questions)
- 30 from CoNaLa (raw intents for normalizer)
- 20 from CQADupStack (conceptual/design)
- Total: 150 queries for Phase 2, expandable to 500

### synthetic_traffic.py

```
Inputs:  data/synthetic_queries.jsonl, Flask endpoint URL
Outputs: data/synthetic_results.jsonl, telemetry_events rows

For each query:
1. POST /api/chat with {"message": query, "history": []}
2. Extract trace from response JSON
3. Log: query + trace + shadow_scores + arm_assignment + latency
4. Rate limit: 2 req/s (avoid overwhelming llama-server)
5. Skip if llama-server not running (fail-open)
```

Headers:
- `X-Internal: true` → sets is_internal=true in telemetry
- `X-Frontend-Build: synthetic-v1` → identifies synthetic traffic

### calibrate_reranker.py

```
Inputs:  SQLite telemetry_events (retrieval_trace_json)
Outputs: Calibration report (stdout + data/calibration_report.json)

Analysis:
1. Score distribution: histogram of reranker_best_score
2. Separation: score ranges for relevant vs irrelevant (using CoSQA labels)
3. Threshold recommendation: optimal suppress/rewrite points
4. Per-query-class breakdown: does any class behave differently?
5. Latency profile: p50/p95/p99 of reranker_shadow_latency_ms
```

---

## Migration Safety

The `retrieval_trace_json` column was added to the TelemetryEvent model but NOT to
`_migrate_add_columns()` in models.py. If the telemetry_events table was created before
that column was added, it won't exist. Add it to the migration list as a safety net:

```python
("telemetry_events", "retrieval_trace_json", "TEXT"),
```

This is idempotent — if the column already exists, the ALTER TABLE is silently skipped.

---

## Constraints

- **No weight mutation**: This is Layer 1 only. No training, no model changes.
- **is_internal tagging**: All synthetic traffic tagged, separable from organic.
- **Rate limited**: 2 req/s default, configurable. Won't overwhelm llama-server.
- **Fail-open**: If llama-server is down, script logs the skip and continues.
- **Idempotent**: Re-running bootstrap overwrites the JSONL, doesn't duplicate.
- **No CI dependency**: These are manual scripts, not automated pipelines.
- **Human-reviewed thresholds**: Calibration script recommends, human decides.

---

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| Traces persist | `SELECT count(*) FROM telemetry_events WHERE retrieval_trace_json IS NOT NULL` > 0 |
| Shadow scores present | `json_extract(retrieval_trace_json, '$.reranker_shadow_applied') = true` on >80% of traces |
| Score distribution visible | Histogram shows clear bimodal or spread distribution |
| Per-class analysis possible | Each query_class has ≥15 traces |
| Threshold recommendation | calibrate_reranker.py outputs a recommended threshold with confidence interval |
| No production contamination | All synthetic events have `is_internal=true` |

---

## Dataset Licensing Summary

| Dataset | License | Commercial OK | Attribution Required |
|---------|---------|--------------|---------------------|
| CoSQA | MIT | Yes | No |
| MTEB CoSQA | MIT | Yes | No |
| CQADupStack | Apache 2.0 | Yes | Yes (NOTICE file) |
| StaQC | CC-BY-4.0 | Yes | Yes |
| CoNaLa | CC-BY-SA | Yes (share-alike) | Yes |
| CodeSearchNet | Other (research) | Check terms | Yes |

All datasets used here are publicly available and permissively licensed for research
and development use. Synthetic traffic generated from these datasets is internal
calibration data, not redistributed.
