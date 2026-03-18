# 3 Gems: Critique Memory + Bayesian Confidence + Weakness Trending
## Refined Plan v3 — Final (GPT Round 2 Feedback Incorporated)

### Context

The training improvement loop (`weakness_hunter` → `generate_pairs` → `train` → `regression_eval`) is stateless. It doesn't remember which fixes worked, which critiques are reliable, or which weaknesses are chronic. Every cycle starts from zero context.

**GPT reviewed our v1 plan and identified 5 real issues** (all verified against code):
1. `check_regression()` includes `failed/` entries in best-score baselines — **CRITICAL BUG**
2. `weakness_hunter._generate_via_miner()` hardcodes `"python"` for ALL categories — **DATA MISLABELING BUG**
3. Ledger stores no `eval_mode` — quick (18-probe) and full (60-probe) runs mix silently — **CRITICAL BUG**
4. `score_response()` computes `keyword_score` and `structure_score` separately but discards components — only returns combined scalar
5. Hop-2 vector search in `chat.py` bypasses `hybrid_search()` filtering — critique patterns would leak into chat RAG

**GPT proposed reordering**: probe telemetry → ledger cleanup → attempt identity → GEM 1 → GEM 3 → GEM 2

**Our response**: GPT's bugs are real and must be fixed. But they're prerequisites (~30 min of fixes), not separate phases. The gem ordering stays GEM 3 → GEM 1 → GEM 2 because GEM 3 produces the raw data GEM 1 and GEM 2 consume. The instrumentation GPT wants gets folded into GEM 3's `regression_eval.py` changes.

**GPT Round 2 raised 6 additional concerns** (all verified against code):
1. **Causal attribution**: `attempt_id` fixes identity but not causality — a training cycle with mixed pairs can't prove which critique "worked." Add `isolated` vs `batched` attribution labels.
2. **Auto-recovery path underspecified**: `_auto_mine_failures()` (line 358) emits only `{"by_category": {domain: {"score": float}}}` — no per-probe data, no components, no trends. The smart path only fires manually.
3. **JSONL needs provenance stamps** for HivePoA multi-worker future: `scorer_version`, `probe_library_hash`, `git_sha`.
4. **Posterior mean is not conservative enough** for pair allocation — use lower credible bound instead.
5. **`weakness_type` needs deterministic classifier versioning** — "low_keyword_coverage" must mean the same thing in March as in June.
6. **Critique patterns should NOT have embeddings** — they're queried by book_id + metadata, not semantic similarity. Embedding wastes compute and pollutes HNSW indexes.

### HivePoA GPU Marketplace Context

HiveAI doesn't build its own GPU marketplace — **[HivePoA](https://github.com/Dhenz14/HivePoA) handles that**:
- Job posting, claiming, verification, HBD settlement
- Node registration, heartbeats, trust registry
- IPFS adapter distribution with integrity verification

**HiveAI's role**: Define job types and consume results. Current state:
- `compute/worker.py` — executes `eval_sweep` and `benchmark_run` jobs (V1 LIVE)
- `compute/verifier.py` — independent re-eval verification (V1 LIVE)
- `dbc/compute_client.py` — full REST API to HivePoA compute (LIVE)
- V1.1 (DEFERRED): `domain_lora_train`, `weakness_targeted_generation`, `adapter_validation`

**How the 3 gems connect to distributed compute**: The gems make HiveAI a smarter *consumer* of distributed results. When multiple contributors run eval sweeps via HivePoA, the trending system (GEM 3) ingests their results. When contributors submit domain-specialist LoRAs, the critique memory (GEM 1) and confidence calibration (GEM 2) guide which contributions are worth merging. The gems are the intelligence layer; HivePoA is the execution layer.

---

## Phase 0: Bug Fixes (Prerequisites)

These are bugs regardless of the gems — fix before anything else.

### Fix 1: `check_regression()` failed-run contamination
**File**: `scripts/regression_eval.py` (~line 222)
**Bug**: Iterates `ledger.values()` without filtering `failed/` keys. Failed runs inflate best-score baselines, causing false regression failures.
**Fix**: Skip `failed/` prefixed keys in the baseline loop:
```python
for version_key, version_data in ledger.items():
    if version_key.startswith("failed/"):
        continue
```

### Fix 2: `weakness_hunter` language hardcoding
**File**: `scripts/weakness_hunter.py` (~line 344)
**Bug**: `_generate_via_miner()` passes `"python"` for every category regardless of actual domain.
**Fix**: Map category to language:
```python
CATEGORY_LANGUAGE = {
    "python": "python", "cpp": "cpp", "rust": "rust",
    "go": "go", "javascript": "javascript",
    "hive_sdk": "python", "hive_architecture": "python",
    # ... etc
}
language = CATEGORY_LANGUAGE.get(category, "python")
pair = miner._generate_one_pair(provider, topic, template, template_text, language)
```

### Fix 3: Add `eval_mode` to ledger storage
**File**: `scripts/regression_eval.py` (~line 320)
**Bug**: No distinction between quick (18-probe) and full (60-probe) runs in ledger. Mixing modes corrupts baselines.
**Fix**: Store eval_mode in ledger entry:
```python
scores_with_meta["eval_mode"] = "quick" if args.quick else "full"
scores_with_meta["probe_count"] = len(probes)
```
Also update `check_regression()` to only compare against same-mode baselines.

---

## Phase 1: GEM 3 — Weakness Trending + Probe Instrumentation

**Addresses GPT's core concern**: "You need per-probe component scores before GEM 1 and GEM 2 can learn what kind of failure happened."

We fold the instrumentation into GEM 3's `regression_eval.py` changes — not a separate phase.

### Changes to `scripts/regression_eval.py`

**`score_response()` (~line 64)**: Return component breakdown alongside scalar:
```python
def score_response(response, probe):
    # ... existing keyword_score and structure_score computation ...
    combined = keyword_score * 0.7 + structure_score * 0.3
    return {
        "score": combined,
        "keyword_score": keyword_score,
        "structure_score": structure_score,
        "keywords_found": found,
        "keywords_total": len(expected_keywords),
        "response_length": len(response),
        "has_code_blocks": bool(re.search(r'```', response)),
    }
```

**`run_all_probes()` (~line 164)**: Return per-probe detail:
```python
def run_all_probes(probes, ...):
    domain_scores = {}    # {domain: avg_score} (existing)
    probe_details = {}    # {probe_id: {score, keyword_score, structure_score, ...}} (NEW)
    # ... existing loop, but capture component scores ...
    return domain_scores, probe_details
```

**`main()` (~line 297)**: After scoring:
- Store `probe_scores` in ledger entry: `scores_with_meta["probe_scores"] = {pid: detail["score"] for pid, detail in probe_details.items()}`
- Store `eval_mode` (from Fix 3)
- Call `weakness_trend.append_trend_entry()` per probe with component data

**Callers to update**: `_auto_mine_failures()` (~line 358) also calls `run_all_probes()` — update to handle tuple return.

**CRITICAL: Upgrade `_auto_mine_failures()` auto-recovery path** (GPT Round 2, Point 2):
Currently builds a minimal temp eval with only `{"by_category": {domain: {"score": float}}}`. The smart parts (per-probe components, trend classifications, critique history) only fire in the manual path. Fix:
```python
def _auto_mine_failures(scores: dict, issues: list, version: str, probe_details: dict = None):
    # Build richer eval payload including per-probe telemetry
    eval_data = {"by_category": {}}
    for domain, score in scores.items():
        if isinstance(score, (int, float)):
            eval_data["by_category"][domain] = {"score": score}

    # NEW: Include per-probe breakdown if available
    if probe_details:
        eval_data["probe_details"] = {
            pid: {"score": d["score"], "keyword_score": d["keyword_score"],
                  "structure_score": d["structure_score"]}
            for pid, d in probe_details.items()
        }

    # NEW: Include trend classifications if available
    try:
        from scripts.weakness_trend import load_trend_log, classify_trends
        trends = classify_trends(load_trend_log(eval_mode="full"))
        eval_data["trend_classifications"] = {
            k: {"trend": v.trend, "consecutive": v.consecutive}
            for k, v in trends.items()
        }
    except Exception:
        pass  # trends not available yet — degrade gracefully
```
This ensures the automatic regression → weakness_hunter path has the same intelligence as manual invocation.

### New File: `scripts/weakness_trend.py`

```python
TREND_LOG_PATH = "weakness_trend.jsonl"

def append_trend_entry(version, domain, probe_id, score,
                       keyword_score=None, structure_score=None,
                       prev_score=None, eval_mode="full",
                       fix_attempted=False, fix_version=None, fix_result=None):
    """Append one trend entry per probe per eval run."""

def load_trend_log(path=None, eval_mode=None) -> list[dict]:
    """Load trend log, optionally filtered by eval_mode. Last 1000 entries."""

def classify_trends(entries) -> dict[str, TrendClassification]:
    """Classify each probe as declining/resistant/improving/stable/volatile."""

def get_domain_trend(domain, entries=None) -> dict:
    """Domain-level summary with per-probe breakdown."""

def main():
    """CLI: --show, --domain X, --resistant, --format json|table, --compact"""
```

**Weakness classifier** (GPT Round 2, Point 5 — deterministic, versioned):
```python
WEAKNESS_CLASSIFIER_VERSION = 1
KEYWORD_LOW_THRESHOLD = 0.70
STRUCTURE_LOW_THRESHOLD = 0.50

def classify_weakness_type(keyword_score, structure_score):
    """Deterministic weakness classification. Bump version if thresholds change."""
    if keyword_score < KEYWORD_LOW_THRESHOLD and structure_score < STRUCTURE_LOW_THRESHOLD:
        return "compound"
    elif keyword_score < KEYWORD_LOW_THRESHOLD:
        return "keyword_only"
    elif structure_score < STRUCTURE_LOW_THRESHOLD:
        return "structure_only"
    else:
        return "none"
```
Every trend entry and critique pattern stores `weakness_classifier_version` so old and new classifications are never mixed.

**Trend entry schema** (JSONL, one line per probe per eval):
```json
{
  "version": "v5-think",
  "timestamp": "2026-03-15T12:00:00Z",
  "domain": "cpp",
  "probe_id": "cpp-raii",
  "score": 0.857,
  "keyword_score": 0.82,
  "structure_score": 0.95,
  "weakness_type": "keyword_only",
  "weakness_classifier_version": 1,
  "keywords_found": 5,
  "keywords_total": 6,
  "response_length": 1842,
  "prev_score": 0.830,
  "delta": 0.027,
  "eval_mode": "full",
  "fix_attempted": false,
  "fix_version": null,
  "fix_result": null,
  "provenance": {
    "scorer_version": "regression_eval_v2",
    "probe_library_hash": "a3f8b2c1",
    "git_sha": "595fdfe"
  }
}
```

Component scores let GEM 1 and GEM 2 distinguish *why* a probe failed (keyword knowledge loss vs structural degradation vs both), which GPT correctly identified as missing from our v1 plan.

### Changes to `scripts/weakness_hunter.py`

- `main()`: Load trend classifications on startup. Print trend context per weakness.
- `analyze_weaknesses()`: Accept optional `trends` param. Flag `resistant` probes.
- `generate_targeted_pairs()`: If `resistant`, switch template strategy.
- **Probe-level action** (GPT Round 3, Point 6): Currently weakness_hunter learns at probe granularity but acts at category granularity — a resistant `cpp-raii` probe gets diluted inside the broader C++ bucket. Fix: when a probe is flagged `resistant`, generate pairs targeted at that probe's specific topic (e.g., "RAII and resource management") rather than the whole domain. Requires adding a `PROBE_TOPICS` mapping to `probe_library.py` that maps probe IDs to focused subtopics for targeted pair generation.

### API Endpoint

**`GET /api/eval/trends`** in `hiveai/app.py` — trend classifications as JSON, filterable by `?domain=`, `?resistant=true`, `?eval_mode=full`.

---

## Phase 2: GEM 1 — Critique Pattern Memory

### GPT Feedback Incorporated

**1. Explicit `critique_attempt_id`** (GPT: "fix_version + domain is too weak a join key")

GPT is right. A single fix version can target multiple probes with different templates. We add a UUID-based attempt ID:

```python
import uuid

def store_critique_pattern(db, domain, probe_id, weakness_type, template_used,
                           pairs_generated, fix_version, pre_score,
                           keyword_score=None, structure_score=None) -> tuple[int, str]:
    attempt_id = str(uuid.uuid4())[:12]  # short unique ID
    # ... store in keywords_json with attempt_id ...
    return section_id, attempt_id

def close_critique_loop(db, attempt_id, post_score, post_keyword=None, post_structure=None) -> bool:
    """Close a specific attempt by its ID. Returns True if found and closed."""
```

The `attempt_id` gets embedded in the training artifact metadata so `regression_eval.py` can close the *exact* attempt, not a fuzzy domain+version bucket.

**2. Exclude from ALL search paths** (GPT: "hop-2 bypasses hybrid_search")

Book-ID exclusion is the safest approach — it works in every search path without modifying `vector_search()`:

```python
_CRITIQUE_BOOK_ID = None  # cached after first lookup

def _get_critique_book_id(db) -> int:
    global _CRITIQUE_BOOK_ID
    if _CRITIQUE_BOOK_ID is None:
        book = db.query(GoldenBook).filter_by(title=_CRITIQUE_BOOK_TITLE).first()
        _CRITIQUE_BOOK_ID = book.id if book else -999
    return _CRITIQUE_BOOK_ID
```

In `chat.py:search_knowledge_sections()`: add critique book_id to an `exclude_book_ids` set passed to both `hybrid_search()` and `vector_search()` calls (hop-2 and book-ref expansion).

In `vectorstore.py`: Add optional `exclude_book_ids` parameter to `vector_search()` and `hybrid_search()`. Filter early in the SQL query: `BookSection.book_id.notin_(exclude_book_ids)`.

This is belt-and-suspenders: both book_id exclusion AND source_type check.

**3. Component scores in critique patterns** (enabled by GEM 3 instrumentation)

Critique patterns now store `pre_keyword_score`, `pre_structure_score`, `post_keyword_score`, `post_structure_score` — so we can learn "this template fixed keyword coverage but broke structure."

**4. Causal attribution quality** (GPT Round 2, Point 1)

A training cycle often includes pairs from multiple weakness categories + replay data. We can't attribute improvement to a single critique attempt. Each stored pattern gets an `attribution` label:
- `isolated` — single-domain cycle with no other data changes. Full weight in template effectiveness.
- `batched` — multi-domain cycle or mixed with other data. Fractional credit in template effectiveness (0.3x weight). Feeds trend statistics but not template success rates.

```python
def store_critique_pattern(db, domain, probe_id, weakness_type, template_used,
                           pairs_generated, fix_version, pre_score,
                           pre_keyword_score=None, pre_structure_score=None,
                           attribution="batched") -> tuple[int, str]:
    # attribution: "isolated" or "batched"
```

`get_effective_templates()` uses full weight for `isolated` attempts, 0.3x for `batched`:
```python
def get_effective_templates(db, domain) -> dict[str, float]:
    for pattern in closed_patterns:
        weight = 1.0 if pattern["attribution"] == "isolated" else 0.3
        # ... weighted success rate computation ...
```

**5. No embeddings for critique patterns** (GPT Round 2, Point 6)

Critique patterns are queried by `book_id` + metadata parsing (direct DB query), NOT semantic similarity. Skip `embed_text()` in `store_critique_pattern()` — set embedding to null. This saves compute and keeps critique rows out of HNSW indexes entirely. Belt-and-suspenders with `exclude_book_ids`: even if someone later adds embeddings, the book exclusion still blocks retrieval.

### New File: `scripts/critique_memory.py`

```python
_CRITIQUE_BOOK_TITLE = "Critique Patterns :: Training Outcomes"
_CRITIQUE_BOOK_JOB_ID = -2

def _get_or_create_critique_book(db) -> GoldenBook
def store_critique_pattern(db, domain, probe_id, weakness_type, template_used,
                           pairs_generated, fix_version, pre_score,
                           pre_keyword_score=None, pre_structure_score=None) -> tuple[int, str]
    # Returns (section_id, attempt_id)

def close_critique_loop(db, attempt_id, post_score,
                        post_keyword_score=None, post_structure_score=None) -> bool
    # Closes by exact attempt_id, not fuzzy domain+version
    # Auto-closes patterns open >7 days as "abandoned"

def retrieve_similar_critiques(db, domain, probe_id=None, limit=5) -> list[dict]
    # Direct DB query filtered by book_id first (fast, no full scan)

def get_effective_templates(db, domain) -> dict[str, float]
    # Template success rates from closed critiques
```

**`keywords_json` schema**:
```json
{
  "source_type": "critique_pattern",
  "attempt_id": "a3f8b2c1e9d4",
  "attribution": "isolated",
  "domain": "cpp",
  "probe_id": "cpp-raii",
  "weakness_type": "keyword_only",
  "weakness_classifier_version": 1,
  "template_used": "implement",
  "pairs_generated": 15,
  "fix_version": "v6-cpp-fix",
  "pre_score": 0.857,
  "pre_keyword_score": 0.82,
  "pre_structure_score": 0.95,
  "post_score": 0.912,
  "post_keyword_score": 0.91,
  "post_structure_score": 0.93,
  "fix_succeeded": true,
  "delta": 0.055,
  "created_at": "2026-03-15T12:00:00Z",
  "closed_at": "2026-03-16T14:00:00Z",
  "keywords": ["cpp", "raii", "keyword_only", "implement", "critique_pattern"]
}
```

**Note**: BookSection rows for critique patterns have `embedding = NULL` (no vector). They are excluded from all search paths via `exclude_book_ids` and are queried only via direct DB lookups filtered by `book_id`.
```

### Files to Modify

**`hiveai/vectorstore.py`**
- `vector_search()`: Add optional `exclude_book_ids` parameter, filter in SQL query
- `hybrid_search()`: Add optional `exclude_book_ids` parameter, pass through to vector_search + add source_type check

**`hiveai/chat.py`**
- `search_knowledge_sections()`: Build `exclude_book_ids` set containing critique book_id. Pass to all search calls (initial hybrid_search, hop-2 vector_search, book-ref vector_search).

**`scripts/weakness_hunter.py`**
- Before generating: call `retrieve_similar_critiques()` and `get_effective_templates()`
- After generating: call `store_critique_pattern()` for each weakness, capture `attempt_id`
- Store `attempt_id` in the generated pair's metadata for later loop closing

**`scripts/regression_eval.py`**
- After ledger save: call `close_critique_loop(attempt_id, post_score, ...)` for each open attempt

**`hiveai/config.py`**
- Add `CRITIQUE_MEMORY_ENABLED` (default `true`)

**`hiveai/app.py`**
- `GET /api/eval/critique-patterns` — all patterns with outcomes, filterable
- `GET /api/eval/effective-templates` — template success rates per domain

---

## Phase 3: GEM 2 — Bayesian Confidence Calibration

### GPT Feedback Incorporated

**1. Beta distribution** (GPT suggested, we already adopted in v1.1)

Beta(alpha, beta) with uniform prior Beta(1,1). GPT and Grok both converged on this — it's the right model. Handles small samples gracefully without arbitrary minimums.

**2. Don't mix quick/full modes** (GPT: valid)

`confidence_calibrator.py` partitions all computations by `eval_mode`. Quick and full runs maintain separate Beta distributions. If a domain has only quick-mode data, we report it with a `mode: "quick"` tag and don't mix into full-mode estimates.

**3. Prompt injection of priors** (from Grok, GPT didn't object)

`build_prior_prompt()` generates natural-language context for weakness_hunter:
```
Past critiques on C++ keyword density: 80% reliable (Beta(5,2), n=6). Be strict.
Past critiques on Rust style quality: 33% reliable (Beta(2,4), n=5). Focus on concrete, testable fixes only.
C++ template "implement" has 82% success rate vs "debug_fix" at 43%. Prefer "implement".
```

### New File: `scripts/confidence_calibrator.py`

```python
def compute_confidence_ledger(score_ledger_path=None, trend_log_path=None,
                              window_size=5, eval_mode="full") -> dict
    # Partitions by eval_mode
    # For each (domain, weakness_type, template):
    #   Beta(alpha=1+successes, beta=1+failures)
    # reliability = alpha / (alpha + beta)
    # recommended_pairs_weight = reliability * (1 + avg_delta * 10)

def update_beta(domain, weakness_type, success: bool) -> None
    # Called by close_critique_loop in GEM 1

def get_pair_allocation(weaknesses, confidence, total_pairs=100) -> dict[str, int]
    # Uses actual Beta posterior 10th percentile, not normal approximation (GPT Round 3, Point 4)
    # from scipy.stats import beta as beta_dist
    # lower_bound = beta_dist.ppf(0.10, alpha, beta)  # true 10th percentile
    # lower_bound > 0.5 → up to 1.5x pairs (genuinely reliable)
    # lower_bound < 0.3 → 0.5x pairs OR different templates (probably noise)
    # alpha + beta < 4 → default allocation (insufficient data, bound too wide)

def build_prior_prompt(domain, weakness_type=None) -> str
    # Natural-language reliability context for weakness_hunter prompts
    # Empty string if Beta(1,1) — nothing to say yet

def save_confidence_ledger(ledger, path=None) -> None
def load_confidence_ledger(path=None) -> dict|None
def main()  # CLI: --compute, --show, --domain X
```

**`confidence_ledger.json`** schema:
```json
{
  "computed_at": "2026-03-15T12:00:00Z",
  "eval_mode": "full",
  "window_size": 5,
  "by_domain": {
    "cpp": {
      "alpha": 5, "beta": 2,
      "reliability": 0.714,
      "avg_delta": 0.035,
      "recommended_pairs_weight": 1.25,
      "probes": {
        "cpp-raii": {"alpha": 2, "beta": 2, "reliability": 0.5, "trend": "resistant"},
        "cpp-move": {"alpha": 3, "beta": 1, "reliability": 0.75, "trend": "improving"}
      }
    }
  },
  "by_weakness_type": {
    "low_keyword_coverage": {"alpha": 14, "beta": 5, "reliability": 0.737},
    "low_structural_quality": {"alpha": 3, "beta": 5, "reliability": 0.375}
  },
  "by_template": {
    "implement": {"alpha": 9, "beta": 2, "reliability": 0.818},
    "debug_fix": {"alpha": 3, "beta": 4, "reliability": 0.429}
  }
}
```

### Files to Modify

**`scripts/weakness_hunter.py`**
- Load confidence ledger, call `get_pair_allocation()` for weighted pair counts
- Prepend `build_prior_prompt()` to LLM generation prompts
- `generate_targeted_pairs()`: Accept `pair_allocation` override

**`scripts/regression_eval.py`**
- After critique loop close: trigger `compute_confidence_ledger()` + save

**`scripts/critique_memory.py`** (GEM 1)
- `close_critique_loop()`: Call `update_beta()` after closing each pattern

**`hiveai/config.py`**
- `CONFIDENCE_CALIBRATION_ENABLED` (default `true`)
- `CONFIDENCE_WINDOW_SIZE` (default `5`)
- `CONFIDENCE_PRIOR_INJECTION` (default `true`)

**`hiveai/app.py`**
- `GET /api/eval/confidence` — full confidence ledger with Beta parameters

---

## Risk Assessment

| Risk | Phase | Severity | Mitigation |
|------|-------|----------|------------|
| `check_regression()` failed-run contamination | 0 | **CRITICAL** | Skip `failed/` keys — 2-line fix |
| weakness_hunter language mislabeling | 0 | **HIGH** | Category→language map — 10-line fix |
| Quick/full mode mixing in ledger | 0 | **HIGH** | Store `eval_mode`, partition comparisons |
| `run_all_probes()` return type breaks callers | 1 | Medium | Only 2 callers (`main()` + `_auto_mine_failures()`), update both |
| `weakness_trend.jsonl` grows unbounded | 1 | Low | `load_trend_log` reads last 1000; `--compact` CLI |
| Critique patterns leak into chat RAG | 2 | **HIGH** | Book-ID exclusion in ALL search paths + source_type check |
| Stale open critique patterns | 2 | Low | Auto-close after 7 days as "abandoned" |
| Insufficient data for Beta confidence | 3 | Low | Beta(1,1) prior is naturally conservative; alpha+beta < 4 → default allocation |
| Mixing eval modes in confidence | 3 | Medium | Partition by eval_mode; never cross-compare |

---

## File Change Matrix

| File | Phase 0 | Phase 1 (GEM 3) | Phase 2 (GEM 1) | Phase 3 (GEM 2) |
|------|---------|-----------------|-----------------|-----------------|
| `scripts/regression_eval.py` | fix failed/ filter, add eval_mode | per-probe components, trend append | close critique loop by attempt_id | trigger confidence recompute |
| `scripts/weakness_hunter.py` | fix language hardcoding | read trends, flag resistant | read critiques, store patterns, template overrides | read confidence, weighted allocation, prior prompt injection |
| `scripts/weakness_trend.py` | | **NEW** | | |
| `scripts/critique_memory.py` | | | **NEW** | |
| `scripts/confidence_calibrator.py` | | | | **NEW** |
| `hiveai/vectorstore.py` | | | add `exclude_book_ids` to both search functions | |
| `hiveai/chat.py` | | | pass exclude_book_ids to all search calls | |
| `hiveai/config.py` | | | add CRITIQUE_MEMORY_ENABLED | add CONFIDENCE flags |
| `hiveai/app.py` | | /api/eval/trends | /api/eval/critique-patterns, /api/eval/effective-templates | /api/eval/confidence |

---

## Data Flow (All Phases Integrated)

```
regression_eval.py runs 60 probes
    │
    ├──[Phase 0]──► skip failed/ in baseline, store eval_mode
    ├──[Phase 1]──► emit per-probe components (keyword_score, structure_score)
    │                  └──► append to weakness_trend.jsonl
    ├──[Phase 2]──► close_critique_loop(attempt_id, post_scores)
    ├──[Phase 3]──► compute_confidence_ledger() with eval_mode partition
    │
    └──► if regression: trigger weakness_hunter
              │
              ├──[Phase 0]──► correct language per category
              ├──[Phase 1]──► load trends → flag "resistant" probes
              ├──[Phase 2]──► retrieve past critiques → pick effective templates
              ├──[Phase 3]──► load confidence → weighted allocation + prior prompts
              │
              └──► generate_targeted_pairs (informed by all gems)
                      │
                      └──[Phase 2]──► store_critique_pattern(attempt_id)
                                        │
                                        └──► train → eval → close the loop

HivePoA Marketplace (separate system):
    │
    ├──► eval_sweep jobs → results ingested by regression_eval
    ├──► benchmark_run jobs → results ingested by regression_eval
    └──► [V1.1] domain_lora_train → adapters merged via dense-delta SVD
              └──► critique memory + confidence guide merge decisions
```

## GPT Feedback Scorecard

### Round 1

| GPT Critique | Valid? | Action |
|---|---|---|
| "Need per-probe component scores before GEM 1/2 work" | **YES** | Folded into Phase 1 (GEM 3) — not a separate phase |
| "failed/ entries contaminate baselines" | **YES** | Phase 0 bug fix |
| "weakness_hunter hardcodes python" | **YES** | Phase 0 bug fix |
| "No eval_mode in ledger" | **YES** | Phase 0 bug fix |
| "hop-2 bypasses hybrid_search filtering" | **YES** | Phase 2 — book_id exclusion in all paths |
| "Need critique_attempt_id, not fuzzy join" | **YES** | Phase 2 — UUID-based attempt tracking |
| "Reorder to: instrumentation → hygiene → GEM 1 → GEM 3 → GEM 2" | **PARTIALLY** | Bug fixes (Phase 0) go first. But instrumentation folds into GEM 3, not separate. Gem order unchanged. |
| "Use Wilson lower bound instead of Beta" | **NO** | Beta(1,1) prior achieves same conservatism, simpler |
| "Refuse to emit confidence below 2 samples" | **NO** | Beta prior handles this naturally — Beta(1,1) = "no opinion", system uses default allocation |
| "Choose one canonical eval source (60-probe vs 165-challenge)" | **YES** | All gems use 60-probe gate exclusively. 165-challenge eval is for release milestones only. |

### Round 2

| GPT Critique | Valid? | Action |
|---|---|---|
| "Causal attribution — attempt_id doesn't prove causality" | **YES** | `attribution` field: `isolated` (full weight) vs `batched` (0.3x weight in template effectiveness) |
| "Auto-recovery path only emits category scores" | **YES** | `_auto_mine_failures()` upgraded to emit full probe_details + trend classifications |
| "JSONL needs provenance for multi-worker future" | **YES** | Added `provenance` block: `scorer_version`, `probe_library_hash`, `git_sha` |
| "Posterior mean isn't conservative — use lower credible bound" | **YES** | `get_pair_allocation()` uses `alpha/(alpha+beta) - 1.28/sqrt(alpha+beta)` for decisions |
| "weakness_type needs deterministic classifier versioning" | **YES** | `WEAKNESS_CLASSIFIER_VERSION = 1` with explicit thresholds, stored in every record |
| "Critique patterns shouldn't have embeddings" | **YES** | `embedding = NULL` for critique BookSections. Queried by book_id + metadata only. |
