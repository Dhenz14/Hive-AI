# Phase 3 (GEM 2) Acceptance Gates — Bayesian Confidence Calibration

## Scope

Phase 3 proves one narrow claim:

**Given a 5-tuple bucket `(eval_mode, weakness_classifier_version, domain,
weakness_type, template)`, the system can emit a calibrated confidence value
whose empirical correctness matches its stated confidence better than the
bucket MLE, on held-out data, without changing generation behavior.**

Phase 3 does NOT include:
- template weighting that changes prompts
- pair allocation logic
- routing decisions
- retry / abstain / escalate policy
- critique-memory influence (CRITIQUE_MEMORY_INFLUENCE stays false)
- reward shaping

Those are consumers of calibrated confidence. They belong to Phase 4+.

---

## Semantic Contract (Gate 1 prerequisite)

### Calibration model

Pure Bernoulli-Beta conjugate updating. Each closed critique attempt
contributes exactly one binary observation (success or failure) to its
bucket's posterior. No fractional pseudo-counts, no evidence weighting.

Attribution (`isolated` vs `batched`) is a **stratification dimension for
reporting**, not a weighting signal in the posterior. `get_effective_templates()`
uses weighted scoring for template ranking — that is a separate system, not
the calibrator. Two clean tools, not one conflated one.

### Contract table

| Field | Definition |
|-------|-----------|
| **Calibrated target** | `P(fix_succeeded == True)` — binary: did delta exceed the success threshold? |
| **Success threshold** | `delta > 0.01` (one percentage point). Below that is measurement noise on 60-probe eval where each probe contributes ~1.67% to domain score. |
| **Prediction unit** | One closed critique pattern (one `attempt_id`) |
| **Label source** | `close_critique_loop()` → `fix_succeeded = (post_score - pre_score > 0.01)` |
| **Prior** | Beta(1, 1) — uniform, uninformative |
| **Update rule** | Pure conjugate: Beta(1 + successes, 1 + failures) per bucket. Each closed attempt = one Bernoulli trial. No fractional counts. |
| **Bucket key (5-tuple)** | `(eval_mode, weakness_classifier_version, domain, weakness_type, template)` |
| **Evidence fields** | `fix_succeeded` (binary, the only field that updates the posterior) |
| **Stratification dimensions** | `attribution` (isolated/batched) — reported separately, does NOT weight the posterior |
| **Partition dimensions** | `eval_mode`, `weakness_classifier_version` — define which bucket, never pooled across values |
| **Excluded fields** | `pre_score` magnitude, `post_score` magnitude, `pairs_generated`, response content, attribution weight |

Label timing: confidence is computed AFTER closure, never on open/abandoned attempts.
Stale/abandoned attempts: excluded from fitting entirely — they carry no outcome signal.

---

## Gate 1 — Semantic contract is explicit

A spec exists (this document) stating:
- calibrated target variable and success threshold
- prediction unit
- label source
- prior definition
- update rule (pure conjugate, no fractional counts)
- bucket key (5-tuple, explicitly enumerated)
- evidence fields (only `fix_succeeded`)
- stratification dimensions (reported, not fitted)
- partition dimensions (fitted separately, never pooled)
- fields explicitly excluded

**Pass**: All fields above are unambiguous, documented, and match implementation.
**Fail**: Any field is missing, ambiguous, or contradicts implementation.

---

## Gate 2 — No-op safety is preserved

Phase 3 ships with:
- `BAYESIAN_CALIBRATION_ENABLED=false` by default
- No generation-path behavior changes when disabled (or enabled)
- Read-only inspection endpoints only
- Stored calibration artifacts are observational only
- `CRITIQUE_MEMORY_INFLUENCE` remains false

**Pass**: Disabling the flag produces identical chat behavior. Enabling it
adds observability fields but changes no ranking, retrieval, or prompt.
**Fail**: Any code path reads calibration output to change generation behavior.

---

## Gate 3 — Training/eval leakage is impossible

Calibration fitting and validation use separate data:

- **Time-based holdout**: fit on attempts closed before cutoff T, evaluate
  on attempts closed after T. No random split.
- **Partition-aware**: attempts from different `eval_mode` or
  `weakness_classifier_version` are never pooled.
- **No retry leakage**: if the same (domain, probe_id) has multiple
  attempts, all attempts for that probe must be on the same side of the
  split. Split by probe, not by attempt.

**Pass**: Validation function accepts explicit `fit_cutoff` datetime and
enforces probe-level grouping. No attempt straddles train/test.
**Fail**: Fit and score on same attempts, or retries of same probe leak
across split boundary.

---

## Gate 4 — Posterior behavior is sane

### 4a — No extreme confidence under low counts
- Beta(1,1) → posterior mean = 0.5, never 0.0 or 1.0
- Beta(2,1) → 0.667, not 1.0
- Any bucket with alpha + beta < 5 must report `insufficient_data=true`

### 4b — Posterior interval narrows with evidence
- Beta(2,1) has wider 90% credible interval than Beta(20,10)
- Verified programmatically

### 4c — Confidence is monotone in positive evidence
- Adding a success must not decrease posterior mean
- Adding a failure must not increase posterior mean

### 4d — Contradictory evidence widens uncertainty
- Beta(5,5) has wider interval than Beta(5,1) or Beta(1,5)
- Mixed evidence produces lower effective confidence than pure evidence

**Pass**: All four sub-checks verified by unit test on synthetic data.
**Fail**: Any sub-check violated.

---

## Gate 5 — Calibration improves on held-out data

### Baseline comparator

The baseline is the **bucket MLE**: `successes / total` for each 5-tuple
bucket. This is the simplest non-trivial estimator. The calibrated posterior
must outperform it. The weighted template effectiveness score from
`get_effective_templates()` is a separate ranking tool and is NOT the
baseline for calibration comparison.

### Three diagnostics required (not one):

### 5a — Reliability diagram improvement
- Bin predicted confidence into 5 equal-width bins (0-0.2, 0.2-0.4, ..., 0.8-1.0)
- Plot observed success rate vs mean predicted confidence per bin
- Both MLE baseline and calibrated posterior plotted
- Calibrated predictions must be closer to the diagonal than MLE baseline
- Report per-bin deviation for both

### 5b — ECE improvement
- Expected Calibration Error (weighted by bin count)
- Calibrated ECE < MLE baseline ECE on held-out data
- Report both values and the delta
- Acknowledge: ECE alone is insufficient (binning-sensitive, can hide local failures)

### 5c — One proper scoring rule tracked
- Brier score computed on held-out data for both MLE and calibrated posterior
- Report both values but do NOT use Brier alone as proof of calibration
- Purpose: detect if calibration improved discrimination at the cost of
  calibration (or vice versa)

**Pass**: 5a shows visible diagonal improvement over MLE, 5b shows ECE
reduction vs MLE, 5c is reported for both.
**Fail**: Any of 5a/5b shows degradation vs MLE on held-out data.

**Minimum data requirement**: Gate 5 cannot be evaluated with fewer than 20
closed attempts in the held-out set. If insufficient data exists, Gate 5
verdict is `insufficient_data`, not `fail` — and Phase 3 is considered
structurally complete but empirically unvalidated.

---

## Gate 6 — Stratified performance is visible

Overall calibration can hide serious local failures. Report separately for:

- `eval_mode` (quick vs full) — never pooled in fitting, reported separately
- `domain` — per-domain posterior + sample size
- `weakness_type` — per-type posterior + sample size
- `template` — per-template posterior + sample size
- `attribution` (isolated vs batched) — reported separately (stratification only)

**Pass**: Stratified report exists. No stratum with n >= 5 has ECE > 2x the
global ECE (severe local miscalibration).
**Fail**: Only global average reported, or a major slice degrades badly while
global improves.

**Minimum data**: Strata with fewer than 5 observations are reported as
`insufficient_data` and excluded from the pass/fail check.

---

## Gate 7 — Confidence is versioned as data

Every emitted calibrated score must carry:

| Field | Example |
|-------|---------|
| `calibration_version` | `"v1"` |
| `prior_spec` | `"Beta(1,1)"` |
| `fit_window` | `{"from": "2026-03-16", "to": "2026-04-01"}` |
| `bucket_key` | `"full::1::cpp::keyword_only::implement"` |
| `eval_mode` | `"full"` |
| `weakness_classifier_version` | `1` |
| `evidence_count` | `7` |
| `source` | `"posterior"` or `"prior_only"` |

**Pass**: Every calibrated score in storage and API output includes all
fields above. `source="prior_only"` whenever `evidence_count == 0`.
**Fail**: Any field missing, or hard to reconstruct after the fact, or
zero-evidence buckets emit `source="posterior"`.

---

## Gate 8 — Runtime observability exists

Read-only inspection endpoints expose:

| Endpoint | Returns |
|----------|---------|
| `GET /api/eval/confidence` | Full calibration ledger with all posteriors, evidence counts, intervals |
| `GET /api/eval/confidence?domain=X` | Per-domain detail |
| `GET /api/eval/confidence/reliability` | Reliability diagram data (bins, observed, predicted, counts) |

Each entry exposes:
- raw success rate (MLE: s/n, or `null` if n=0)
- calibrated posterior mean (alpha / (alpha + beta))
- prior parameters
- posterior parameters
- 90% credible interval (lower, upper)
- effective sample size (alpha + beta - 2)
- `insufficient_data` flag (alpha + beta < 5)
- `source` field: `"posterior"` if evidence_count > 0, `"prior_only"` if evidence_count == 0
- calibration version + full bucket key

**Pass**: All endpoints return correct data. `source="prior_only"` entries
are visually distinguishable from evidence-backed entries. Inspection alone
is sufficient to answer "why was this 0.72?"
**Fail**: Any field missing, prior-only entries indistinguishable from
evidence-backed entries, or tracing a specific score requires reading code.

---

## Gate 9 — Failure mode is acceptable

There must be a passing path where Phase 3 concludes:

**"Calibration is structurally sound but empirically unvalidated due to
insufficient closed critique patterns."**

That is a successful engineering result. It means:
- The machinery exists and is tested on synthetic data (Gates 1-4, 7-8)
- Empirical validation is deferred until real data accumulates (Gates 5-6)
- No behavior change occurred (Gate 2)
- The system is ready to validate as soon as data arrives

### Prior-only output semantics

When `evidence_count == 0` for a bucket, the system emits:
- `source = "prior_only"` (never `"posterior"`)
- `posterior_mean = 0.5` (the Beta(1,1) prior mean)
- `usable = false`
- `insufficient_data = true`

A prior-only value of 0.50 is NOT information — it is the absence of
information. The `source` and `usable` fields make this explicit so no
downstream consumer can mistake prior for evidence.

A bad calibration layer is worse than no calibration layer because it
launders uncertainty into fake precision. The system must be able to say
"I don't know yet" and have that be the correct answer.

**Pass**: Phase 3 can complete with `insufficient_data` verdict on Gates 5-6
while all other gates pass. Zero-evidence buckets always emit
`source="prior_only"` and `usable=false`. The system does not pretend to
be calibrated.
**Fail**: The system emits confident-looking numbers despite having fewer
than 20 closed attempts, or zero-evidence buckets lack `source`/`usable`
fields, or `insufficient_data` is treated as failure rather than honest
uncertainty.

---

## Implementation boundary

Phase 3 code should:
1. Compute raw evidence per 5-tuple bucket
2. Fit pure Beta posteriors (one Bernoulli trial per closed attempt, no fractional counts)
3. Store calibration artifacts (ledger JSON) with full versioning
4. Expose read-only inspection endpoints
5. Include synthetic validation suite (Gates 1-4, 7-8)
6. Include empirical validation harness (Gates 5-6) that runs when data exists
7. Mark zero-evidence buckets as `source="prior_only"` and `usable=false`
8. NOT let any consumer act on calibration output

The milestone label is:
**"Phase 3 complete — confidence estimated and validated (or honestly deferred), not policy-active."**

---

## Data requirement estimate

To clear Gates 5-6 empirically:
- Minimum 20 closed attempts in held-out set
- Minimum 3 strata with n >= 5 each for Gate 6
- At current pace (0 closed attempts), this requires real training cycles

Phase 3 should ship the machinery and synthetic validation now.
Empirical validation runs automatically when data accumulates.

---

## Design decisions (frozen)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Bucket key | 5-tuple: `(eval_mode, wcv, domain, weakness_type, template)` | Prevents cross-partition comparison |
| Attribution in posterior | **No** — stratification only | Keeps posterior as pure Bernoulli-Beta; weighted ranking is a separate tool |
| Success threshold | `delta > 0.01` | One percentage point; below is noise on 60-probe eval (~1.67%/probe) |
| Gate 5 baseline | Bucket MLE (s/n) | Simplest non-trivial estimator; `get_effective_templates()` is a separate system |
| Zero-evidence output | `source="prior_only"`, `usable=false` | 0.50 must not masquerade as information |
