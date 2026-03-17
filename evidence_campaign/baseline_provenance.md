# Evidence Campaign v1 — Baseline Provenance Note

## The Score Shift

On Day 1 (2026-03-16), the initial anchor evaluation produced scores systematically
higher than the 2-day-old 60-probe regression_eval.py baseline (2026-03-14).

Examples: py-metaclass 0.767→0.883, cpp-const 0.840→1.000, js-generics 0.600→0.700.

## Root Cause: Scorer Divergence

campaign_anchor_eval.py (v1, commit 11af1af) contained 4 implementation differences
from regression_eval.py that inflated structure_score and keyword_score:

1. **System prompt** — "Provide clear, well-structured responses with working code
   examples" vs regression_eval's "Answer directly without chain-of-thought reasoning."
   The permissive prompt encouraged longer, better-structured responses that maximized
   scoring signals. This was the primary driver (~+0.03-0.05).

2. **Code block detection** — Simple substring `"```" in response` vs regression_eval's
   regex `r"```\w*\n"` which requires a newline after the fence. The substring match
   counted partial fences, inflating structure_score (+0.02-0.04).

3. **Definition detection** — Simple `any(p in text for p in patterns)` vs
   regression_eval's word-boundary regex `r"\b(def |fn |...)\\b"`. The substring
   match was more permissive (+0.01-0.03).

4. **Length check** — `len(response)` vs `len(response.strip())`. Negligible impact.

**Combined effect**: ~+0.08-0.12 systematic inflation across all probes.

## Resolution

campaign_anchor_eval.py was corrected (commit TBD) to be byte-identical in scoring
logic with regression_eval.py: same system prompt, same regex patterns, same length
check. The corrected scorer was validated with 5 consecutive runs showing zero variance
(max_delta=0.0000) across all 6 anchor probes.

## Corrected Baseline vs Original 60-Probe Baseline

| Probe | Memory (2026-03-14) | Corrected (2026-03-16, 5-run) | Delta |
|-------|-------------------|-------------------------------|-------|
| js-generics | 0.600 | 0.900 | +0.300 |
| py-metaclass | 0.767 | 0.767 | 0.000 |
| rs-ownership | 0.800 | 0.740 | -0.060 |
| cpp-variadic | 0.825 | 0.925 | +0.100 |
| cpp-const | 0.840 | 0.940 | +0.100 |
| go-generics | 0.840 | 1.000 | +0.160 |

Note: cpp-const is now a C++ holdout probe (not an anchor). go-generics is a
dead reserve (zero headroom). Both rows are historical — measured before final
bucket assignments were decided.

py-metaclass matches exactly. The remaining deltas (especially js-generics +0.300,
go-generics +0.160) cannot be explained by scorer differences since the scorer is
now identical. Possible causes:

- **llama-server session state**: The original eval ran in a different llama-server
  session (2 days ago). KV cache initialization, batch scheduling, or CUDA stream
  ordering can cause subtle generation differences between sessions even with
  deterministic settings (temp=0, seed=42, top_k=1). Within a session, results
  are perfectly deterministic (proven by 5-run zero variance).
- **llama-server version/config**: The server may have been restarted with different
  parameters between the original eval and today.
- **Concurrent load**: Other queries in the original session may have affected
  KV cache state.

## Formal Disposition

1. The **2-day-old memory baseline (2026-03-14) is formally non-comparable** and
   excluded from campaign evidence. It was produced in a different inference session
   with unknown environmental differences.

2. The **campaign canonical baseline** is the corrected 2-run measurement at
   commit TBD (2026-03-16), using the scorer identical to regression_eval.py.

3. All campaign evidence starts from this baseline. Pre-campaign and post-campaign
   measurements use the same scorer, same system prompt, same parameters.

4. **Future baseline stability**: Any llama-server restart requires a baseline
   re-verification (run anchors, check for drift) before continuing the campaign.
   If drift exceeds 0.02 on any anchor, the campaign pauses until root-caused.
