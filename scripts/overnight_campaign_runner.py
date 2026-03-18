#!/usr/bin/env python3
"""
Evidence Campaign v1 — Overnight Sequential Runner

Runs a queued list of campaign experiments:
  1. session_admit (creates baseline)
  2. campaign_dry_run gate4 (train → eval → restore)
  3. Gate 0 check on artifact (eligibility + dry_run_hash + props_hash)
  4. Print summary, append to run_log.jsonl

Usage:
    python3 -u scripts/overnight_campaign_runner.py [--queue FILE]

Default queue (if not specified):
  B1/seed=2  (confirm js-generics home-anchor fragility)
  B3/seed=1  (new domain: rust/debug_fix, rs-ownership)
  B5/seed=1  (new domain: rust/debug_fix, rs-errors)
  B2/probe-aware/seed=1  (sauce: --probe-aware --probe-weight 0.2)
  B2/lower-lr/seed=1     (sauce: --lr 2.5e-5)

Run from WSL project root:
  cd /opt/hiveai/project
  python3 -u scripts/overnight_campaign_runner.py 2>&1 | tee evidence_campaign/logs/overnight_$(date +%Y%m%dT%H%M%SZ).log
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = PROJECT_ROOT / "evidence_campaign"
LOGS_DIR = EVIDENCE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

RUN_LOG = LOGS_DIR / "overnight_run_log.jsonl"

# Gate 0 constants
# Both hashes are valid canonical scripts with --flash-attn auto in SERVER_FLAGS:
#   35772e8bf1d68f43 — pre-variant_flags (commits up to 6ce47aa)
#   63eee86b0e975cc6 — post-variant_flags (commit e9b0a7f, adds --extra-train-flags)
VALID_DRY_RUN_HASHES = {"35772e8bf1d68f43", "63eee86b0e975cc6"}
EXPECTED_PROPS_HASH = "c32cf0bf17b2"

# ---------------------------------------------------------------------------
# Run queue definition
# ---------------------------------------------------------------------------
DEFAULT_QUEUE = [
    {
        "label": "B1/seed=2 (confirm js-generics home-anchor fragility)",
        "bucket": "B1",
        "seed": 2,
        "extra_train_flags": None,
    },
    {
        "label": "B3/seed=1 (new domain: rust/debug_fix, anchor rs-ownership)",
        "bucket": "B3",
        "seed": 1,
        "extra_train_flags": None,
    },
    {
        "label": "B5/seed=1 (new domain: rust/debug_fix, anchor rs-errors)",
        "bucket": "B5",
        "seed": 1,
        "extra_train_flags": None,
    },
    {
        "label": "B2/probe-aware/seed=1 (sauce: --probe-aware --probe-weight 0.2)",
        "bucket": "B2",
        "seed": 1,
        "extra_train_flags": "--probe-aware --probe-weight 0.2",
    },
    {
        "label": "B2/lower-lr/seed=1 (sauce: --lr 2.5e-5)",
        "bucket": "B2",
        "seed": 1,
        "extra_train_flags": "--lr 2.5e-5",
    },
]


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[{ts()}] {msg}", flush=True)


def run_cmd(cmd, label, timeout_sec=7200):
    """Run command, stream output, return (returncode, elapsed_sec)."""
    log(f"  CMD: {' '.join(cmd)}")
    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, cwd=str(PROJECT_ROOT))
    try:
        for line in proc.stdout:
            print(line, end="", flush=True)
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        log(f"  TIMEOUT after {timeout_sec}s — killed")
    elapsed = time.time() - start
    return proc.returncode, elapsed


def run_session_admit():
    """Run session_admit.py and return the path of the baseline file created."""
    log("=== SESSION ADMIT ===")
    before = set(EVIDENCE_DIR.glob("session_baseline_*.json"))
    rc, elapsed = run_cmd(
        [sys.executable, "-u", "scripts/session_admit.py", "--skip-warmup"],
        "session_admit",
    )
    if rc != 0:
        log(f"  session_admit FAILED (rc={rc})")
        return None
    after = set(EVIDENCE_DIR.glob("session_baseline_*.json"))
    new = after - before
    if not new:
        log("  session_admit ran but no new baseline file found!")
        return None
    baseline_path = sorted(new)[-1]  # newest
    log(f"  Baseline: {baseline_path.name} ({elapsed:.0f}s)")
    return str(baseline_path)


def run_gate4(bucket, seed, baseline_path, extra_train_flags=None):
    """Run campaign_dry_run.py gate4. Returns artifact path or None."""
    log(f"=== GATE 4: {bucket}/seed={seed} ===")
    cmd = [
        sys.executable, "-u", "scripts/campaign_dry_run.py",
        "--bucket", bucket,
        "--seed", str(seed),
        "--session-baseline", baseline_path,
    ]
    if extra_train_flags:
        cmd += ["--extra-train-flags", extra_train_flags]

    before = set(EVIDENCE_DIR.glob("gate4_dryrun_*.json"))
    rc, elapsed = run_cmd(cmd, f"gate4_{bucket}_s{seed}", timeout_sec=7200)
    after = set(EVIDENCE_DIR.glob("gate4_dryrun_*.json"))
    new = after - before

    if not new:
        log(f"  No artifact written (rc={rc}, elapsed={elapsed:.0f}s)")
        return None, rc, elapsed

    artifact_path = sorted(new)[-1]
    log(f"  Artifact: {artifact_path.name} (rc={rc}, elapsed={elapsed:.0f}s)")
    return str(artifact_path), rc, elapsed


def gate0_check(artifact_path):
    """Gate 0: eligibility + dry_run_hash + props_hash. Returns dict."""
    try:
        art = json.loads(Path(artifact_path).read_text())
    except Exception as e:
        return {"pass": False, "reason": f"parse error: {e}"}

    gov = art.get("governance", {})
    eligible = gov.get("campaign_eligible", False)
    dry_run_hash = gov.get("provenance", {}).get("dry_run_hash", "")
    props_hash = gov.get("server_identity", {}).get("props_hash", "")
    run_type = art.get("run_type", "")

    # variant_train is intentionally not campaign_eligible
    if run_type == "variant_train":
        eligible_ok = True  # expected False
        eligible_note = "variant_train (expected ineligible)"
    else:
        eligible_ok = eligible
        eligible_note = f"campaign_eligible={eligible}"

    hash1_ok = dry_run_hash in VALID_DRY_RUN_HASHES
    hash2_ok = props_hash.startswith(EXPECTED_PROPS_HASH)

    # Extract key metrics: anchor pre/post/delta + domain deltas
    metrics = art.get("metrics", {})
    bucket_id = art.get("bucket_id", "")
    anchor_summary = {
        "pre_score": metrics.get("pre_score"),
        "post_score": metrics.get("post_score"),
        "delta": metrics.get("delta"),
        "domain_deltas": metrics.get("domain_deltas", {}),
        "child_overall": metrics.get("child_overall"),
    }

    verdict = art.get("verdict", "UNKNOWN")

    result = {
        "pass": hash1_ok and hash2_ok,
        "eligible_note": eligible_note,
        "dry_run_hash": dry_run_hash,
        "dry_run_hash_ok": hash1_ok,
        "props_hash": props_hash,
        "props_hash_ok": hash2_ok,
        "run_type": run_type,
        "verdict": verdict,
        "bucket_id": bucket_id,
        "metrics": anchor_summary,
    }
    if not hash1_ok:
        result["reason"] = f"dry_run_hash unknown: {dry_run_hash} not in {VALID_DRY_RUN_HASHES}"
    elif not hash2_ok:
        result["reason"] = f"props_hash mismatch: {props_hash} (expected prefix {EXPECTED_PROPS_HASH})"
    return result


def append_run_log(entry):
    with open(RUN_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    queue = DEFAULT_QUEUE
    log(f"Overnight runner starting. {len(queue)} runs queued.")
    log(f"Run log: {RUN_LOG}")

    for i, run in enumerate(queue):
        label = run["label"]
        bucket = run["bucket"]
        seed = run["seed"]
        extra = run.get("extra_train_flags")

        print("\n" + "=" * 70, flush=True)
        log(f"Run {i+1}/{len(queue)}: {label}")
        print("=" * 70, flush=True)

        run_start = time.time()

        # Step 1: session_admit
        baseline_path = run_session_admit()
        if baseline_path is None:
            log(f"  SKIPPING run — session_admit failed")
            append_run_log({
                "ts": ts(), "label": label, "status": "SKIP",
                "reason": "session_admit failed",
            })
            continue

        # Step 2: gate4
        artifact_path, rc, gate_elapsed = run_gate4(bucket, seed, baseline_path, extra)
        if artifact_path is None:
            log(f"  SKIPPING gate0 — no artifact (rc={rc})")
            append_run_log({
                "ts": ts(), "label": label, "status": "FAIL",
                "reason": f"no artifact rc={rc}", "elapsed": gate_elapsed,
            })
            continue

        # Step 3: Gate 0
        g0 = gate0_check(artifact_path)
        total_elapsed = time.time() - run_start

        print("\n--- Gate 0 Check ---", flush=True)
        log(f"  dry_run_hash: {'OK' if g0['dry_run_hash_ok'] else 'FAIL'} ({g0['dry_run_hash'][:16]})")
        log(f"  props_hash:   {'OK' if g0['props_hash_ok'] else 'FAIL'} ({g0['props_hash'][:12]})")
        log(f"  {g0['eligible_note']}")
        log(f"  run_type:     {g0['run_type']}")
        log(f"  verdict:      {g0['verdict']}")
        m = g0.get("metrics", {})
        if m.get("pre_score") is not None:
            log(f"  Anchor ({g0['bucket_id']}): "
                f"{m['pre_score']:.3f} → {m['post_score']:.3f} "
                f"(Δ={m['delta']:+.4f})  child_overall={m.get('child_overall','?')}")
            dd = m.get("domain_deltas", {})
            if dd:
                log(f"  Domain deltas: {dd}")

        gate0_status = "PASS" if g0["pass"] else "FAIL"
        log(f"  Gate 0: {gate0_status}  |  Total elapsed: {total_elapsed/60:.1f}min")

        log_entry = {
            "ts": ts(),
            "label": label,
            "bucket": bucket,
            "seed": seed,
            "extra_train_flags": extra,
            "status": gate0_status,
            "artifact": str(Path(artifact_path).name),
            "gate4_verdict": g0["verdict"],
            "gate0_pass": g0["pass"],
            "dry_run_hash_ok": g0["dry_run_hash_ok"],
            "props_hash_ok": g0["props_hash_ok"],
            "run_type": g0["run_type"],
            "metrics": g0.get("metrics", {}),
            "elapsed_min": round(total_elapsed / 60, 1),
        }
        append_run_log(log_entry)

    print("\n" + "=" * 70, flush=True)
    log("All queued runs complete.")
    print("=" * 70, flush=True)

    # Print summary
    if RUN_LOG.exists():
        log("Summary:")
        for line in RUN_LOG.read_text().splitlines():
            try:
                e = json.loads(line)
                m = e.get("metrics", {})
                delta_str = f"Δ={m.get('delta', '?'):+.4f}" if m.get("delta") is not None else ""
                print(f"  {e['label'][:50]:50s}  {e.get('status','?'):6s}  {delta_str}", flush=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
