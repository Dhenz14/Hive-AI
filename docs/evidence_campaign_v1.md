# Frozen 30-Day Evidence Campaign Plan v1

## Status: FROZEN — Do not modify after preregistration (Day 3)

## Objective

Generate **50 valid real critique closures** under live Phase 2/3 semantics:
- 30 fit closures + 20 holdout closures
- 5 primary buckets, isolated attribution only
- All behavior gates OFF, no serving-model updates
- Disposable child checkpoints only — v5-think stays frozen

This is a **label-generation campaign**, not a product-improvement campaign.

---

## Success Criteria

Structurally successful if by Day 30:
- At least 40 valid closures (target: 50)
- At least 20 valid holdout closures
- At least 4 primary buckets with 8+ total closures
- At least 1 stratum with usable evidence (n >= 5)
- Zero contamination of live posterior from shadow data
- Zero probe leakage across fit/holdout
- Zero serving-path behavior change

Empirically successful only if Gates 5-6 pass on real data.
`insufficient_data` is still a valid outcome.

---

## Frozen Campaign Boundaries

| Parameter | Value |
|-----------|-------|
| Base model | v5-think (frozen, 94.65%) |
| eval_mode | full (60-probe) |
| weakness_classifier_version | 1 |
| success threshold | delta > 0.01 |
| attribution | isolated only |
| CRITIQUE_MEMORY_INFLUENCE | false |
| BAYESIAN_CALIBRATION_ENABLED | false |
| Serving checkpoint | unchanged for 30 days |
| Shadow data | usable_for_live_calibration=false |

---

## Target Buckets

### Primary (5)

| ID | Anchor Probe | Domain | Template | Target | Split |
|----|-------------|--------|----------|--------|-------|
| B1 | js-generics | JS | implement | 10 | 6 fit / 4 holdout |
| B2 | py-metaclass | Python | explain | 10 | 6 fit / 4 holdout |
| B3 | rs-ownership | Rust | debug_fix | 10 | 6 fit / 4 holdout |
| B4 | cpp-variadic | C++ | implement | 10 | 6 fit / 4 holdout |
| B5 | cpp-const | C++ | refactor | 10 | 6 fit / 4 holdout |

### Reserve (1)

| ID | Anchor Probe | Domain | Template | Use |
|----|-------------|--------|----------|-----|
| R1 | go-generics | Go | explain | Replace any primary that fails preregistration |

### Bucket freeze rule
5-tuple frozen on Day 2: `(full, 1, domain, classifier_emitted_weakness_type, template)`

---

## Diversity Requirements

All must be satisfied:
- At least 3 domains
- At least 2 distinct weakness types
- At least 3 templates
- No single domain > 40% of total closures
- No single template > 40% of total closures
- No single bucket > 25% of total closures

If fewer than 2 distinct weakness types across B1-B5, replace weakest bucket with R1.
If diversity still fails, abort and re-register.

---

## Probe Assignment and Holdout Rule

Each primary bucket needs:
- Minimum: 2 fit probes + 1 holdout probe
- Preferred: 2 fit + 2 holdout probes

Hard split rules:
- A probe in fit may NEVER appear in holdout
- A probe in holdout may NEVER appear in fit
- Violation invalidates all closures involving that probe

Frozen holdout cutoff:
- Fit window closes end of Day 21
- Holdout window begins start of Day 22

Bucket validity: if a bucket can't produce 2 fit + 1 holdout by Day 3, replace with reserve.

---

## Attempt Recipe

Each attempt = one Bernoulli trial, one critique closure.

### Structure
1. Start from frozen v5-think base
2. Train disposable child checkpoint (one isolated micro-cycle)
3. Run full 60-probe eval
4. Close critique loop by exact attempt_id
5. Archive metrics
6. Discard child checkpoint — NEVER promote to serving

### Pair pack (400 total per attempt)
- 240 fresh targeted pairs (weakness_hunter + retrieval)
- 120 matched historical pairs (from 280K corpus, same domain/weakness/template)
- 40 stability/control pairs (high-quality in-domain)

### Pair rules
- Historical pairs = training material only, never evidence
- No holdout probe text/answers in any pack
- Dedupe all packs against holdout probe set
- Content hash logged per pack

---

## Campaign Structure

10 micro-campaigns x 5 attempts each = 50 total attempts

Interleaves buckets over time — prevents one domain from dominating.

---

## Timeline

### Days 1-3: Preregistration
- Day 1: Freeze campaign manifest (model hash, eval hash, thresholds, gates, buckets)
- Day 2: Run weakness_hunter on anchors, freeze emitted weakness_types, verify diversity
- Day 3: Assign probe bundles, split fit/holdout, commit prereg manifest

### Days 4-7: Dry-run and pack generation
- Day 4: Build pair pack generator for all 5 buckets
- Day 5: Leakage audit (holdout probe dedupe, content hashes, attribution check)
- Day 6: 2 baseline full eval reruns on unchanged v5-think
- Day 7: Verify baseline stability (abort if variance > 0.5 overall or > 1.0 per probe)

### Days 8-21: Fit phase
- 6 micro-campaigns (30 fit attempts, 6 per bucket)
- ~2-3 attempts/day, ~2 hours/day
- End of Day 21: freeze fit artifact (counts, usable flags, reliability data)

### Day 22: Freeze fit artifact
- No training. Write and freeze fit-side calibration snapshot.

### Days 23-29: Holdout phase
- 4 micro-campaigns (20 holdout attempts, 4 per bucket)
- Only holdout-assigned probes. No fit probes.

### Day 30: Final audit and verdict
- Run Gates 5-6 on real data
- Stratified report, survivorship audit, prior-only share, sparsity report
- Final go/no-go memo

---

## Weekly Audit Metrics

### Core counts
- Attempts: started, open, closed, abandoned, invalidated

### Quality
- Median closure latency, closure rate, abandonment rate, invalidation rate

### Calibration readiness
- Fit closures, holdout closures, prior-only share, usable-bucket share
- Evidence count by bucket/domain/template

### Bias/sparsity
- Closure share by domain/template/bucket
- Success rate by bucket and phase
- Concentration index (top bucket share)

### Hard thresholds (alert if violated)
- Abandonment rate > 20%
- Invalidation rate > 10%
- Any domain > 40% of closures
- Any template > 40% of closures
- Any bucket > 25% of closures
- Prior-only share > 80% after Day 21
- Median closure latency > 48h

---

## Stop Conditions

### Normal stop
All true: 50 valid closures, 30 fit / 20 holdout, 5 buckets represented, 4+ with 8+ closures, Day 30 audit done.

### Early stop (all must be true)
- 40+ valid closures, 20+ holdout, 4+ buckets with 8+, Gates 5-6 run, 1+ usable stratum, no audit violations

### Budget stop
Hard ceiling: 60 attempts. If insufficient by 60, declare "insufficient real evidence; continue paused state."

---

## No-Go Rules

Abort or invalidate if ANY occur:
1. Holdout probe leaks into training material
2. Probe appears on both sides of split
3. Any parameter changes after Day 3 preregistration
4. Any behavior gate turned on
5. Any child checkpoint promoted to serving
6. Any attempt lacks exact attempt_id closure
7. Shadow/synthetic record enters live calibration
8. Baseline eval instability exceeds threshold
9. Bucket can't supply minimum probe bundle
10. >20% of attempts in a week invalidated or abandoned

---

## Expected Outcomes (Day 30)

### Outcome A — Empirically validated
Gates 5-6 pass, 1+ usable stratum, posterior evidence-backed.
→ Phase 3 empirically credible. Phase 4 still OFF pending separate decision.

### Outcome B — Structurally sound, empirically insufficient
No contamination, audits clean, but not enough usable evidence.
→ System says "I don't know yet." Run second evidence window.

### Outcome C — Data invalid
Leakage, instability, or concentration bias broke protocol.
→ Discard affected subset. Do not consume. Re-register.

---

## Use of 280K Distilled Pairs

- Training material only (120 matched historical pairs per pack)
- NEVER evidence, NEVER live posterior seed, NEVER backfilled critique history
- Filtered by domain + weakness family + template style
