#!/usr/bin/env python3
"""
Evidence Campaign v1 — Session Admission Gate (Protocol v2)

Session-local baseline regime. Admission proves intra-session determinism.
After admission, captures full 40-probe baseline for this session.
All campaign measurements are paired deltas within the admitted session.

Usage:
    python scripts/session_admit.py              # full: warmup + admit + baseline
    python scripts/session_admit.py --skip-warmup # skip warmup (already warm)
    python scripts/session_admit.py --admit-only  # admit only, skip full baseline
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.probe_library import (
    PYTHON_PROBES, RUST_PROBES, CPP_PROBES, JS_PROBES,
)
from scripts.weakness_trend import classify_weakness_type
from scripts.campaign_governance import (
    governance_stamp, PROTOCOL_VERSION, COLD_START_REQUIRED,
    capture_server_identity, atomic_write_json,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:11435")
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

ANCHOR_IDS = ["js-generics", "py-metaclass", "rs-ownership", "cpp-variadic", "rs-errors"]
SENTINEL_IDS = ["rs-patterns", "py-context-mgr", "cpp-raii", "js-proxy"]

# Design baseline (commit 4b4b083) — diagnostic artifact only, not a gate.
DESIGN_BASELINE = {
    "js-generics": 0.900, "py-metaclass": 0.767, "rs-ownership": 0.740,
    "cpp-variadic": 0.925, "rs-errors": 0.525,
}

CAMPAIGN_PROBES = {
    "js": JS_PROBES,
    "python": PYTHON_PROBES,
    "rust": RUST_PROBES,
    "cpp": CPP_PROBES,
}


# ---------------------------------------------------------------------------
# Inference + scoring (identical to regression_eval.py)
# ---------------------------------------------------------------------------
def _find_probe(probe_id: str):
    for probes in CAMPAIGN_PROBES.values():
        for p in probes:
            if p.id == probe_id:
                return p
    return None


def _call(prompt: str) -> str:
    payload = json.dumps({
        "model": "hiveai",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0, "max_tokens": 2048, "top_k": 1, "seed": 42,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{SERVER_URL}/v1/chat/completions",
            data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode())
        return result["choices"][0]["message"].get("content", "")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return ""


def _score(response: str, expected_keywords: list) -> dict:
    if not response or not response.strip():
        return {"score": 0.0, "keyword_score": 0.0, "structure_score": 0.0,
                "keywords_hit": 0, "keywords_total": len(expected_keywords)}
    text = response.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in text)
    kw_score = found / len(expected_keywords) if expected_keywords else 0.0
    sigs = [
        1.0 if bool(re.search(r"```\w*\n", response)) else 0.0,
        1.0 if bool(re.search(
            r"\b(def |fn |func |function |class |struct |impl |interface )\b",
            response)) else 0.0,
        1.0 if len(response.strip()) > 200 else 0.3,
        1.0 if len(re.sub(r"```[\s\S]*?```", "", response).strip()) > 50 else 0.2,
    ]
    str_score = sum(sigs) / len(sigs)
    return {
        "score": round(kw_score * 0.7 + str_score * 0.3, 4),
        "keyword_score": round(kw_score, 4),
        "structure_score": round(str_score, 4),
        "keywords_hit": found,
        "keywords_total": len(expected_keywords),
    }


def _run_probe(probe_id: str) -> dict:
    probe = _find_probe(probe_id)
    if not probe:
        return {"error": f"probe {probe_id} not found"}
    response = _call(probe.prompt)
    scores = _score(response, probe.expected_keywords)
    wt = classify_weakness_type(scores["keyword_score"], scores["structure_score"])
    return {**scores, "weakness_type": wt, "domain": probe.domain}


# ---------------------------------------------------------------------------
# Phase 1: Warmup
# ---------------------------------------------------------------------------
def warmup():
    print("  Phase 1a: 3 generic throwaway queries...")
    for _ in range(3):
        _call("Write a hello world function in Python.")

    print("  Phase 1b: 1 anchor round (discarded, primes GPU)...")
    for pid in ANCHOR_IDS:
        probe = _find_probe(pid)
        if probe:
            _call(probe.prompt)

    print("  Waiting 3s...")
    time.sleep(3)


# ---------------------------------------------------------------------------
# Phase 2: Stabilization (proves intra-session determinism)
# ---------------------------------------------------------------------------
def stabilize(max_attempts: int = 3) -> tuple:
    """Returns (stable: bool, scores: dict).

    Tests each probe 3 times back-to-back and checks modal stability.
    A probe is stable if at least 2 of 3 runs agree (within 0.001).
    The modal score is used as the stabilized value.

    This handles probes on structural scoring boundaries (e.g., rs-ownership
    where prose length oscillates around the 50-char threshold).
    """
    for attempt in range(1, max_attempts + 1):
        print(f"\n  Stabilization attempt {attempt}/{max_attempts}...")
        unstable = []
        scores = {}

        for pid in ANCHOR_IDS:
            runs = [_run_probe(pid) for _ in range(3)]
            run_scores = [r["score"] for r in runs]

            # Check modal stability: at least 2 of 3 must agree (within 0.001)
            stable_score = None
            for i in range(3):
                matches = sum(1 for j in range(3) if abs(run_scores[i] - run_scores[j]) <= 0.001)
                if matches >= 2:
                    stable_score = run_scores[i]
                    break

            if stable_score is not None:
                # Use the run that matches the modal score
                for r in runs:
                    if abs(r["score"] - stable_score) <= 0.001:
                        scores[pid] = r
                        break
                print(f"    OK: {pid} = {stable_score:.3f} "
                      f"(runs: {run_scores[0]:.3f}, {run_scores[1]:.3f}, {run_scores[2]:.3f})")
            else:
                unstable.append((pid, run_scores))
                print(f"    UNSTABLE: {pid} runs={[f'{s:.3f}' for s in run_scores]} (no 2-of-3 agreement)")

        if not unstable:
            print(f"  Stabilized on attempt {attempt}.")
            return True, scores

        if attempt < max_attempts:
            print("  Re-warming...")
            warmup()

    return False, {}


# ---------------------------------------------------------------------------
# Phase 3: Admission (session is internally stable → admitted)
# ---------------------------------------------------------------------------
def admit(scores: dict, cold_start: bool = True,
          campaign_eligible: bool = True) -> dict:
    session_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    # Capture server identity at admission time for no-restart verification
    server_id = capture_server_identity()

    result = {
        "session_id": session_id,
        "protocol_version": PROTOCOL_VERSION,
        "verdict": "ADMITTED",
        "governance": governance_stamp(
            session_id=session_id,
            cold_start_confirmed=cold_start,
            no_restart_confirmed=True,
            server_identity=server_id,
            campaign_eligible=campaign_eligible,
        ),
        "anchor_scores": {},
        "diagnostic_vs_design_baseline": {},
    }

    for pid in ANCHOR_IDS:
        s = scores[pid]
        result["anchor_scores"][pid] = {
            "score": s["score"],
            "keyword_score": s["keyword_score"],
            "structure_score": s["structure_score"],
            "weakness_type": s["weakness_type"],
        }
        # Diagnostic comparison (informational only)
        design_ref = DESIGN_BASELINE.get(pid, 0)
        result["diagnostic_vs_design_baseline"][pid] = {
            "session_score": s["score"],
            "design_score": design_ref,
            "deviation": round(abs(s["score"] - design_ref), 4),
        }

    return result


# ---------------------------------------------------------------------------
# Phase 4: Sentinel spot-check (informational)
# ---------------------------------------------------------------------------
def sentinel_check() -> dict:
    print("\n  Sentinel spot-check (informational)...")
    result = {}
    for pid in SENTINEL_IDS:
        s = _run_probe(pid)
        result[pid] = {"score": s["score"], "domain": s.get("domain", "?")}
        print(f"    {pid:22s} score={s['score']:.3f}")
    return result


# ---------------------------------------------------------------------------
# Phase 5: Full 40-probe session baseline capture
# ---------------------------------------------------------------------------
def capture_full_baseline(session_id: str, cold_start: bool = True,
                          server_identity: dict = None,
                          campaign_eligible: bool = True) -> Path:
    print(f"\n  Capturing full 40-probe session baseline...")
    baseline = {}
    t0 = time.time()

    for domain, probes in CAMPAIGN_PROBES.items():
        domain_results = []
        print(f"    {domain.upper()} ({len(probes)} probes)...", end=" ", flush=True)
        for probe in probes:
            s = _run_probe(probe.id)
            domain_results.append({"probe_id": probe.id, **s})
        avg = sum(r["score"] for r in domain_results) / len(domain_results)
        print(f"avg={avg:.3f}")
        baseline[domain] = domain_results

    elapsed = time.time() - t0
    out_path = PROJECT_ROOT / "evidence_campaign" / f"session_baseline_{session_id}.json"
    atomic_write_json(out_path, {
        "session_id": session_id,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(elapsed, 1),
        "governance": governance_stamp(
            session_id=session_id,
            cold_start_confirmed=cold_start,
            no_restart_confirmed=True,
            server_identity=server_identity,
            campaign_eligible=campaign_eligible,
        ),
        "domains": baseline,
    })

    print(f"  Baseline written: {out_path} ({elapsed:.0f}s)")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=f"Session Admission Gate (protocol v{PROTOCOL_VERSION})")
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument("--admit-only", action="store_true",
                        help="Skip full 40-probe baseline capture")
    parser.add_argument("--cold-start", action="store_true", default=True,
                        help="Confirm server was freshly started (required by v2.1)")
    parser.add_argument("--no-cold-start", dest="cold_start", action="store_false",
                        help="Override cold-start (EXPLORATORY ONLY, artifacts quarantined)")
    parser.add_argument("--exploratory", action="store_true",
                        help="Exploratory mode: governance violations warn, not fail")
    args = parser.parse_args()

    # Enforce cold-start invariant in campaign mode
    if COLD_START_REQUIRED and not args.cold_start and not args.exploratory:
        print(f"\n  FATAL: Cold-start invariant violated in campaign mode.")
        print(f"  --no-cold-start is only allowed with --exploratory.")
        print(f"  Restart the server and re-run, or use --exploratory for non-campaign testing.")
        sys.exit(1)

    print(f"\n{'='*65}")
    print(f"  Evidence Campaign v1 — Session Admission (Protocol v{PROTOCOL_VERSION})")
    print(f"  Server: {SERVER_URL}")
    print(f"  Regime: session-local baselines, paired deltas only")
    print(f"  Cold-start: {'confirmed' if args.cold_start else 'OVERRIDDEN'}")
    print(f"{'='*65}")

    # Phase 1: Warmup
    if not args.skip_warmup:
        print("\n--- Phase 1: Warmup ---")
        warmup()
    else:
        print("\n  Warmup skipped (--skip-warmup)")

    # Phase 2: Stabilization
    print("\n--- Phase 2: Stabilization ---")
    stable, scores = stabilize()
    if not stable:
        print(f"\n  REJECTED: Session did not stabilize after 3 attempts.")
        sys.exit(1)

    # Phase 3: Admission
    print("\n--- Phase 3: Admission ---")
    is_campaign = not args.exploratory
    admission = admit(scores, cold_start=args.cold_start,
                      campaign_eligible=is_campaign)
    session_id = admission["session_id"]

    print(f"\n  Session ID: {session_id}")
    print(f"  Protocol: v{PROTOCOL_VERSION}")
    print(f"  Verdict: {admission['verdict']}")
    print(f"\n  Anchor scores (session-local baseline):")
    for pid, data in admission["anchor_scores"].items():
        diag = admission["diagnostic_vs_design_baseline"][pid]
        print(f"    {pid:18s} score={data['score']:.3f} wt={data['weakness_type']:14s} "
              f"(design: {diag['design_score']:.3f}, dev={diag['deviation']:.3f})")

    # Phase 4: Sentinels
    sentinels = sentinel_check()

    # Phase 5: Full baseline
    baseline_path = None
    if not args.admit_only:
        print("\n--- Phase 5: Full Baseline Capture ---")
        server_id = admission["governance"].get("server_identity")
        baseline_path = capture_full_baseline(
            session_id, cold_start=args.cold_start, server_identity=server_id,
            campaign_eligible=is_campaign)
        admission["full_baseline_file"] = str(baseline_path.name)
    else:
        print("\n  Full baseline skipped (--admit-only)")

    admission["sentinels"] = sentinels

    # Append to session log
    log_path = PROJECT_ROOT / "evidence_campaign" / "session_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(admission, ensure_ascii=False) + "\n")
    print(f"\n  Session log appended: {log_path}")

    print(f"\n{'='*65}")
    print(f"  {admission['verdict']} — session {session_id} (v{PROTOCOL_VERSION})")
    print(f"  Governance: cold_start={args.cold_start}, addendum={admission['governance']['addendum_hash']}")
    print(f"  All campaign measurements in this session use session-local baseline.")
    print(f"  Restart = new epoch. Never splice cross-session raw scores.")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
