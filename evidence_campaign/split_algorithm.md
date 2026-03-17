# Evidence Campaign v1 — Deterministic Fit/Holdout Split Algorithm

## Purpose

Assign sibling probes to fit vs holdout roles without human selection bias.
The algorithm is frozen before seeing results and produces reproducible output
from the same inputs.

## Anchor Configuration (Final)

| Bucket | Anchor | Domain | Rationale |
|--------|--------|--------|-----------|
| B1 | js-generics | JS | Single anchor |
| B2 | py-metaclass | Python | Single anchor |
| B3 | rs-ownership | Rust | Dual anchor (with B5) |
| B4 | cpp-variadic | C++ | Single anchor (cpp-const demoted) |
| B5 | rs-errors | Rust | Promoted from sibling pool — 47.5% headroom, keyword_only |

**B5 swap rationale**: cpp-const (0.940, 6% headroom) was a low-sensitivity second
C++ canary. rs-errors (0.525, 47.5% headroom, keyword_only) provides dramatically
better improvement detection. One C++ bucket (B4) is kept for breadth/regression.

## Inputs

- All probes for each campaign domain (JS=10, Python=10, Rust=10, C++=10)
- Anchor probe IDs per bucket (see table above)
- Per-probe baseline scores (from corrected scorer, same session)
- Campaign salt: SHA256-derived constant frozen in manifest

## Algorithm

```
SALT = "evidence_campaign_v1_2026-03-16"

For each campaign domain D:
  1. Enumerate all probes in domain D (from probe_library.py)
  2. Remove anchors — they are measurement targets, not fit/holdout
     - JS: remove js-generics (B1)
     - Python: remove py-metaclass (B2)
     - Rust: remove rs-ownership (B3) AND rs-errors (B5)
     - C++: remove cpp-variadic (B4)
  3. Sort remaining probes by: SHA256(SALT + probe_id), ascending hex
     This is deterministic, reproducible, and not predictable from
     alphabetical or difficulty ordering.
  4. Assign by position in sorted list:
     - First round(N * 0.6) → FIT
     - Remaining → HOLDOUT
     JS (9 siblings): 5 fit + 4 holdout
     Python (9 siblings): 5 fit + 4 holdout
     Rust (8 siblings): 5 fit + 3 holdout
     C++ (9 siblings): 5 fit + 4 holdout
  5. POST-ASSIGNMENT CHECKS (per domain):
     a. At least 2 fit probes — HARD FAIL if not
     b. At least 1 holdout probe — HARD FAIL if not
     c. Classify each holdout as improvement_sensitive (score < 0.95)
        or regression_sentinel (score >= 0.95)
     d. No holdout probe text/answer appears in any training pack
```

## Properties

- **Deterministic**: Same inputs + same salt → same output every time.
- **Reproducible**: Anyone can run the algorithm and get the identical assignment.
- **Bias-free**: SHA256 hash eliminates ordering effects from alphabetical,
  difficulty, or score rankings. No human selects which probes go where.
- **Auditable**: Salt is public. Hash values are logged. The split can be
  independently verified.

## Shared domain handling (Rust)

B3 (rs-ownership) and B5 (rs-errors) share the Rust domain. The 8 remaining
Rust probes are split ONCE. Both B3 and B5 use the same fit/holdout assignment.

This means:
- A regression on a fit probe during B3 training is also visible to B5 analysis
- Holdout probes are never in any training pack for either B3 or B5

## Holdout role classification

Each holdout probe is assigned a role based on its baseline score:

- **improvement_sensitive** (score < 0.95): Can detect both improvement and regression.
  Counts toward the primary improvement-sensitive holdout denominator.
- **regression_sentinel** (score >= 0.95): Can detect regression but has no room
  for measurable improvement. Reported separately. Does NOT count as positive
  evidence of holdout improvement.

## Bucket role taxonomy

- **improvement**: Anchor has >15% headroom AND holdout has improvement_sensitive probes.
- **mixed**: Anchor has some headroom but holdout may be regression-only.
- **regression_sentinel**: Anchor near ceiling (<=8% headroom), mostly canary.

## Option C rejection

Manual rebalancing of the split was considered and explicitly rejected.

After computing the Rust split, all 3 holdout probes were at ceiling (1.000).
Moving rs-patterns (0.840, fit) to holdout would have fixed this — but it
would constitute curator contamination. The split algorithm exists precisely
to prevent "just one reasonable exception."

The Rust ceiling holdout is a structural property of the domain distribution
(6 of 10 Rust probes at 1.000), not a hygiene failure. It is disclosed and
accounted for in the analysis rules, not "fixed" by override.

## Analysis rules

At end of campaign, results are reported in two channels:

1. **Primary improvement-sensitive holdout**: Only probes with
   holdout_role=improvement_sensitive. Eligible buckets: B1, B2, B4.
2. **Regression sentinel holdout**: All holdout probes. Includes B3/B5 ceiling
   probes. Confirms non-regression but is not positive improvement evidence.

This split protects interpretability. A ceiling holdout cannot confirm
improvement — it can only fail to regress. Mixing the two produces muddy claims.
