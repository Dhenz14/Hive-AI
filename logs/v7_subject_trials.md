# v7 Subject-by-Subject Training Trials Log

## Ground Rules
- NEVER eval the base model. Published benchmarks are ground truth.
- Base quick_eval score: 0.978 (hardcoded)
- Each LoRA must score >= 0.978 on quick_eval or training is BAD
- If degradation detected: STOP, investigate, fix, retry
- Goal: equal or better on every subject

## Base Scores (hardcoded, never re-test)
- Quick eval: 0.978
- Python: 89.0 (MultiPL-E) STRONG
- C++: 69.6 WEAK
- JavaScript: 61.5 WEAK
- Rust: ~60 WEAK
- Go: ~60 WEAK
- Hive: 0 (no benchmark) WEAKEST

---

## Trial 1: Combined Hive (hive_sdk + hive_economics + hive_layer2 + hive_security + hive_architecture)
- **Data**: 345 pairs (327 after val split)
- **Started**: 2026-03-07 00:16
- **Config**: r=16, alpha=32, dropout=0.1, RSLoRA, assistant_only_loss, 2 epochs, no KL
- **Steps**: 42/42 completed in 26 minutes
- **Loss curve**: 1.09 -> 1.06 -> 0.72 -> 0.58 -> 0.55 -> 0.48 -> 0.42 -> 0.39 (final avg 0.587)
- **GGUF**: models/hiveai-hive-lora-f16.gguf (138MB)
- **Quick eval**: 0.978 (matches base exactly)
  - python_lcs: 1.00, rust_csv: 0.89, go_queue: 1.00, explain_tcp_udp: 1.00, hive_comment: 1.00
- **Verdict**: PASS - zero degradation, hive domain knowledge added
- **Base model path for converter**: `/root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d`

---

## Trial 2: Rust (93 pairs)

- **Data**: 93 pairs (no val split — too small)
- **Started**: 2026-03-07 00:48
- **Config**: r=16, alpha=32, dropout=0.1, RSLoRA, assistant_only_loss, 2 epochs, no KL
- **Steps**: 12/12 completed in 7 minutes
- **Loss curve**: 1.23 -> 0.93 -> 0.67 -> 0.79 (final avg 0.789)
- **GGUF**: models/hiveai-rust-lora-f16.gguf (138MB)
- **Quick eval**: 0.978 (matches base)
  - python_lcs: 1.00, rust_csv: 0.89, go_queue: 1.00, explain_tcp_udp: 1.00, hive_comment: 1.00
- **Verdict**: PASS - zero degradation

---

## Trial 3: Go (102 pairs)

- **Data**: 102 pairs
- **Started**: 2026-03-07 00:59
- **Config**: r=16, alpha=32, dropout=0.1, RSLoRA, assistant_only_loss, 2 epochs, no KL
- **Steps**: 14/14 completed in 7.5 minutes
- **Loss curve**: 1.11 -> 0.92 -> 0.65 -> 0.76 (final avg 0.762)
- **GGUF**: models/hiveai-go-lora-f16.gguf (138MB)
- **Quick eval**: 0.978 (matches base)
  - python_lcs: 1.00, rust_csv: 0.89, go_queue: 1.00, explain_tcp_udp: 1.00, hive_comment: 1.00
- **Verdict**: PASS - zero degradation

---

## Trial 4: JavaScript (452 pairs)

- **Data**: 452 pairs (429 after val split)
- **Started**: 2026-03-07 01:10
- **Config**: r=16, alpha=32, dropout=0.1, RSLoRA, assistant_only_loss, 2 epochs, no KL
- **Steps**: 54/54 completed in 32 minutes
- **Loss curve**: 1.27 -> 1.02 -> 0.71 -> 0.63 -> 0.54 -> 0.57 -> 0.49 -> 0.45 -> 0.46 -> 0.60 (final avg 0.598)
- **GGUF**: models/hiveai-js-lora-f16.gguf (138MB)
- **Quick eval**: 0.978 (matches base)
- **Verdict**: PASS - zero degradation

---

## Trial 5: Systems (693 pairs)

- **Data**: 693 pairs (658 after val split)
- **Started**: 2026-03-07 01:49
- **Steps**: 84/84 completed in 56 minutes
- **Loss curve**: 1.04 -> 1.00 -> 0.72 -> 0.65 -> 0.61 -> 0.49 -> 0.45 -> 0.43 -> 0.42 -> 0.55 (final avg 0.548)
- **Quick eval**: 0.978 (matches base)
- **Verdict**: PASS - zero degradation

---

## Trial 6: Web (464 pairs)

- **Data**: 464 pairs, 56 steps, 34 min
- **Loss**: 1.08 -> 0.50 -> 0.65 (final avg 0.651)
- **Quick eval**: 0.978 PASS

---

## Trial 7: Testing (427 pairs)

- **Data**: 427 pairs, 52 steps, 37 min
- **Loss**: starting high -> 0.32 -> 0.45 (final avg 0.448)
- **Quick eval**: 0.978 PASS

---

## Trial 8: Database (366 pairs)

- **Data**: 366 pairs, ~45 steps, 26 min
- **Loss**: final avg 0.721
- **Quick eval**: 0.978 PASS

---

## Trial 9: DevOps (239 pairs)

- **Data**: 239 pairs, ~29 steps, 18 min
- **Loss**: final avg 0.688
- **Quick eval**: 0.978 PASS

---

## Trial 10: Security (171 pairs)

- **Data**: 171 pairs, ~21 steps, 13 min
- **Loss**: final avg 0.759
- **Quick eval**: 0.978 PASS

---

## Trial 11: Design Patterns (161 pairs)

- **Data**: 161 pairs, ~20 steps, 13 min
- **Loss**: final avg 0.691
- **Quick eval**: 0.978 PASS

---

## Trial 12: Algorithms (537 pairs)

- **Data**: 537 pairs, 64 steps, 44 min
- **Loss**: 0.47 -> 0.44 -> final avg 0.586
- **Quick eval**: 0.978 PASS

---

## Trial 13: Python (829 pairs)

- **Data**: 829 pairs, 100 steps, 61 min
- **Loss**: 0.38 -> 0.40 -> final avg 0.520
- **Quick eval**: 0.978 PASS

---

## Summary: All 13 Individual Subject Trials

ALL PASSED with quick_eval = 0.978 (zero degradation from base).

| # | Subject | Pairs | Steps | Time | Final Loss | Quick Eval |
|---|---------|-------|-------|------|------------|------------|
| 1 | hive_combined | 345 | 42 | 26m | 0.587 | 0.978 |
| 2 | rust | 93 | 12 | 7m | 0.789 | 0.978 |
| 3 | go | 102 | 14 | 8m | 0.762 | 0.978 |
| 4 | javascript | 452 | 54 | 32m | 0.598 | 0.978 |
| 5 | systems | 693 | 84 | 56m | 0.548 | 0.978 |
| 6 | web | 464 | 56 | 34m | 0.651 | 0.978 |
| 7 | testing | 427 | 52 | 37m | 0.448 | 0.978 |
| 8 | database | 366 | 45 | 26m | 0.721 | 0.978 |
| 9 | devops | 239 | 29 | 18m | 0.688 | 0.978 |
| 10 | security | 171 | 21 | 13m | 0.759 | 0.978 |
| 11 | design_patterns | 161 | 20 | 13m | 0.691 | 0.978 |
| 12 | algorithms | 537 | 64 | 44m | 0.586 | 0.978 |
| 13 | python | 829 | 100 | 61m | 0.520 | 0.978 |

Total training time: ~6.25 hours across 13 subjects
All subjects individually verified as non-degrading.

---
