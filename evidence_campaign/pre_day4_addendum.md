# Pre-Day-4 Frozen Addendum

**Status**: FROZEN at commit boundary before first real training dry-run.
**Date**: 2026-03-17
**Trigger**: Day 2-3 review identified five items requiring explicit documentation
before the campaign advances to Day 4-7.

---

## 1. Admission Rule Addendum

### Previous rule (protocol v2, original)
Two sequential batch runs (all 5 anchors in Run A, all 5 in Run B).
Stable if max_delta <= 0.001 across all probes between Run A and Run B.

### Current rule (protocol v2.1)
Three consecutive per-probe runs (A, B, C for each probe individually).
Stable if at least 2 of 3 runs agree within 0.001 (modal agreement).
The modal score is used as the stabilized value.

### Failure mode that motivated the change
- `rs-ownership` oscillated between 0.740 and 0.800 on every batch run.
- Root cause: structure score boundary. The probe's response crosses a
  prose-length threshold (~50 chars of non-code text) nondeterministically.
  keyword_score is constant (5/7 = 0.714); structure_score flips between
  0.800 (prose=False) and 1.000 (prose=True).
- `js-generics` also oscillated (0.800/0.900) under batch runs due to
  KV cache interference from intervening probes.

### Why this does NOT alter downstream claim shape
- Campaign claims are paired deltas within a session, not raw scores.
- The modal rule selects the score the model produces most often, not an
  artificial middle value.
- Both the pre-score and post-score for a given probe will use the same
  modal rule, so the delta computation is self-consistent.
- The rule does not suppress genuine drift — it requires 2-of-3 agreement,
  which a truly drifting probe cannot achieve.

### Cross-session comparability
All future session admissions in this campaign MUST use the v2.1 modal rule.
No session admitted under the original batch rule may be spliced with a
session admitted under the modal rule.

### Classification
This is a **versioned operational addendum** (v2 -> v2.1), not a protocol
semantic change. The admission criteria changed; the claim shape did not.

---

## 2. Cold-Start Operational Envelope

### Requirement
llama-server MUST be freshly started before session admission.
"Freshly started" means: process launched, model loaded, health check
returns ok, NO prior inference calls from any source.

### Restart procedure (exact)
```bash
# 1. Kill any running server
pkill -9 llama-server; sleep 2

# 2. Start fresh server in tmux
tmux new-session -d -s llama \
  "/opt/hiveai/llama-cpp-build/build/bin/llama-server \
   -m /opt/hiveai/project/models/deploy/current_base.gguf \
   --port 11435 -ngl 99 --ctx-size 4096 --flash-attn auto -t 12"

# 3. Wait for health
sleep 20 && curl -s http://localhost:11435/health
# Must return {"status":"ok"}

# 4. Proceed to session_admit.py (warmup phase handles GPU priming)
```

### Post-admission invariant
No server restart may occur during an admitted session. If the server
restarts for any reason (crash, OOM, manual), the epoch is invalidated
per session_protocol.json epoch_validity rules.

### Runtime enforcement

The no-restart invariant is verified at runtime via `boot_key`, which
tracks the specific llama-server **process instance** (OS PID +
`/proc/<pid>/stat` start time). boot_key changes on any event that
creates a new serving process: process crash/restart, wrapper relaunch,
host restart. It does NOT change on tmux reattach or other terminal
operations that leave the serving process untouched.

### Scope
Results from this campaign are valid only under this cold-start regime.
They do not claim generalizability to long-running or warm-state servers.

### Rationale
Day 2-3 showed that a server with prior inference history produces
different stabilization behavior than a fresh server. The exact mechanism
is not fully characterized (CUDA scheduling state, KV cache residuals,
memory allocator fragmentation are all candidates). Rather than chase the
root cause, the campaign controls for it by requiring a known initial state.

---

## 3. Gate 3 Interpretation Rule

### What "PASS" means
No detected holdout probe content in any training pack, under the frozen
audit logic (>=86% keyword cluster match threshold, 5-word prompt skeleton
overlap check).

### What "PASS" does not mean
- Zero residual leakage risk.
- The audit is robust to arbitrary threshold perturbations.
- Semantic or topological paraphrase leakage is absent.

### Threshold sensitivity disclosure
The initial threshold (>50% keyword match) produced 28% exclusion rates.
The final threshold (>=86% keyword match = 6/7 keywords) produces <1%.
The 28% was caused by common programming keywords (e.g., "import",
"function", "class") appearing in general-purpose training pairs.
This was a **false positive problem**, not a threshold gaming problem.
The >=86% threshold correctly identifies pairs that are genuinely
near-duplicates of holdout probes.

### Sensitivity posture
The leakage audit is classified as **tool-sensitive** rather than
fully de-risked. The frozen audit logic is the law for this campaign.
If a future threshold change is needed, it constitutes a protocol
regression and must be escalated.

### Separation rule (binding vs informational)
- **Binding leakage**: no detected violations. Campaign-gating.
- **Informational residual risk**: no findings under current audit lenses.
  Residual risk remains nonzero by construction. Not campaign-gating.

This separation must be maintained in all reporting.

---

## 4. Bucket Comparability Note

### Effective pack sizes

| Bucket | Domain | Pack Size | Targeted | Historical | Stability |
|--------|--------|-----------|----------|------------|-----------|
| B1     | JS     | 400       | 240      | 120        | 40        |
| B2     | Python | 400       | 240      | 120        | 40        |
| B3     | Rust   | 191       | 33       | 118        | 40        |
| B4     | C++    | 314       | 154      | 120        | 40        |
| B5     | Rust   | 191       | 33       | 118        | 40        |

### Comparability rule
B3/B5 (Rust) are **lower-power buckets** due to materially smaller
corpus depth (191 vs 400 target). Cross-bucket comparison must account
for unequal evidence mass.

### Reporting requirement
All bucket-level reporting MUST include effective pack size.
Bucket outcomes with different pack sizes may not be compared at
face value. If cross-bucket aggregation is performed, it must
normalize by evidence mass or explicitly disclose the imbalance.

### What this does NOT mean
B3/B5 are not invalid. They are valid but lower-power. A strong
signal from a 191-pair pack is still informative. A weak or null
signal is harder to interpret than from a 400-pair pack.

---

## 5. Gate 4 Scope Note

### What Gate 4 proved
- Pack determinism (re-verified)
- Holdout exclusion (re-verified)
- Attribution isolation (domain distribution correct)
- Orchestration plumbing (attempt_id, manifests, cleanup)
- Stop-condition wiring (correct exit paths)

### What Gate 4 did NOT prove
- Checkpoint creation under real training load
- Optimizer state handling
- Disk pressure behavior during training
- Child lineage metadata correctness with real weights
- Interruption/failure recovery behavior
- Artifact sealing after a real mutation
- Post-training evaluation path (merge, quantize, serve, score)
- Trainer-side nondeterminism
- Rollback/cleanup on failed child runs

### Implication
Day 4-7 remains a **real risk-bearing phase**, not a formality.
The first full training dry-run will be the actual test of the
training lifecycle. Infrastructure failures in Day 4-7 do not
count against the campaign (per operational_gates.json failure
handling rules), but they must be resolved before fit-phase begins.

---

## Risks to watch in Day 4-7

### Highest: Training-path state contamination
Admission already showed state sensitivity. Watch for hidden
contamination crossing: baseline eval -> training -> post-train
eval -> child cleanup.

### Second: Artifact sealing drift
Real child checkpoints must have:
- parent/child lineage
- immutable manifests
- post-failure quarantine
- no accidental promotion path

### Third: Metric instability around boundary probes
rs-ownership is probably not unique. Expect more threshold-sensitive
probes once real training changes output length/shape.

### Fourth: Unequal evidence mass
Rust runs that look unusually good or bad may be noise at 191-pair
scale. Do not over-interpret.
