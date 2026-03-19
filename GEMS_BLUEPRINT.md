# HiveAI Gems Blueprint — Master Status (2026-03-16)

## How to Read This

Three layers, like building a bridge:
- **Foundation** = ground already laid, validated, in production
- **Beams** = next implementation work, ordered by dependency
- **Bridge** = features that sit on top of the beams, build later

Plus: **Archive** (dead/shelved, reference only) and **Watch List** (research, no action yet).

---

## FOUNDATION (Done, Validated, In Production)

These are not gems — they're the ground the gems stand on. Do not modify without good reason.

| Component | Status | Commit/Gate |
|-----------|--------|-------------|
| v5-think base model (94.3%, Q5_K_M) | FROZEN | Serving on llama-server:11435 |
| Layer 1 RAG (22 books, 434 sections, hybrid search) | LIVE | Gate 12 PASS |
| Promotion bridge (verified → BookSection → retrieval) | LIVE | Gate 6 + Gate 10 PASS |
| Product telemetry (3-arm experiment architecture) | LIVE | Commit 7527e7e, freeze 9c5286a |
| v1.1 protocol hardening (output contract, oracle harness) | DONE | Tickets T1+T2 complete |
| DBC on-chain pair proposals + HP-weighted voting | LIVE | chain.py + node.py |
| HivePoA V1 compute (eval_sweep + benchmark_run jobs) | LIVE | worker.py + verifier.py |
| Phase 0 bug fixes (failed/ filter, language map, eval_mode) | DONE | Commit d364136 |
| Phase 1 GEM 3: Probe telemetry + weakness trending | DONE | Commit d364136, 5/5 validated |

**State discipline**: WSL `/opt/hiveai/project/` is canonical for ALL persistent state files (score_ledger.json, weakness_trend.jsonl, future confidence_ledger.json). Windows is for code edits only.

**External validation (2026-03-18)**: 0xSero autoresearch post independently confirms our system integrity design. Their Experiment 2 drifted overnight due to loose objective + infrequent checkpoints + context pollution — exactly the failure mode `campaign_governance.py` prevents (dirty-tree gate, cold-start admission, one-artifact-per-run, hash pinning). No action required. Design confirmed.

**Trust model**: Anti-cheating measures (Web of Trust, DBC voting, miner reputation) target untrusted marketplace participants — these are HivePoA's domain. System integrity controls (fail-closed gates, hash pinning, dirty-tree checks) protect experiment reproducibility — these are Hive-AI's domain. Trusted validators are trusted by design via Web of Trust; do not build controls to police them.

---

## BEAMS (Next Work, In Dependency Order)

Build these in order. Each beam enables the ones below it.

### Beam 1: Phase 2 — GEM 1: Critique Pattern Memory
**Depends on**: Phase 1 (DONE)
**Enables**: GEM 2, distributed weakness hunting, template optimization
**Scope** (locked by GPT review):
- `scripts/critique_memory.py` — store/close/retrieve critique patterns
- BookSection with `embedding = NULL`, `source_type = "critique_pattern"`
- Explicit `attempt_id` (UUID) for loop closing
- `attribution` field: `isolated` (1.0 weight) vs `batched` (0.3 weight)
- `exclude_book_ids` in vectorstore.py + chat.py (all search paths)
- `CRITIQUE_MEMORY_ENABLED` config flag
- API endpoints: `/api/eval/critique-patterns`, `/api/eval/effective-templates`

### Beam 2: Phase 3 — GEM 2: Bayesian Confidence Calibration
**Depends on**: GEM 1 (for template effectiveness data)
**Enables**: Smart pair allocation, prior prompt injection
**Scope** (locked by GPT review):
- `scripts/confidence_calibrator.py` — Beta distributions, pair allocation, prior prompts
- `confidence_ledger.json` — recomputed on each eval, partitioned by eval_mode
- Actual Beta quantile (scipy.stats.beta.ppf) for conservative allocation decisions
- `build_prior_prompt()` for weakness_hunter prompt injection
- `CONFIDENCE_CALIBRATION_ENABLED`, `CONFIDENCE_WINDOW_SIZE`, `CONFIDENCE_PRIOR_INJECTION` config flags
- API endpoint: `/api/eval/confidence`

### Beam 3: Small Cleanups + Layer 1 Enhancements (Independent, Do Anytime)

These are small, self-contained, and don't block each other:

| Item | Scope | Status | Why |
|------|-------|--------|-----|
| ~~execution_language split~~ | ~20 lines | **DONE** (2026-03-18) | DB schema was already clean; removed redundant field from sandbox.py, cleaned fallback chain in app.py |
| ~~Go verifier~~ | sandbox.py | **DONE** (pre-existing) | `execute_go()` already exists at sandbox.py:766-881 |
| ~~Rust verifier~~ | sandbox.py | **DONE** (pre-existing) | `execute_rust()` already exists at sandbox.py:655-764 |
| ~~Go/Rust canonical harnesses~~ | ~180 lines | **DONE** (2026-03-18) | 3 Go + 3 Rust harnesses + multi-language dispatch in canonical_harness.py |
| ~~CATEGORY_LANGUAGE in CLAUDE.md~~ | ~10 lines | **DONE** (already present) | Policy needs central management |
| **Query Normalizer** | ~100 lines + flag | Pending | Tighter BGE-M3 clusters for Gate 11. Enable only after shadow validation. |

#### Query Normalizer — Detail

**Status**: Build anytime. Enable only after shadow validation passes.

**What it is**: A component that rewrites raw user queries into dense structured form *before*
they hit the BGE-M3 embedding model. The hypothesis is that promoted examples (verified against
structured code queries) and raw natural-language retrieval queries don't share the same semantic
neighborhood in embedding space — and that bridging that gap improves recall.

**Coupling warning — implementation-local, behavior-global**: This sits in `vectorstore.py`
at the retrieval entry point. Even though the code footprint is small (~100 lines + flag), it
affects *every path that calls retrieval*: promoted-example lookup, book retrieval, hop-2, critique
lookup, and any evals that depend on ranking. Low code coupling does not mean low behavioral reach.
The flag-gate contains the risk; casual enabling does not.

**This is still a hypothesis.** It assumes:

1. The current miss is primarily embedding-space mismatch (not reranking, prompt construction, or use-side acceptance)
2. Normalization improves alignment more than it destroys discriminative specificity
3. BGE-M3 is not already handling paraphrase variance internally
4. Failure is retrieval-side, not downstream

**Biggest failure mode — semantic over-smoothing**: Aggressive normalization can move the query
into a broader neighborhood, hurting recall for cases where the raw query contains discriminative
structure (code syntax, exact error strings, unusual token mixes, probe-local phrasing).

**Input → Output example**:

```text
In:  "i want to do something like async but blocking in rust without tokio"
Out: [L:rs] [GOAL:async→sync blocking wrapper] [CONSTRAINT:!tokio std::thread]
```

**Scope**:

- `scripts/query_normalizer.py` — normalizer logic (rule-based + optional tiny LLM fallback)
- Hook into `hiveai/vectorstore.py` at the retrieval entry point (primary + hop-2 + book-ref paths)
- Config flag: `QUERY_NORMALIZER_ENABLED=false` (default off — enable only after shadow validation)
- Raw query always preserved in logs for audit and rollback comparison
- Normalization must be deterministic and idempotent
- Graceful degradation: normalizer failure falls through to raw query
- Telemetry: log `query_normalized=true/false`, both raw and normalized form, on every retrieval event

**Implementation path**:

1. Rule-based first: regex + keyword extraction covers ~60% of coding queries with zero model cost
2. Tiny LLM fallback (Qwen2.5-0.5B via llama-server) for complex queries
3. Shadow mode: run normalizer silently, log both results, compare offline before enabling

**Shadow validation gate (must pass before enabling)**:

Two requirements, both mandatory:

**Requirement 1 — Slice composition**. The validation set must include a representative and
adversarial mix. If the slice is dominated by easy paraphrastic cases, normalization will look
better than it is. Required coverage before the five questions are meaningful:

| Query class | Why required |
| --- | --- |
| Paraphrase-heavy | Tests the best-case gain the hypothesis predicts |
| Syntax-heavy (code snippets in query) | Tests the primary over-smoothing failure mode |
| Exact-string / error-text | Tests precision loss on discriminative surface cues |
| Probe-local phrasing | Tests whether eval-critical queries degrade |
| Short / ambiguous | Tests false-positive normalization |

**Requirement 2 — Per-record validation artifact**. Each shadow record must bind:

- raw query
- normalized query
- top-k before (ids + scores)
- top-k after (ids + scores)
- overlap count / new entrants / dropped items
- downstream usefulness outcome (retrieved item used in response? verified pass/fail?)
- query class tag (from the five classes above)

"Overall improvement" without query-class breakdown hides the over-smoothing failure. The five
questions below must be answered *per class*, not just in aggregate.

**Requirement 3 — Five questions, answered per class**:

1. How often does normalized top-k differ from raw top-k?
2. Are newly surfaced items actually better, or just different?
3. Does recall improve without collapsing precision?
4. Do exact-match / syntax-heavy / error-string cases degrade?
5. Does this help only promoted examples, or does it perturb general book retrieval too much?

Enable only if: paraphrase-heavy improves AND syntax-heavy/exact-string do not degrade.

**Expected impact if hypothesis holds**: Potentially accelerates Gate 11 (≥50% retrieved on
relevant follow-ups) *if current failures are driven by raw-vs-promoted query embedding mismatch*.
Not guaranteed — Gate 11 could be bottlenecked by reranking, prompt construction, attribution
filtering, or acceptance policy instead.

**Does NOT require**: weight mutation, new training data, changes to BGE-M3, changes to promotion logic.
**Rollback**: one flag switch, no code unwind required.

### Beam 4: Telemetry Validation Gate → Read Treatment Effects
**Depends on**: Enough usage data accumulated
**Scope**: Run the 5-point validation gate, then staged analysis (global lift → workflow segmentation → confidence band → language splits)
**Blocked by**: Data volume, not code. Check periodically.

### Beam 5: Domain LoRA CLI Flags (MoLoRA Production)
**Depends on**: v5-think frozen (DONE), domain-isolated architecture design (DONE)
**Enables**: Production MoLoRA routing with trained per-domain adapters
**Status**: **IMPLEMENTATION COMPLETE** (commit c0ea6d5). Runtime validations 2/3 closed.
**Scope** (5 concrete items — all implemented):

1. ~~Add `--target-layers` and `--target-modules` CLI flags to train_v5.py~~ DONE
2. ~~Add `layers_to_transform` passthrough to all 3 LoRA application paths~~ DONE (incl. PEFT use_rslora fix)
3. ~~Post-apply assertion (use_rslora, layers_to_transform, target_modules)~~ DONE
4. ~~Create `loras/domains/` folder structure + domains.json manifest~~ DONE
5. ~~Add `--adapter-template` flag (hive/cpp/generic) as shortcut~~ DONE

**Runtime validations**:

- ~~Bad input parse (`--target-layers "24-25-26"` → ValueError)~~ PASS (2026-03-18)
- use_rslora PEFT path — closed by code inspection (line 771), full GPU test deferred
- Manifest read path — blocked on Bridge A (domains.json exists but no consumer yet)

---

## BRIDGE (Later — Builds on Beams)

These only become actionable after the beams are in place.

### Bridge A: HivePoA V1.1 Training Jobs
**Depends on**: Beams 1+2 (GEM 1+2 for smart merge decisions), Beam 5 (domain LoRA flags)
**Integration contract**: `docs/HIVE_AI_INTEGRATION.md` (synced from HivePoA be04c4a)
**Architecture**: HivePoA owns compute marketplace. Hive-AI owns intelligence. `compute_client.py` is the only coupling point.
**Scope** (Hive-AI side only — HivePoA handles scheduling/payment):
- Sync `schemas/` from HivePoA + Python conformance tests
- `domain_lora_train` worker job type in compute/worker.py
- `weakness_targeted_generation` worker job type
- `adapter_validation` worker job type
- Dense-delta SVD merge for combining contributed adapters (~20 lines torch)
- Verifiable shard randomness (block_hash + miner_account_id seed)
- Human seed ratio floor (30% minimum human-sourced pairs per training mix)
- Provenance collection in GPUWorker
- IPFS upload/download in compute_client.py

### Bridge B: Distributed Weakness Hunter Loop
**Depends on**: Bridge A (training jobs live), all 3 gems operational
**Scope**: After each global merge, miners run weakness_hunter against new model + their local shard. Synthetic pairs get DBC-voted, winners feed next training contract.
**Why it needs gems**: Without critique memory + confidence, synthetic data compounds errors.

### Bridge C: Layer 3 Periodic Promotion
**Depends on**: ~~Beam 3 (Go/Rust verifiers)~~ DONE, Layer 1 Gate 5 (auto-staging), skill candidate clustering
**Scope**: Event-driven training only when ALL 4 conditions met:
1. Repeated miss in real use
2. Retrieval too slow (Layer 1 insufficient)
3. Executable eval exists for the domain
4. Big expected gain (>3%)
**Policy**: Do NOT train because model saw something new once.

### Bridge D: DiLoCo Protocol (Research)
**Depends on**: Bridge A working with basic federated rounds
**Scope**: Replace multi-round FedAvg with DiLoCo (Distributed Low-Communication Optimization). Hundreds of local steps, rare outer syncs. FedMomentum preserves optimizer state.
**Why later**: Only matters with 5+ concurrent miners.

---

## ARCHIVE (Dead, Shelved, or Superseded — Reference Only)

These are NOT coming back unless explicitly triggered. Do not work on them.

| Item | Status | Why Archived |
|------|--------|-------------|
| ts-generics adapter | SHELVED | +3.3% avg, only 1/5 prompts improved, 66 pairs too few. Pipeline validation only. |
| cpp-lifetime adapter | SHELVED | 3 runs inconclusive. Variant damage is structural, not capacity-related. 150 pairs insufficient. |
| EWC v1 | BROKEN | Fisher penalty domination. STM+SDFT v5.0 supersede. Never re-enable. |
| DELLA pruning | BROKEN | 3.33x rescaling corrupts PEFT merges. DO NOT USE. |
| SGLang backend | PARKED | Chat template incompatibility with gpt-oss-20b. llama-server stable. No urgency. |
| gpt-oss-20b model | PARKED | 3/10 vs v5-think 7/10. Chat template issue, not model quality. |
| Golden chain iterations | FROZEN | v5-think is the ceiling for sequential merge. Use adapters for slice-specific gains. |
| Keyword-only eval as optimizer | DEPRECATED | ±5.6% noise, synonyms score 0. 60-probe eval for regression only, not training optimization. |
| ICL-conditioned teacher (SDFT v5.1) | FUTURE | v5.0 baseline sufficient. Only revisit if SDFT mixing ratio needs refinement. |

---

## WATCH LIST (Research, No Action Yet)

| Technique | Territory | Trigger to Activate | Source / Notes |
|-----------|-----------|-------------------|-------|
| Padding-Free Sequence Packing | **Hive-AI** | Next campaign run — use `--packing` flag. STM boundary fix implemented; validate STM mask density matches non-packed baseline before promoting to standard runs. | Unsloth December 2025. 3x faster training + 30% VRAM reduction. **Fix implemented (commit 241488d)**: Unsloth removes `attention_mask` from batch and replaces with `packed_seq_lengths`. STM and `_chunked_log_probs` (SDFT) now pass `packed_seq_lengths` through to base model so flash-attn varlen kernel handles sequence boundary isolation. Without the fix, all-ones fallback caused cross-sequence attention leakage in per-token PPL. Validation gate: run one B-series bucket with `--packing`, compare STM mask density % and SDFT KL magnitude against equivalent non-packed run. If statistically indistinguishable, promote to default. |
| FP8 Training | **Hive-AI** | When VRAM is the binding constraint during Layer 3 AND boundary probe stability has been validated at FP8 precision. | Unsloth 2025. 1.4x speed + 60% VRAM on Ada Lovelace hardware (RTX 4070 Ti SUPER is Ada = supported). Triton block-wise FP8 with per-tensor/per-row scaling. **Risk for our pipeline**: (1) STM per-token PPL computed in FP8 — underflow near threshold boundary (default 2.5) could cause mask to flip incorrectly. (2) SDFT reverse KL mixing — FP8 KL values near zero could round to zero, effectively disabling the anti-forgetting term silently. Validate: run one B-series bucket at FP8, compare STM mask density and SDFT KL magnitude against bf16 baseline. Only activate if KL and PPL distributions are statistically indistinguishable. |
| QAT (Quantization-Aware Training) | **Hive-AI** | If per-probe analysis shows a measurable gap between bf16 eval scores and Q5_K_M serving scores on boundary-sensitive probes. | Unsloth/PyTorch collaboration October 2025. Recovers up to 70% of accuracy lost during post-training quantization by simulating quantization noise during training. Relevant to our bf16 → Q5_K_M conversion step — boundary-sensitive probes (py-metaclass, js-generics, cpp-variadic) that sit near the score boundary are the most likely victims of quantization degradation. Current evidence: we do not know whether our -0.1166 anchor deltas are training effects, measurement effects, or quantization effects. QAT is not worth activating until quantization is isolated as a contributor. Trigger: run identical eval on bf16 child (no quantization) vs Q5_K_M child and compare anchor probe scores. |
| DOC/OSFT (Dynamic Orthogonal CL) | **Hive-AI** | If MoLoRA hits cross-adapter interference | arXiv 2509.23893 |
| RFT/GRPO (RL Fine-Tuning) | **Hive-AI** | After executable eval gates are robust for all 6 languages | arXiv 2507.05386 |
| TreeLoRA (Hierarchical LoRA Org) | **Hive-AI** | When active adapter count exceeds 5 | arXiv 2506.10355 |
| SEE (Sequential Ensemble of Experts) | **Hive-AI** | ALREADY MATCHES our architecture conceptually — no new code needed | arXiv 2504.06664 |
| REAP Expert Pruning (static compression) | **Hive-AI** (VRAM) / **HivePoA** (miner serving) | Hive-AI: when base model exceeds 14B parameter budget on RTX 4070 Ti SUPER 16GB. HivePoA: when miners need to serve 70B+ models on consumer GPU rigs. | reap-expert-swap (open source). 7.8× BF16 compression (717GB→92GB) via expert pruning + INT4. Key finding: 7.6% of experts per layer carry 50% of routing traffic — independently confirms our layer-selective LoRA targeting (layers 24-39, 16-31) is sound. **Pair with MoE Staging Buffer below** — REAP decides what to keep; staging buffer decides what to load. Together they form the full MoE efficiency stack. |
| MoE Expert Staging Buffer Inference (dynamic serving) | **HivePoA** (miner economics) / **Hive-AI** (future base model) | HivePoA: when miners want to serve 70B+ MoE models on consumer GPUs without server VRAM. Hive-AI: if base model is ever upgraded to a MoE architecture (Qwen3-MoE, Mixtral, Step-3.5, etc.). | Step-3.5-Flash (197B, 394GB BF16 → 6.29GB active VRAM, ~62× peak reduction). Architecture: non-expert skeleton (~6.1GB) lives permanently on GPU. 8-slot staging buffer (66.8MB) overwritten per layer by router-selected experts via DMA. Expert tensors: 0 on GPU at rest. Memory invariant: GPU after token 1 = GPU after token 100 = 6,286MB, delta 0.0MB. 12,096 unique experts managed entirely off-GPU. Architecture is model-agnostic — any MoE, any size. **Key test pattern**: assert flat VRAM profile at token 1, 10+, 100 + assert expert tensors on GPU = 0. This is the companion to REAP: REAP prunes which experts exist; staging buffer governs which are hot at any moment. Current ceiling on single consumer GPU: ~15 tok/s (short). Performance at scale on 8×RTX 3090: Kimi-k2.5 running (0xSero). |
| MCP Server Interface for RAG | **Hive-AI** (Claude Desktop / cross-client) / **HivePoA** (knowledge query interface) | When HivePoA miners or Claude Desktop need to query Hive-AI's knowledge base without HTTP/Flask dependency. OR when we want native tool-call access to RAG from Claude Code itself. | TurboVault (github.com/Epistates/turbovault) implements MCP server wrapping a knowledge graph + Tantivy search as 44 typed tools with `StandardResponse<T>` envelope (duration_ms, warnings, next_steps fields). Key insight: MCP is Anthropic's native tool protocol — an MCP wrapper around our BookSection/RAG system would let Claude Code call retrieval as a first-class tool rather than via HTTP. Current blocker: Flask API already works and we have no cross-client requirements yet. Activate when: (a) HivePoA needs to query Hive-AI knowledge programmatically, or (b) Claude Desktop integration becomes a product requirement. Note the `StandardResponse` pattern is worth adopting now — adding `duration_ms` and estimated token counts to our existing API responses costs nothing and improves orchestration decisions. |
| Progressive Disclosure RAG | **Hive-AI** | When BookSection count exceeds ~1000 AND base model upgrades to stronger instruction-following (Qwen3+). | Inject lightweight index (title + summary + score) instead of full sections; model requests content on demand. Saves tokens, improves precision. **Not justified at current scale** (434 sections, budget_context already filters to 2-3 sections avg). Latency cost: 30-50% (2-3 LLM calls vs 1). 14B model too weak for reliable structured request parsing. Simpler wins first: cross-encoder reranking (already live at chat.py:545), adaptive suppression thresholds, top-3 section cap. Revisit when KB scales 3x+ or base model improves. Audited 2026-03-18. |
| Tantivy Full-Text Search | **Hive-AI** | If SQLite FTS5 becomes a throughput or ranking-quality bottleneck as BookSection count scales past ~50k. | TurboVault uses Tantivy (Rust, Lucene-inspired, BM25+TF-IDF) achieving sub-100ms full-text search on 10k+ docs with ~80MB in-memory index. Our current SQLite FTS5 is working well at current scale (~434 sections). Tantivy's advantage at scale: better ranking, fuzzy matching (Levenshtein 1), field-specific queries, in-memory index. Cost: adding Rust/Python bindings (tantivy-py exists) to a Python stack. Not worth switching until FTS5 latency or ranking quality is a measured problem. |
| eBPF Compute Worker Sandboxing | **HivePoA** | When HivePoA runs untrusted training jobs from marketplace miners (i.e., when compute_client.py dispatches jobs to unknown workers). | Kavach (github.com/LucidAkshay/kavach) plans eBPF-based syscall interception for v2.0 Linux. The primitive: intercept file system + process + network syscalls at kernel level before they reach user space, with approve/deny/ghost semantics per call. For HivePoA: miners accept compute jobs from strangers — eBPF sandboxing of the worker process is the correct containment layer (not OS-level chroot, not Docker alone). Pairs with resource throttling (CPU/RAM limits on worker PIDs). Kavach implementation is early-stage and incomplete (no Linux support yet, CSP disabled) — extract the concept, not the dependency. When to activate: before HivePoA opens to untrusted miners. |
| Behavioral Heuristics for Worker Containment | **HivePoA** | When compute marketplace opens to non-vetted miners and job payloads are externally submitted. | Three patterns from Kavach directly applicable to HivePoA worker monitoring: (1) velocity detection — flag rapid sequential file modifications (runaway training loop or data exfiltration); (2) recursive loop detection — catch infinite child-process spawns from malformed training jobs; (3) dynamic resource throttling — CPU/RAM hard caps on worker PIDs enforced in-flight, not just at launch. These are heuristic guards, not cryptographic proofs — pair with DBC voting and miner reputation score for defense-in-depth. |
| Autoresearch Distributed Research Loop | **HivePoA** (infrastructure) / **Hive-AI** (experiment format + data feed) | HivePoA: when stable job dispatch is live and ≥10 active miners. Hive-AI: campaign artifact schema already defines the shareable experiment format. | autoresearch@home (open source). 95 agents, 2600+ experiments, agents read each other's results and pivot strategy in real time. By day 3: architectural breakthroughs. This is the spirit bomb GPU effect in prototype form. HivePoA owns the coordination and compute; Hive-AI contributes the governed experiment format (campaign artifacts as shared state). Bottleneck today: sandbox tooling, CUDA permissions, API key plumbing — not intelligence. Key design lesson: one-experiment-per-call with strict accept/revert gate; context window overflow is the primary drift mechanism. |

---

## CONFLICT CHECK (Resolved)

| Potential Conflict | Resolution |
|---|---|
| MoLoRA routing vs domain-isolated LoRA CLI flags | Same feature at different stages. CLI flags (Beam 5) enable MoLoRA production. |
| Golden chain FROZEN vs 3 gems | No conflict. Gems improve the *improvement loop intelligence*, not the training architecture. Golden chain stays frozen. |
| Keyword eval DEPRECATED vs 60-probe regression eval | 60-probe eval is the surviving version. Now has component scores (Phase 1). Use for regression gating, not training optimization. |
| STM/SDFT v5.0 vs EWC v1 | EWC is dead. STM+SDFT won. No conflict. |
| Layer 1 (RAG) vs Layer 3 (training) | Complementary. Layer 1 = retrieval at query time. Layer 3 = rare, event-driven training. |
| Query Normalizer vs raw retrieval | Implementation-local, behavior-global. Flag defaults off. Build anytime; enable only after 5-point shadow validation gate passes. Rollback is one switch. |
| Distributed training gems vs local 3 gems | 3 gems are the intelligence layer (what to train). Distributed gems are the execution layer (who trains). Build intelligence first (Beams 1-2), then distribute (Bridge A-B). |
| Product telemetry vs probe telemetry | Different systems. Product telemetry = 3-arm A/B test on memory injection UX. Probe telemetry = per-probe eval component scores for the training loop. No overlap. |

---

## EXECUTION PRIORITY (Updated 2026-03-18)

**Completed**: Beam 1 (structural), Beam 2 (structural), Beam 3 (all items), Beam 5 (implementation)
**Blocked on data**: Beam 4 (telemetry volume), GEM 1+2 empirical gates (real training cycles)
**Next actionable**: RAG improvements (shadow reranker live, composite confidence calibration next)

After RAG: Bridge A (HivePoA V1.1 training jobs) → Bridge B (distributed weakness hunter).
