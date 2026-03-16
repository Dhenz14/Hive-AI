# Evidence Campaign v1 — Deterministic Fit/Holdout Split Algorithm

## Purpose

Assign sibling probes to fit vs holdout roles without human selection bias.
The algorithm is frozen before seeing results and produces reproducible output
from the same inputs.

## Inputs

- All probes for each campaign domain (JS=10, Python=10, Rust=10, C++=10)
- Anchor probe IDs per bucket (known a priori, not selected by this algorithm)
- Per-probe baseline scores (from corrected scorer, same session)
- Campaign salt: SHA256-derived constant frozen in manifest

## Algorithm

```
SALT = "evidence_campaign_v1_2026-03-16"

For each campaign domain D:
  1. Enumerate all probes in domain D (from probe_library.py)
  2. Remove anchors — they are measurement targets, not fit/holdout
     - JS: remove js-generics (B1 anchor)
     - Python: remove py-metaclass (B2 anchor)
     - Rust: remove rs-ownership (B3 anchor)
     - C++: remove cpp-variadic (B4 anchor) AND cpp-const (B5 anchor)
  3. Sort remaining probes by: SHA256(SALT + probe_id), ascending hex
     This is deterministic, reproducible, and not predictable from
     alphabetical or difficulty ordering.
  4. Assign by position in sorted list:
     - Positions 0,1,2,3,4 → FIT (first 60%)
     - Remaining positions → HOLDOUT
     For C++ (8 siblings): 5 fit + 3 holdout
     For others (9 siblings): 5 fit + 4 holdout
  5. POST-ASSIGNMENT CHECKS (per bucket):
     a. At least 2 fit probes — HARD FAIL if not
     b. At least 1 holdout probe — HARD FAIL if not
     c. At least 1 fit or holdout probe with score < 0.95 — WARNING if not
     d. No holdout probe text/answer appears in any training pack — verified at pack time
```

## Properties

- **Deterministic**: Same inputs + same salt → same output every time.
- **Reproducible**: Anyone can run the algorithm and get the identical assignment.
- **Bias-free**: SHA256 hash eliminates ordering effects from alphabetical,
  difficulty, or score rankings. No human selects which probes go where.
- **Auditable**: Salt is public. Hash values are logged. The split can be
  independently verified.

## Shared domain handling (C++)

B4 (cpp-variadic) and B5 (cpp-const) share the C++ domain. The 8 remaining
C++ probes are split ONCE. Both B4 and B5 use the same fit/holdout assignment.

When training for B4: measure B4 anchor + fit probes + holdout probes (separately)
When training for B5: measure B5 anchor + same fit probes + same holdout probes

This means:
- A regression on a fit probe during B4 training is also visible to B5 analysis
- Holdout probes are never in any training pack for either B4 or B5

## Headroom sufficiency rule

A bucket is "low headroom / low sensitivity" if:
- The anchor score >= 0.95 (can't measurably improve)
- AND all holdout probes score >= 0.95

Such a bucket is flagged but not removed. Its closures are valid Bernoulli trials
but may have reduced statistical power to detect improvement.

## Output format

```json
{
  "split_salt": "evidence_campaign_v1_2026-03-16",
  "split_algorithm_version": 1,
  "domains": {
    "js": {
      "anchor": ["js-generics"],
      "fit": ["probe-a", "probe-b", ...],
      "holdout": ["probe-x", "probe-y", ...],
      "headroom_flag": false
    },
    ...
  }
}
```
