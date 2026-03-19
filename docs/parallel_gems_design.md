# Parallel Gems — Design Document (2026-03-18)

## Audit Summary

Deep audit of all 4 parallel gems revealed the GEMS_BLUEPRINT was stale on 2 items:

| Gem | Blueprint Said | Audit Found | Actual Work |
|-----|---------------|-------------|-------------|
| Go verifier | "~50 lines in sandbox.py" | `execute_go()` already exists (sandbox.py:766-881) | Add Go canonical harnesses to canonical_harness.py |
| Rust verifier | "~50 lines in sandbox.py" | `execute_rust()` already exists (sandbox.py:655-764) | Add Rust canonical harnesses to canonical_harness.py |
| execution_language split | "~20 lines in models.py" | DB schema already clean; conflation is in sandbox.py verification output | Remove redundant field, clean fallback chain (~15 lines) |
| Beam 5 runtime validation | "3 validations needed" | All code complete (c0ea6d5); 2/3 validations closable now | Run 2 validation tests, 1 blocked on Bridge A |

---

## GEM A: Go Canonical Harnesses

### Problem
`execute_go()` compiles and runs Go code correctly. But `canonical_harness.py` only has
Python harnesses — Go code falls back to model-authored assertions (weak oracle). This means
Go verification has lower trust than Python verification.

### Design
Add Go-native canonical harnesses to `canonical_harness.py`. These must:
1. Be standalone Go programs (package main, func main)
2. Use fmt.Println for assertion output (no testing.T — that requires _test.go files)
3. Match the same task patterns as existing Python harnesses where applicable
4. Use exit code 0/1 for pass/fail (matching existing sandbox contract)

### Harness Pattern
```go
package main

import "fmt"

// Model's solution code injected here

func main() {
    // Canonical test cases
    result := functionUnderTest(args)
    if result != expected {
        fmt.Printf("FAIL: expected %v, got %v\n", expected, result)
        os.Exit(1)
    }
    fmt.Println("PASS")
}
```

### Implementation
- Add `GO_HARNESSES` list to canonical_harness.py (separate from Python HARNESSES)
- Extend `match_harness()` to accept a `language` parameter
- Extend `run_harness()` to dispatch to Go sandbox when language="go"
- Harnesses: merge_sorted, binary_search, validate_brackets (3 initial)

### Risk
Low. Additive only. No changes to existing Python harness behavior.

---

## GEM B: Rust Canonical Harnesses

### Problem
Same as Go — `execute_rust()` exists but no Rust canonical harnesses. Rust code
falls back to weak oracle.

### Design
Same pattern as Go but in Rust:
1. Standalone programs (fn main)
2. Assert via process::exit(1) on failure
3. Use println! for output

### Harness Pattern
```rust
// Model's solution code injected here

fn main() {
    assert_eq!(function_under_test(args), expected, "test description");
    println!("PASS: all assertions passed");
}
```

### Implementation
- Add `RUST_HARNESSES` list to canonical_harness.py
- Extend `match_harness()` and `run_harness()` for Rust dispatch
- Harnesses: merge_sorted, binary_search, validate_brackets (3 initial)
- Rust has native assert_eq! macro — simpler than Go

### Risk
Low. Same additive pattern.

---

## GEM C: execution_language Cleanup

### Problem
`verify_response_code()` in sandbox.py sets both `language` and `execution_language`
on each result block. They always contain the same value. Training pair creation in
app.py has a fallback chain `b.get("execution_language") or b.get("language")` that
hides this redundancy.

### Current State (Clean)
- **Database**: Two separate columns — `contract_format` (format) and `execution_languages` (languages). Already clean.
- **Orchestrator**: Separate `language` and `response_contract` fields. Already clean.
- **Telemetry**: Separate `language_detected` and `response_contract`. Already clean.

### Current State (Conflated)
- **sandbox.py:924**: `"execution_language": lang` — redundant copy of `"language"` field
- **app.py:2355**: Fallback chain reads `execution_language` first, falls back to `language`

### Fix
1. Remove `"execution_language": lang` from sandbox.py line 924
2. Simplify app.py line 2355 to read `b.get("language")` directly (no fallback)
3. Add docstring clarifying the separation

### Risk
Minimal. No functional behavior change — the fallback was always hitting `language` anyway.

---

## GEM D: Beam 5 Runtime Validations

### Problem
Beam 5 CLI flags are implementation-complete (commit c0ea6d5) but 3 runtime validations
were never executed:

1. **use_rslora PEFT path**: `--no-unsloth --adapter-template hive` proves use_rslora
   appears in realized peft_config
2. **Bad input parse**: `--target-layers "24-25-26"` produces actionable error, not IndexError
3. **Manifest read path**: domains.json is authoritative (blocked on Bridge A)

### Validation Plan
- Validation 1: Run train_v5.py with `--no-unsloth --adapter-template hive --dry-run`
  (if dry-run exists) or inspect peft_config after model creation
- Validation 2: Run `python scripts/train_v5.py --target-layers "24-25-26"` and verify
  ValueError with message (quick, no GPU needed)
- Validation 3: DEFERRED — requires Bridge A to implement manifest read

### Risk
None. Read-only validation of existing code.

---

## Governance Clarification

Per user directive: governance in HiveAI/HivePoA has a precise separation of concerns:

- **Anti-cheating measures** target untrusted participants (marketplace miners, external
  submitters) via HivePoA's Web of Trust
- **Trusted validators** are trusted by design — do NOT build controls to police them
- These are separate concerns and must never be conflated in documentation

All references in GEMS_BLUEPRINT.md and CLAUDE.md that use "governance" must be reviewed
for clarity on which layer is meant.

---

## Execution Order

1. execution_language cleanup (smallest, unblocks nothing but reduces tech debt)
2. Go + Rust canonical harnesses (parallel, both additive)
3. Beam 5 validation 2 (quick, no GPU)
4. Beam 5 validation 1 (needs model load, defer if GPU busy)
5. Governance language fixes in docs
6. Update GEMS_BLUEPRINT with audit findings
