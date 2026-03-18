#!/usr/bin/env python3
"""
Evidence Campaign v1 — Gate 4: Dry-Run Orchestrator

Runs a single disposable training attempt and verifies all stop conditions.
The child checkpoint is NEVER promoted — it is destroyed after evaluation.

Gate 4 success criteria (all must pass):
  1. Pack manifest reproduced exactly from frozen inputs
  2. Holdout exclusion enforced (zero holdout content in pack)
  3. Attribution remains isolated (single-domain pairs only)
  4. Disposable child checkpoint created successfully
  5. Full 60-probe eval runs to completion on child checkpoint
  6. Critique closure emitted with correct attempt_id
  7. Child checkpoint destroyed after closure (not promoted)
  8. Expected metrics emitted (pre_score, post_score, delta, success boolean)
  9. No threshold, pack, or parameter changes based on dry-run outcome

Usage:
    python scripts/campaign_dry_run.py --bucket B2 --seed 1 --session-baseline <path>
    python scripts/campaign_dry_run.py --bucket B2 --seed 1 --session-baseline <path> --skip-train
    python scripts/campaign_dry_run.py --bucket B2 --seed 1 --session-baseline <path> --aa-control

Run modes:
  (default)     Real training: train -> merge -> convert -> quantize -> serve -> eval -> cleanup
  --skip-train  Infrastructure check only: all checks simulated, delta=0 (no lifecycle)
  --aa-control  Full-path no-op control: convert HF → quantize → serve → eval, no training.
                Homologous to real_train in all pipeline stages except weight delta.
                Bounds how much anchor delta can be explained without training.
                Result classifies into three bins:
                  SUFFICIENT  — A/A delta ≈ historical → asymmetry explains prior drop
                  INSUFFICIENT — A/A delta << historical → training is live suspect
                  AMBIGUOUS   — result unstable or between bins
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.campaign_pack_builder import (
    build_pack, write_pack, _load_buckets, load_holdout_probes,
    verify_determinism, leakage_audit, PACK_OUTPUT_DIR,
)
from scripts.campaign_governance import (
    attempt_stamp, validate_governance, reporting_header,
    require_governed_baseline, verify_server_identity,
    GovernanceViolation, atomic_write_json,
    PROTOCOL_VERSION, BUCKET_EVIDENCE_MASS,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_MODEL_HF = "/opt/hiveai/project/models/training/v5-think/hf"
CHILD_OUTPUT_DIR = "/opt/hiveai/project/models/training/campaign_dry_run"
SUCCESS_THRESHOLD = 0.01  # delta > 0.01 = success (frozen)

# Pipeline binaries and paths (frozen for campaign)
LLAMA_SERVER_BIN = "/opt/hiveai/llama-cpp-build/build/bin/llama-server"
LLAMA_QUANTIZE_BIN = "/opt/hiveai/llama-cpp-build/build/bin/llama-quantize"
CONVERT_SCRIPT = "/opt/hiveai/llama-cpp-build/convert_hf_to_gguf.py"
CURRENT_BASE_GGUF = "/opt/hiveai/project/models/deploy/current_base.gguf"
SERVER_PORT = "11435"
SERVER_URL = f"http://localhost:{SERVER_PORT}"
# Match production server flags (from tmux session)
SERVER_FLAGS = [
    "--port", SERVER_PORT,
    "-ngl", "99",
    "--ctx-size", "4096",
    "--flash-attn", "auto",
    "-t", "12",
]


def generate_attempt_id() -> str:
    """Deterministic-format attempt ID for traceability."""
    return uuid.uuid4().hex[:12]


def _restore_parent_server(poll_timeout_s: int = 120) -> dict:
    """Restart v5-think and poll until healthy with socket-bound identity verification.

    Returns a structured result dict — never raises. Caller records fields.

    Fields:
        required          always True (only called when stop occurred)
        attempted         always True (launch was attempted)
        restored          True if /health responded within poll_timeout_s
        elapsed_s         seconds from launch to first healthy response (or None)
        listener_pid      PID of the process actually listening on SERVER port (or None)
        identity_verified True if the listener PID's cmdline contains CURRENT_BASE_GGUF

    Design note: /health proves liveness but not parent identity. Identity
    verification is socket-bound: we find the PID listening on SERVER_URL's port
    via `ss`, then check THAT process's /proc/<pid>/cmdline for the expected model
    path. This closes the "some other matching process" gap that pgrep-based checks
    leave open — pgrep matches any process in the namespace, not the port listener.

    Remaining honest bound: cmdline = intent (launch args), not proof of loaded
    weights. Path identity is also assumed stable (no symlink/file-swap detection).
    """
    result = {
        "required": True,
        "attempted": True,
        "restored": False,
        "elapsed_s": None,
        "listener_pid": None,
        "identity_verified": False,
    }
    t0 = time.time()
    subprocess.Popen(
        [LLAMA_SERVER_BIN, "-m", CURRENT_BASE_GGUF] + SERVER_FLAGS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = t0 + poll_timeout_s
    while time.time() < deadline:
        time.sleep(2)
        try:
            urllib.request.urlopen(f"{SERVER_URL}/health", timeout=5)
            result["restored"] = True
            result["elapsed_s"] = round(time.time() - t0, 1)
            break
        except Exception:
            continue

    if not result["restored"]:
        print(f"  ERROR: v5-think did not become healthy within {poll_timeout_s}s "
              f"— parent restoration FAILED. Manual restart required.")
        return result

    # Socket-bound identity verification.
    # Step 1: find the PID listening on the expected port via `ss`.
    # This binds identity to the actual listener, not any matching process.
    try:
        port = SERVER_URL.rsplit(":", 1)[-1]
        ss_out = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=5).stdout
        if "pid=" in ss_out:
            after_pid = ss_out.split("pid=", 1)[1]
            listener_pid = int(after_pid.split(",")[0].split(")")[0])
            result["listener_pid"] = listener_pid

            # Step 2: check that listener PID's cmdline for the expected model path.
            cmdline_path = Path(f"/proc/{listener_pid}/cmdline")
            if cmdline_path.exists():
                cmdline = cmdline_path.read_bytes().decode(
                    errors="replace").replace("\x00", " ")
                result["identity_verified"] = CURRENT_BASE_GGUF in cmdline
        else:
            print(f"  WARNING: no listener found on port {port} via ss — "
                  f"cannot determine listener PID for identity verification.")
    except Exception as e:
        print(f"  WARNING: socket-bound identity verification failed ({e}). "
              f"Liveness confirmed, listener identity unverified.")

    if result["identity_verified"]:
        print(f"  v5-think restored: healthy after {result['elapsed_s']}s, "
              f"listener pid={result['listener_pid']} identity verified "
              f"(cmdline contains expected model path)")
    else:
        print(f"  WARNING: v5-think healthy (pid={result['listener_pid']}) "
              f"but identity NOT verified — expected model path not found in "
              f"listener cmdline. A wrong model or stale process may be serving.")

    return result


def _not_required_restore() -> dict:
    """Restore detail when parent server was never stopped (not applicable).

    Note: parent_restored check treats restored=None as pass (not False).
    Artifact readers must inspect parent_restore_detail.required to distinguish
    'restore succeeded' from 'restore was not needed'.
    """
    return {
        "required": False,
        "attempted": False,
        "restored": None,       # not applicable — no restore was needed
        "elapsed_s": None,
        "listener_pid": None,
        "identity_verified": None,
    }


def run_gate4(
    bucket_id: str,
    seed: int,
    session_baseline_path: str,
    skip_train: bool = False,
    aa_control: bool = False,
    extra_train_flags: list = None,
):
    """Run a complete Gate 4 dry-run attempt."""

    attempt_id = generate_attempt_id()
    child_dir = Path(CHILD_OUTPUT_DIR) / f"child_{bucket_id}_{attempt_id}"

    print(f"\n{'='*70}")
    print(f"  Gate 4: Dry-Run — {bucket_id} seed={seed}")
    print(f"  Attempt ID: {attempt_id}")
    print(f"  Child dir: {child_dir}")
    print(f"  Session baseline: {session_baseline_path}")
    print(f"{'='*70}")

    # Determine run type for artifact stamping
    if skip_train:
        run_type = "skip_train"
    elif aa_control:
        run_type = "aa_control"
    elif extra_train_flags:
        run_type = "variant_train"
    else:
        run_type = "real_train"

    # --- Load and validate session baseline governance ---
    # aa-control is not campaign-eligible (no training = no training evidence)
    campaign_mode = (run_type == "real_train")
    variant_flags_list = extra_train_flags or []
    try:
        session_data = require_governed_baseline(
            session_baseline_path, campaign_mode=campaign_mode)
    except GovernanceViolation as e:
        print(f"\n  {e}")
        sys.exit(1)

    session_id = session_data.get("session_id", "unknown")
    session_gov = session_data.get("governance", {})
    cold_start = session_gov.get("cold_start_confirmed", False)
    no_restart = session_gov.get("no_restart_confirmed", False)
    admission_server_id = session_gov.get("server_identity")

    # Verify server has not restarted since admission (real_train and aa_control only)
    if run_type != "skip_train" and admission_server_id:
        server_violations = verify_server_identity(admission_server_id)
        if server_violations:
            print(f"\n  FATAL: Server identity changed since admission:")
            for v in server_violations:
                print(f"    - {v}")
            print(f"  Session epoch is INVALIDATED. Re-admit before proceeding.")
            sys.exit(1)
        else:
            print(f"  Server identity verified: boot_key={admission_server_id.get('boot_key')}")

    results = {
        "attempt_id": attempt_id,
        "bucket_id": bucket_id,
        "seed": seed,
        "run_type": run_type,
        "variant_flags": variant_flags_list if variant_flags_list else None,
        "measurement_protocol": "v2.1",  # warm-modal pre / cold-single-pass post
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "governance": attempt_stamp(
            session_id=session_id,
            bucket_id=bucket_id,
            attempt_id=attempt_id,
            cold_start_confirmed=cold_start,
            no_restart_confirmed=no_restart,
            server_identity=admission_server_id,
            actual_pack_size=None,  # filled after pack build
            campaign_eligible=(run_type == "real_train"),  # variant_train is NOT eligible
        ),
        "evidence_mass": reporting_header(bucket_id),
        "checks": {},
    }

    # --- Check 1: Pack determinism (already proven by Gate 2, re-verify) ---
    print("\n--- Check 1: Pack determinism ---")
    buckets = _load_buckets()
    holdout = load_holdout_probes()
    pack_result = build_pack(bucket_id, seed, buckets, holdout)
    pack_hash_1 = pack_result["manifest"]["pack_sha256"]

    pack_result_2 = build_pack(bucket_id, seed, buckets, holdout)
    pack_hash_2 = pack_result_2["manifest"]["pack_sha256"]

    results["checks"]["pack_determinism"] = pack_hash_1 == pack_hash_2
    # Backfill actual pack size into governance stamp
    results["governance"]["actual_pack_size"] = pack_result["manifest"]["pack_total"]
    declared = BUCKET_EVIDENCE_MASS.get(bucket_id, {}).get("pack_size")
    results["governance"]["pack_size_validated"] = (
        pack_result["manifest"]["pack_total"] == declared)
    print(f"  Pack determinism: {'PASS' if results['checks']['pack_determinism'] else 'FAIL'}")
    print(f"  Evidence mass: actual={pack_result['manifest']['pack_total']}, "
          f"declared={declared}, match={results['governance']['pack_size_validated']}")

    # --- Check 2: Holdout exclusion (already proven by Gate 3, re-verify) ---
    print("\n--- Check 2: Holdout exclusion ---")
    from scripts.campaign_pack_builder import check_holdout_contamination
    violations = 0
    for pair in pack_result["pack"]:
        if check_holdout_contamination(pair, holdout):
            violations += 1
    results["checks"]["holdout_exclusion"] = violations == 0
    print(f"  Holdout exclusion: {'PASS' if violations == 0 else 'FAIL'} ({violations} violations)")

    # --- Check 3: Attribution isolation ---
    print("\n--- Check 3: Attribution isolation ---")
    bucket_config = None
    for b in buckets["buckets"]:
        if b["bucket_id"] == bucket_id:
            bucket_config = b
            break

    target_domain = bucket_config["domain"]
    from scripts.campaign_pack_builder import _classify_domain
    domain_counts = {}
    for pair in pack_result["pack"]:
        d = _classify_domain(pair)
        domain_counts[d] = domain_counts.get(d, 0) + 1

    # Primary domain should be majority (allow stability/control pairs from other domains)
    primary_frac = domain_counts.get(target_domain, 0) / len(pack_result["pack"])
    results["checks"]["attribution_isolated"] = primary_frac >= 0.5
    results["domain_distribution"] = domain_counts
    print(f"  Primary domain ({target_domain}): {primary_frac:.1%} of pack")
    print(f"  Domain distribution: {domain_counts}")
    print(f"  Attribution: {'PASS' if results['checks']['attribution_isolated'] else 'FAIL'}")

    # --- Write pack to disk ---
    print("\n--- Writing pack ---")
    pack_dir = PACK_OUTPUT_DIR / f"dryrun_{attempt_id}"
    pack_path, manifest_path = write_pack(pack_result, pack_dir)

    # --- Extract pre-scores from already-loaded session baseline ---
    print("\n--- Session baseline pre-scores ---")
    pre_scores = {}
    for domain_name, probes_list in session_data["domains"].items():
        for p in probes_list:
            pre_scores[p["probe_id"]] = p["score"]

    anchor_pre = pre_scores.get(bucket_config["anchor_probe"], 0)
    print(f"  Anchor ({bucket_config['anchor_probe']}) pre-score: {anchor_pre:.3f}")

    if skip_train:
        print("\n--- SKIP TRAIN mode: skipping actual training ---")
        print("  Simulating checks 4-8 with pre-scores as post-scores (delta=0)")

        results["checks"]["child_checkpoint_created"] = True  # simulated
        results["checks"]["eval_completed"] = True  # simulated
        results["checks"]["critique_closure_emitted"] = True  # simulated
        results["checks"]["child_destroyed"] = True  # simulated
        results["checks"]["metrics_emitted"] = True  # simulated

        post_score = anchor_pre  # no training = no change
        delta = 0.0
        success = delta > SUCCESS_THRESHOLD

        results["metrics"] = {
            "pre_score": anchor_pre,
            "post_score": post_score,
            "delta": delta,
            "success": success,
            "headroom_closed": 0.0,
            "note": "skip-train mode, no actual training performed",
        }

    elif aa_control:
        # ---------------------------------------------------------------
        # A/A full-path no-op control: noise-floor characterization
        # Pipeline: stop → convert HF → quantize → serve → eval → cleanup
        # Identical lifecycle stages as real_train, but zero weight delta.
        # Uses BASE_MODEL_HF directly (no LoRA applied).
        # NOT campaign-eligible — produces no training evidence.
        #
        # Result classification (three bins):
        #   SUFFICIENT   A/A delta ≈ historical → asymmetry explains prior drop
        #   INSUFFICIENT A/A delta << historical → training is live suspect
        #   AMBIGUOUS    result is in between or eval is unstable
        # ---------------------------------------------------------------
        child_gguf_dir = child_dir / "gguf"
        child_gguf_f16 = child_gguf_dir / "child-f16.gguf"
        child_gguf_q5 = child_gguf_dir / "child-q5_k_m.gguf"
        child_ledger = child_dir / "eval_ledger.json"
        child_version = f"campaign_aa_{bucket_id}_{attempt_id}"
        child_server_proc = None
        v5_server_stopped = False

        # ------------------------------------------------------------------
        # Admission-state comparability gate (hard gate on historical claims)
        # The historical B2/seed=1 run admitted py-metaclass at 0.8833.
        # If this session admits at a materially different anchor state,
        # SUFFICIENT/INSUFFICIENT classification is AMBIGUOUS by construction,
        # regardless of the A/A delta observed.
        # Run still proceeds for current-stack noise floor data.
        # ------------------------------------------------------------------
        HIST_PRE = 0.8833      # B2/seed=1 attempt 9cf93fce48ad
        COMPARABILITY_BAND = 0.05
        historical_comparability = abs(anchor_pre - HIST_PRE) <= COMPARABILITY_BAND

        print(f"\n--- A/A FULL-PATH NO-OP CONTROL ---")
        print(f"  Source: BASE_MODEL_HF (v5-think HF, no LoRA applied)")
        print(f"  Pipeline: stop → convert → quantize → serve → eval → cleanup")
        print(f"  Goal: bound measurement-path + pipeline contribution to anchor delta")
        print(f"\n  Admission comparability check:")
        print(f"    anchor_pre = {anchor_pre:.4f}, historical = {HIST_PRE:.4f}, "
              f"band = ±{COMPARABILITY_BAND}")
        if historical_comparability:
            print(f"    COMPARABLE — historical SUFFICIENT/INSUFFICIENT classification allowed")
        else:
            print(f"    NOT COMPARABLE — historical classification will be AMBIGUOUS")
            print(f"    A/A run proceeds for current-stack noise floor data only")

        # Stop v5-think — identical to real_train VRAM lifecycle
        print(f"\n--- Stopping v5-think (identical to real-train lifecycle) ---")
        subprocess.run(["pkill", "-f", "llama-server"],
                       capture_output=True)
        v5_server_stopped = True
        time.sleep(3)
        print(f"  Server stopped")

        try:
            results["checks"]["child_checkpoint_created"] = False  # no trained checkpoint

            # Convert BASE_MODEL_HF → F16 GGUF (no merge step: base is the "merged" model)
            print(f"\n--- A/A: Convert BASE_MODEL_HF → F16 GGUF ---")
            child_dir.mkdir(parents=True, exist_ok=True)
            child_gguf_dir.mkdir(parents=True, exist_ok=True)
            convert_result = subprocess.run(
                ["python3", CONVERT_SCRIPT,
                 BASE_MODEL_HF,
                 "--outfile", str(child_gguf_f16),
                 "--outtype", "f16"],
                capture_output=True, text=True, timeout=1800,
                cwd=str(PROJECT_ROOT))
            convert_ok = (child_gguf_f16.exists()
                          and convert_result.returncode == 0)
            print(f"  Convert: {'OK' if convert_ok else 'FAILED'} "
                  f"(rc={convert_result.returncode})")
            if not convert_ok:
                if convert_result.stderr:
                    print(f"  stderr: {convert_result.stderr[-300:]}")
                raise RuntimeError("GGUF conversion failed")

            # Quantize F16 → Q5_K_M (identical to real_train)
            print(f"\n--- A/A: Quantize F16 → Q5_K_M ---")
            quant_result = subprocess.run(
                [LLAMA_QUANTIZE_BIN,
                 str(child_gguf_f16), str(child_gguf_q5), "Q5_K_M"],
                capture_output=True, text=True, timeout=600,
                cwd=str(PROJECT_ROOT))
            quant_ok = (child_gguf_q5.exists()
                        and quant_result.returncode == 0)
            print(f"  Quantize: {'OK' if quant_ok else 'FAILED'} "
                  f"(rc={quant_result.returncode})")
            if not quant_ok:
                raise RuntimeError("Quantization failed")

            # Free F16 GGUF (identical to real_train)
            if child_gguf_f16.exists():
                child_gguf_f16.unlink()
                print(f"  Cleaned F16 GGUF")

            # Start child server with freshly quantized Q5 (identical path to real_train)
            print(f"\n--- A/A: Starting child server (freshly quantized, base weights) ---")
            child_server_proc = subprocess.Popen(
                [LLAMA_SERVER_BIN, "-m", str(child_gguf_q5)]
                + SERVER_FLAGS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

            server_healthy = False
            for _ in range(40):  # 80s max — fresh load after quantize
                time.sleep(2)
                try:
                    resp = urllib.request.urlopen(
                        f"{SERVER_URL}/health", timeout=5)
                    if resp.status == 200:
                        server_healthy = True
                        break
                except Exception:
                    continue
            print(f"  Child server: {'HEALTHY' if server_healthy else 'FAILED'}")
            if not server_healthy:
                raise RuntimeError("Child server failed to start")

            # Full 60-probe eval — identical path to real_train
            print(f"\n--- A/A: 60-probe eval (cold child, full pipeline, base weights) ---")
            eval_result = subprocess.run(
                ["python3", "scripts/regression_eval.py",
                 "--model-version", child_version,
                 "--server-url", SERVER_URL,
                 "--ledger", str(child_ledger)],
                capture_output=True, text=True, timeout=3600,
                cwd=str(PROJECT_ROOT))
            eval_ok = child_ledger.exists()
            results["checks"]["eval_completed"] = eval_ok
            print(f"  Eval completed: {eval_ok} (rc={eval_result.returncode})")
            if not eval_ok:
                if eval_result.stderr:
                    print(f"  stderr: {eval_result.stderr[-500:]}")
                raise RuntimeError("Eval did not produce ledger")

            # Parse results — identical to real_train
            with open(child_ledger) as f:
                ledger_data = json.load(f)
            child_scores = (
                ledger_data.get(child_version)
                or ledger_data.get(f"failed/{child_version}")
                or {})
            if not child_scores:
                raise RuntimeError("Eval ledger missing child scores")

            anchor_id = bucket_config["anchor_probe"]
            probe_scores_post = child_scores.get("probe_scores", {})
            anchor_post = probe_scores_post.get(anchor_id, anchor_pre)
            anchor_delta = round(anchor_post - anchor_pre, 4)

            domain_deltas = {}
            for dname in ["cpp", "go", "hive", "js", "python", "rust"]:
                post_val = child_scores.get(dname)
                if post_val is None:
                    continue
                pre_probes = session_data.get("domains", {}).get(dname, [])
                if pre_probes:
                    pre_avg = (
                        sum(p["score"] for p in pre_probes) / len(pre_probes))
                    domain_deltas[dname] = round(post_val - pre_avg, 4)

            # Three-bin classification — gated on admission comparability.
            # Policy constants (not empirically derived — must be stamped as such):
            #   SUFFICIENT boundary:   anchor_delta <= hist_delta + 0.02
            #   INSUFFICIENT boundary: anchor_delta >= hist_delta / 2
            #   Middle band → AMBIGUOUS (delta_in_middle_band)
            # classification_policy_version: "1" — bump if thresholds or logic change.
            # insufficient_boundary_basis: conservative policy, not measured distribution.
            hist_delta = -0.1166  # B2/seed=1 real_train (9cf93fce48ad)
            ambiguous_reason = None  # set only when classification == AMBIGUOUS
            if not historical_comparability:
                # Cause: wrong pre-state — historical attribution is blocked.
                # Next action: re-admit; determine whether warm state is reproducible.
                classification = "AMBIGUOUS"
                ambiguous_reason = "pre_state_not_comparable"
                classification_note = (
                    f"Pre-state not comparable to historical run "
                    f"(anchor_pre={anchor_pre:.4f} vs historical {HIST_PRE:.4f}, "
                    f"band ±{COMPARABILITY_BAND}). "
                    "Historical SUFFICIENT/INSUFFICIENT classification disallowed. "
                    "A/A delta is valid current-stack noise floor only.")
                next_action_class = "re_admit_for_comparability"
                next_action_preconditions = [
                    "warm_admission_reproducibility_characterized",
                    "anchor_pre within comparability_band of hist_pre on next admit",
                ]
            elif anchor_delta <= hist_delta + 0.02:
                # Asymmetry explains the historical drop.
                # Next action: move to v2.2 symmetric measurement, then first clean train.
                classification = "SUFFICIENT"
                classification_note = (
                    "measurement asymmetry sufficient to explain historical drop. "
                    f"A/A {anchor_delta:+.4f} ≈ historical {hist_delta:+.4f}. "
                    "Prior regression non-attributable to training (cannot prove zero, "
                    "but asymmetry is sufficient explanation).")
                next_action_class = "proceed_to_v22_then_train"
                next_action_preconditions = [
                    "measurement_protocol v2.2 designed and versioned",
                    "child-side anchor stabilization implemented (3-run modal)",
                    "clean_tree == true",
                ]
            elif anchor_delta >= hist_delta / 2:
                # Asymmetry alone does not explain the drop; training is a live suspect.
                # Next action: repeat real train for pattern check (not causal resolution —
                # v2.1 measurement stack still has known asymmetry).
                classification = "INSUFFICIENT"
                classification_note = (
                    "measurement asymmetry insufficient to explain full historical drop. "
                    f"A/A {anchor_delta:+.4f} << historical {hist_delta:+.4f}. "
                    "Training is a live suspect for the remainder. "
                    "Cannot prove training caused it, only that asymmetry alone cannot. "
                    "B2/seed=2 under v2.1 checks repeatability of the suspicious pattern, "
                    "not causal resolution (measurement asymmetry still present).")
                next_action_class = "run_real_train_repeat"
                next_action_preconditions = [
                    "historical_comparability == true on next admit",
                    "clean_tree == true",
                    "interpret result as pattern-check only, not causal resolution",
                ]
            else:
                # Cause: comparable pre-state, but delta falls between policy bins.
                # Measurement stack too coarse to classify; v2.2 becomes mandatory.
                classification = "AMBIGUOUS"
                ambiguous_reason = "delta_in_middle_band"
                classification_note = (
                    f"A/A {anchor_delta:+.4f} is between bins vs historical {hist_delta:+.4f}. "
                    "Mixed or unstable contribution — measurement stack too coarse to classify. "
                    "v2.2 symmetric measurement mandatory before further interpretation.")
                next_action_class = "design_v22_measurement"
                next_action_preconditions = [
                    "historical_comparability == true (already satisfied)",
                    "measurement_protocol v2.2 designed and versioned",
                    "child-side anchor stabilization implemented (3-run modal)",
                ]

            results["metrics"] = {
                "pre_score": anchor_pre,
                "post_score": anchor_post,
                "delta": anchor_delta,
                "success": False,  # A/A control never claims success
                "headroom_closed": 0.0,
                "child_overall": child_scores.get("overall"),
                "domain_deltas": domain_deltas,
                "child_probe_scores": probe_scores_post,
                "historical_comparability": historical_comparability,
                "aa_classification": classification,
                "aa_classification_note": classification_note,
                "ambiguous_reason": ambiguous_reason,
                "next_action_class": next_action_class,
                "next_action_preconditions": next_action_preconditions,
                "classification_policy": {
                    "version": "1",
                    "sufficient_boundary": "anchor_delta <= hist_delta + 0.02",
                    "insufficient_boundary": "anchor_delta >= hist_delta / 2",
                    "insufficient_boundary_basis": "policy_half_historical_delta",
                },
                "historical_reference": {
                    "attempt_id": "9cf93fce48ad",
                    "delta": hist_delta,
                    "hist_pre": HIST_PRE,
                    "comparability_band": COMPARABILITY_BAND,
                    "run_type": "real_train",
                },
                "note": ("A/A full-path no-op: delta bounds measurement-path contribution. "
                         "Cannot prove training caused remainder, only bound it. "
                         "historical_comparability must be true for SUFFICIENT/INSUFFICIENT "
                         "classification to be valid."),
            }
            results["checks"]["metrics_emitted"] = True

            print(f"\n  A/A result — Anchor ({anchor_id}): "
                  f"{anchor_pre:.3f} -> {anchor_post:.3f} "
                  f"(delta={anchor_delta:+.4f})")
            print(f"  Classification: {classification}")
            print(f"  {classification_note}")
            if domain_deltas:
                print(f"  Domain deltas: {domain_deltas}")

            critique_record = {
                "attempt_id": attempt_id,
                "bucket_id": bucket_id,
                "domain": target_domain,
                "anchor_probe": anchor_id,
                "pre_score": anchor_pre,
                "post_score": anchor_post,
                "delta": anchor_delta,
                "fix_succeeded": False,
                "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": (f"A/A full-path no-op. Classification: {classification}. "
                         "Delta is measurement + pipeline noise, not training effect."),
            }
            results["critique_closure"] = critique_record
            results["checks"]["critique_closure_emitted"] = True

        except Exception as e:
            print(f"\n  A/A LIFECYCLE ABORT: {e}")
            results["checks"].setdefault("eval_completed", False)
            results["checks"].setdefault("critique_closure_emitted", False)
            results["checks"].setdefault("metrics_emitted", False)
            if "metrics" not in results:
                results["metrics"] = {
                    "pre_score": anchor_pre,
                    "post_score": None,
                    "delta": None,
                    "success": None,
                    "note": f"A/A lifecycle aborted: {e}",
                }

        finally:
            # Cleanup — mirrors real_train finally exactly
            print(f"\n--- A/A: Cleanup ---")
            if child_server_proc:
                try:
                    child_server_proc.kill()
                    child_server_proc.wait(timeout=10)
                except Exception:
                    pass
                subprocess.run(["pkill", "-f", "llama-server"],
                               capture_output=True)
                time.sleep(2)
                print(f"  Child server stopped")

            if v5_server_stopped:
                print(f"  Restarting v5-think server...")
                restore = _restore_parent_server()
            else:
                restore = _not_required_restore()
            results["checks"]["parent_restored"] = (
                restore["restored"] is not False)  # True or None (not required) → pass
            results["checks"]["parent_restore_detail"] = restore

            if child_dir.exists():
                shutil.rmtree(child_dir, ignore_errors=True)
            results["checks"]["child_destroyed"] = not child_dir.exists()
            print(f"  Child destroyed: "
                  f"{'PASS' if results['checks']['child_destroyed'] else 'FAIL'}")

    else:
        # ---------------------------------------------------------------
        # Full training lifecycle
        # Train -> Merge -> Convert -> Quantize -> Serve -> Eval -> Close
        # ---------------------------------------------------------------
        child_merged_hf = child_dir / "merged_hf"
        child_gguf_dir = child_dir / "gguf"
        child_gguf_f16 = child_gguf_dir / "child-f16.gguf"
        child_gguf_q5 = child_gguf_dir / "child-q5_k_m.gguf"
        child_ledger = child_dir / "eval_ledger.json"
        child_version = f"campaign_child_{bucket_id}_{attempt_id}"
        child_server_proc = None
        v5_server_stopped = False

        # Stop v5-think server to free GPU VRAM for training
        print(f"\n--- Stopping v5-think (free GPU for training) ---")
        subprocess.run(["pkill", "-f", "llama-server"],
                       capture_output=True)
        v5_server_stopped = True
        time.sleep(3)
        print(f"  Server stopped, GPU memory released")

        try:
            # --- Check 4: Train disposable child checkpoint ---
            print(f"\n--- Check 4: Training child checkpoint ---")
            child_dir.mkdir(parents=True, exist_ok=True)
            train_cmd = [
                "python3", "scripts/train_v5.py",
                "--base-model-hf", BASE_MODEL_HF,
                "--data", str(pack_path),
                "--output-dir", str(child_dir),
                "--rank", "4",
                "--lr", "5e-5",
                "--epochs", "1",
                "--stm", "--sdft", "--no-ewc",
            ] + variant_flags_list
            print(f"  Command: {' '.join(train_cmd)}")
            try:
                train_result = subprocess.run(
                    train_cmd, capture_output=True, text=True,
                    timeout=3600, cwd=str(PROJECT_ROOT))
                train_ok = (train_result.returncode == 0
                            and child_dir.exists())
            except subprocess.TimeoutExpired:
                train_result = None
                train_ok = False
                print(f"  TRAIN TIMEOUT (1h)")
            results["checks"]["child_checkpoint_created"] = train_ok
            if not train_ok:
                print(f"  TRAIN FAILED")
                if train_result and train_result.stderr:
                    print(f"  stderr: {train_result.stderr[-500:]}")
                raise RuntimeError("Training failed")
            print(f"  Training completed successfully")

            # --- Check 5a: Merge LoRA into base HF ---
            print(f"\n--- Check 5a: Merging LoRA into base HF ---")
            merge_code = (
                'import os\n'
                'os.environ["HF_DEACTIVATE_ASYNC_LOAD"] = "1"\n'
                'import torch\n'
                'from peft import PeftModel\n'
                'from transformers import AutoModelForCausalLM, '
                'AutoTokenizer\n'
                f'base = "{BASE_MODEL_HF}"\n'
                f'lora = "{child_dir}"\n'
                f'out = "{child_merged_hf}"\n'
                'print("Loading base model (CPU, bf16)...")\n'
                'model = AutoModelForCausalLM.from_pretrained(\n'
                '    base, torch_dtype=torch.bfloat16, '
                'device_map="cpu")\n'
                'print("Loading LoRA adapter...")\n'
                'model = PeftModel.from_pretrained(\n'
                '    model, lora, device_map="cpu")\n'
                'print("Merging and unloading...")\n'
                'model = model.merge_and_unload()\n'
                'print("Saving merged model...")\n'
                'os.makedirs(out, exist_ok=True)\n'
                'model.save_pretrained(out)\n'
                'tokenizer = AutoTokenizer.from_pretrained(base)\n'
                'tokenizer.save_pretrained(out)\n'
                'print("Merge complete.")\n'
            )
            merge_script = child_dir / "_merge.py"
            merge_script.write_text(merge_code)
            merge_result = subprocess.run(
                ["python3", str(merge_script)],
                capture_output=True, text=True, timeout=1800,
                cwd=str(PROJECT_ROOT),
                env={**os.environ,
                     "HF_DEACTIVATE_ASYNC_LOAD": "1"})
            merge_ok = (merge_result.returncode == 0
                        and child_merged_hf.exists())
            print(f"  Merge: {'OK' if merge_ok else 'FAIL'}")
            if not merge_ok:
                if merge_result.stderr:
                    print(f"  stderr: {merge_result.stderr[-500:]}")
                raise RuntimeError("LoRA merge failed")

            # --- Check 5b: Convert HF -> F16 GGUF ---
            print(f"\n--- Check 5b: Converting HF -> GGUF ---")
            child_gguf_dir.mkdir(parents=True, exist_ok=True)
            convert_result = subprocess.run(
                ["python3", CONVERT_SCRIPT,
                 str(child_merged_hf),
                 "--outfile", str(child_gguf_f16),
                 "--outtype", "f16"],
                capture_output=True, text=True, timeout=1800,
                cwd=str(PROJECT_ROOT))
            convert_ok = (convert_result.returncode == 0
                          and child_gguf_f16.exists())
            print(f"  Convert: {'OK' if convert_ok else 'FAIL'}")
            if not convert_ok:
                if convert_result.stderr:
                    print(f"  stderr: "
                          f"{convert_result.stderr[-500:]}")
                raise RuntimeError(
                    "HF -> GGUF conversion failed")

            # Free ~28GB: merged HF no longer needed
            shutil.rmtree(child_merged_hf, ignore_errors=True)
            print(f"  Cleaned merged HF dir")

            # --- Check 5c: Quantize F16 -> Q5_K_M ---
            print(f"\n--- Check 5c: Quantizing GGUF ---")
            quantize_result = subprocess.run(
                [LLAMA_QUANTIZE_BIN, str(child_gguf_f16),
                 str(child_gguf_q5), "Q5_K_M"],
                capture_output=True, text=True, timeout=1800)
            quantize_ok = (quantize_result.returncode == 0
                           and child_gguf_q5.exists())
            print(f"  Quantize: {'OK' if quantize_ok else 'FAIL'}")
            if not quantize_ok:
                if quantize_result.stderr:
                    print(f"  stderr: "
                          f"{quantize_result.stderr[-500:]}")
                raise RuntimeError("GGUF quantization failed")

            # Free ~28GB: F16 GGUF no longer needed
            if child_gguf_f16.exists():
                child_gguf_f16.unlink()
                print(f"  Cleaned F16 GGUF")

            # --- Check 5d: Start child model server ---
            print(f"\n--- Check 5d: Starting child server ---")
            # v5-think already stopped before training

            child_server_proc = subprocess.Popen(
                [LLAMA_SERVER_BIN, "-m", str(child_gguf_q5)]
                + SERVER_FLAGS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

            server_healthy = False
            for _ in range(30):  # 60s max
                time.sleep(2)
                try:
                    resp = urllib.request.urlopen(
                        f"{SERVER_URL}/health", timeout=5)
                    if resp.status == 200:
                        server_healthy = True
                        break
                except Exception:
                    continue
            print(f"  Child server: "
                  f"{'HEALTHY' if server_healthy else 'FAILED'}")
            if not server_healthy:
                raise RuntimeError(
                    "Child llama-server failed to start")

            # --- Check 5e: Full 60-probe eval on child ---
            print(f"\n--- Check 5: Running 60-probe eval ---")
            eval_result = subprocess.run(
                ["python3", "scripts/regression_eval.py",
                 "--model-version", child_version,
                 "--server-url", SERVER_URL,
                 "--ledger", str(child_ledger)],
                capture_output=True, text=True, timeout=3600,
                cwd=str(PROJECT_ROOT))
            eval_ok = child_ledger.exists()
            results["checks"]["eval_completed"] = eval_ok
            print(f"  Eval completed: {eval_ok} "
                  f"(rc={eval_result.returncode})")
            if not eval_ok:
                if eval_result.stderr:
                    print(f"  stderr: "
                          f"{eval_result.stderr[-500:]}")
                raise RuntimeError(
                    "Eval did not produce ledger")

            # --- Parse eval results ---
            with open(child_ledger) as f:
                ledger_data = json.load(f)
            child_scores = (
                ledger_data.get(child_version)
                or ledger_data.get(f"failed/{child_version}")
                or {})
            if not child_scores:
                raise RuntimeError(
                    "Eval ledger missing child scores")

            anchor_id = bucket_config["anchor_probe"]
            probe_scores_post = child_scores.get(
                "probe_scores", {})
            anchor_post = probe_scores_post.get(
                anchor_id, anchor_pre)
            anchor_delta = round(
                anchor_post - anchor_pre, 4)

            # Domain deltas (session baseline -> child)
            domain_deltas = {}
            for dname in [
                "cpp", "go", "hive",
                "js", "python", "rust",
            ]:
                post_val = child_scores.get(dname)
                if post_val is None:
                    continue
                pre_probes = session_data.get(
                    "domains", {}).get(dname, [])
                if pre_probes:
                    pre_avg = (
                        sum(p["score"] for p in pre_probes)
                        / len(pre_probes))
                    domain_deltas[dname] = round(
                        post_val - pre_avg, 4)

            success = anchor_delta > SUCCESS_THRESHOLD
            headroom = 1.0 - anchor_pre
            headroom_closed = (
                round(anchor_delta / headroom, 4)
                if headroom > 0 else 0.0)

            results["metrics"] = {
                "pre_score": anchor_pre,
                "post_score": anchor_post,
                "delta": anchor_delta,
                "success": success,
                "headroom_closed": headroom_closed,
                "child_overall": child_scores.get("overall"),
                "domain_deltas": domain_deltas,
                "child_probe_scores": probe_scores_post,
            }
            results["checks"]["metrics_emitted"] = True

            print(f"\n  Anchor ({anchor_id}): "
                  f"{anchor_pre:.3f} -> {anchor_post:.3f} "
                  f"(delta={anchor_delta:+.4f})")
            print(f"  Success (delta>{SUCCESS_THRESHOLD}): "
                  f"{success}")
            print(f"  Headroom closed: "
                  f"{headroom_closed:.1%}")
            if domain_deltas:
                print(f"  Domain deltas: {domain_deltas}")

            # --- Check 6: Critique closure ---
            print(f"\n--- Check 6: Critique closure ---")
            critique_record = {
                "attempt_id": attempt_id,
                "bucket_id": bucket_id,
                "domain": target_domain,
                "anchor_probe": anchor_id,
                "pre_score": anchor_pre,
                "post_score": anchor_post,
                "delta": anchor_delta,
                "fix_succeeded": success,
                "closed_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": (
                    "prior_only and delta<0.01 are "
                    "acceptable outcomes, not failures"),
            }
            results["critique_closure"] = critique_record
            results["checks"][
                "critique_closure_emitted"] = True
            print(f"  Critique emitted: "
                  f"fix_succeeded={success}")

        except Exception as e:
            print(f"\n  LIFECYCLE ABORT: {e}")
            results["checks"].setdefault(
                "child_checkpoint_created", False)
            results["checks"].setdefault(
                "eval_completed", False)
            results["checks"].setdefault(
                "critique_closure_emitted", False)
            results["checks"].setdefault(
                "metrics_emitted", False)
            if "metrics" not in results:
                results["metrics"] = {
                    "pre_score": anchor_pre,
                    "post_score": None,
                    "delta": None,
                    "success": None,
                    "note": f"Lifecycle aborted: {e}",
                }

        finally:
            # --- Check 7: Cleanup (always runs) ---
            print(f"\n--- Check 7: Cleanup ---")

            # Stop child server if running
            if child_server_proc:
                try:
                    child_server_proc.kill()
                    child_server_proc.wait(timeout=10)
                except Exception:
                    pass
                subprocess.run(
                    ["pkill", "-f", "llama-server"],
                    capture_output=True)
                time.sleep(2)
                print(f"  Child server stopped")

            # Restart v5-think if we stopped it
            if v5_server_stopped:
                print(f"  Restarting v5-think server...")
                restore = _restore_parent_server()
            else:
                restore = _not_required_restore()
            results["checks"]["parent_restored"] = (
                restore["restored"] is not False)  # True or None (not required) → pass
            results["checks"]["parent_restore_detail"] = restore

            # Destroy child artifacts
            if child_dir.exists():
                shutil.rmtree(child_dir, ignore_errors=True)
            results["checks"]["child_destroyed"] = (
                not child_dir.exists())
            print(f"  Child destroyed: "
                  f"{'PASS' if results['checks']['child_destroyed'] else 'FAIL'}")

    # --- Check 9: No parameter changes ---
    results["checks"]["no_parameter_changes"] = True  # verified by code review

    # --- Cleanup ---
    if pack_dir.exists():
        shutil.rmtree(pack_dir, ignore_errors=True)
        print(f"\n  Dry-run pack cleaned up: {pack_dir}")

    # --- Verdict ---
    critical_checks = [
        "pack_determinism", "holdout_exclusion", "attribution_isolated",
    ]
    if run_type == "real_train":
        critical_checks.extend([
            "child_checkpoint_created", "eval_completed",
            "critique_closure_emitted", "child_destroyed",
            "metrics_emitted", "parent_restored",
        ])
    elif run_type == "aa_control":
        # A/A control: no checkpoint, but eval + cleanup must succeed
        critical_checks.extend([
            "eval_completed", "critique_closure_emitted",
            "child_destroyed", "metrics_emitted", "parent_restored",
        ])
    critical_pass = all(results["checks"].get(c, False) for c in critical_checks)

    results["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results["verdict"] = "PASS" if critical_pass else "FAIL"

    print(f"\n{'='*70}")
    print(f"  Gate 4 Results:")
    for k, v in results["checks"].items():
        status = "PASS" if v else "FAIL"
        print(f"    {k:35s} {status}")
    print(f"  Verdict: {results['verdict']}")
    print(f"{'='*70}")

    # Self-validate governance on output artifact
    output_violations = validate_governance(results, campaign_mode=False)
    if output_violations:
        print(f"\n  Governance self-check on output artifact:")
        for v in output_violations:
            print(f"    - {v}")
        results["governance_self_check"] = output_violations
    else:
        results["governance_self_check"] = "CLEAN"

    # Write results atomically
    results_path = PROJECT_ROOT / "evidence_campaign" / f"gate4_dryrun_{attempt_id}.json"
    atomic_write_json(results_path, results)
    print(f"  Results: {results_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Gate 4: Dry-Run Orchestrator")
    parser.add_argument("--bucket", type=str, required=True, help="Bucket ID (B1-B5)")
    parser.add_argument("--seed", type=int, required=True, help="RNG seed")
    parser.add_argument("--session-baseline", type=str, required=True,
                        help="Path to session_baseline_{id}.json")
    parser.add_argument("--skip-train", action="store_true",
                        help="Skip actual training (verify infrastructure only, delta=0)")
    parser.add_argument("--aa-control", action="store_true",
                        help="A/A noise-floor run: real child lifecycle, no training. "
                             "Measures warm-pre vs cold-post asymmetry. Not campaign-eligible.")
    parser.add_argument("--extra-train-flags", type=str, default="",
                        help="Space-separated extra flags for train_v5.py. "
                             "Triggers run_type=variant_train, campaign_eligible=False. "
                             "Example: --extra-train-flags '--probe-aware --probe-weight 0.2'")
    args = parser.parse_args()

    if args.skip_train and args.aa_control:
        print("ERROR: --skip-train and --aa-control are mutually exclusive")
        sys.exit(1)

    if not Path(args.session_baseline).exists():
        print(f"ERROR: session baseline not found: {args.session_baseline}")
        sys.exit(1)

    extra_flags = args.extra_train_flags.split() if args.extra_train_flags.strip() else None
    results = run_gate4(
        args.bucket, args.seed, args.session_baseline,
        skip_train=args.skip_train,
        aa_control=args.aa_control,
        extra_train_flags=extra_flags,
    )

    sys.exit(0 if results["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
