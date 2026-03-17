#!/usr/bin/env python3
"""
Evidence Campaign v1 — Session Admission Gate

Implements session_protocol.json: warmup, stabilization check, admission
against reference baseline, non-anchor sentinel spot-check.

Usage:
    python scripts/session_admit.py              # full admission sequence
    python scripts/session_admit.py --skip-warmup # skip warmup (already warm)
"""
import argparse
import json
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

# ---------------------------------------------------------------------------
# Reference baseline (from design session, commit 4b4b083)
# ---------------------------------------------------------------------------
REFERENCE = {
    "js-generics":  {"score": 0.900, "weakness_type": "none"},
    "py-metaclass": {"score": 0.767, "weakness_type": "keyword_only"},
    "rs-ownership": {"score": 0.740, "weakness_type": "none"},
    "cpp-variadic": {"score": 0.925, "weakness_type": "none"},
    "rs-errors":    {"score": 0.525, "weakness_type": "keyword_only"},
}

SENTINEL_PROBES = ["rs-patterns", "py-context-mgr", "cpp-raii", "js-proxy"]

SENTINEL_REFERENCE = {
    "rs-patterns":  0.840,
    "py-context-mgr": 0.900,
    "cpp-raii": 0.900,
    "js-proxy": 0.900,
}

SERVER_URL = "http://localhost:11435"
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

# Thresholds
HARD_LABEL_MATCH = True        # weakness_type must match
HARD_MEAN_DEV = 0.05           # mean abs deviation across anchors
HARD_MAX_DEV = 0.15            # max single-anchor deviation
SOFT_SINGLE_DEV = 0.03         # warning threshold per anchor
SOFT_MEAN_DEV = 0.02           # warning threshold for mean
SENTINEL_WARN_DEV = 0.10       # sentinel warning threshold

from scripts.weakness_trend import classify_weakness_type


def _find_probe(probe_id: str):
    all_probes = PYTHON_PROBES + RUST_PROBES + CPP_PROBES + JS_PROBES
    for p in all_probes:
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
        req = urllib.request.Request(f"{SERVER_URL}/v1/chat/completions",
                                     data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode())
        return result["choices"][0]["message"].get("content", "")
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return ""


def _score(response: str, expected_keywords: list) -> dict:
    """Score — identical to regression_eval.py."""
    if not response or not response.strip():
        return {"score": 0.0, "keyword_score": 0.0, "structure_score": 0.0}
    text = response.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in text)
    kw_score = found / len(expected_keywords) if expected_keywords else 0.0

    sigs = []
    sigs.append(1.0 if bool(re.search(r"```\w*\n", response)) else 0.0)
    sigs.append(1.0 if bool(re.search(
        r"\b(def |fn |func |function |class |struct |impl |interface )\b", response)) else 0.0)
    sigs.append(1.0 if len(response.strip()) > 200 else 0.3)
    prose = re.sub(r"```[\s\S]*?```", "", response).strip()
    sigs.append(1.0 if len(prose) > 50 else 0.2)
    str_score = sum(sigs) / len(sigs)

    return {
        "score": round(kw_score * 0.7 + str_score * 0.3, 4),
        "keyword_score": round(kw_score, 4),
        "structure_score": round(str_score, 4),
    }


def run_probes(probe_ids: list) -> dict:
    results = {}
    for pid in probe_ids:
        probe = _find_probe(pid)
        if not probe:
            print(f"  WARNING: probe {pid} not found")
            continue
        response = _call(probe.prompt)
        scores = _score(response, probe.expected_keywords)
        wt = classify_weakness_type(scores["keyword_score"], scores["structure_score"])
        results[pid] = {**scores, "weakness_type": wt}
    return results


def warmup():
    """Warmup: 3 generic queries + 1 full anchor round (discarded).

    The GPU/KV cache needs to be primed with actual probe-like content,
    not just generic queries. Without probe-priming, the first anchor
    call can produce different output than subsequent calls.
    """
    print("  Warmup phase 1: 3 generic throwaway queries...")
    for i in range(3):
        _call("Write a hello world function in Python.")

    print("  Warmup phase 2: 1 throwaway anchor round (primes GPU for probe patterns)...")
    anchor_ids = list(REFERENCE.keys())
    for pid in anchor_ids:
        probe = _find_probe(pid)
        if probe:
            _call(probe.prompt)  # Result discarded
    print("  Warmup done. Waiting 3s...")
    time.sleep(3)


def stabilization_check() -> bool:
    """Run anchors twice, check for intra-session stability."""
    anchor_ids = list(REFERENCE.keys())
    print("  Stabilization: run 1...")
    run1 = run_probes(anchor_ids)
    print("  Stabilization: run 2...")
    run2 = run_probes(anchor_ids)

    stable = True
    for pid in anchor_ids:
        s1 = run1[pid]["score"]
        s2 = run2[pid]["score"]
        delta = abs(s1 - s2)
        if delta > 0.001:
            print(f"  UNSTABLE: {pid} run1={s1:.3f} run2={s2:.3f} delta={delta:.3f}")
            stable = False
        else:
            print(f"  OK: {pid} = {s2:.3f}")

    return stable, run2  # Return the stable scores


def admission_check(scores: dict) -> dict:
    """Check scores against reference baseline."""
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "anchor_scores": {},
        "deviations": {},
        "warnings": [],
        "hard_fails": [],
        "verdict": "pending",
    }

    deviations = []
    for pid, ref in REFERENCE.items():
        measured = scores.get(pid, {})
        ms = measured.get("score", 0)
        mw = measured.get("weakness_type", "unknown")
        dev = abs(ms - ref["score"])
        deviations.append(dev)

        result["anchor_scores"][pid] = {"score": ms, "weakness_type": mw}
        result["deviations"][pid] = round(dev, 4)

        # Hard fail: weakness label mismatch
        if mw != ref["weakness_type"]:
            result["hard_fails"].append(
                f"{pid}: weakness_type {mw} != reference {ref['weakness_type']}")

        # Hard fail: individual deviation > 0.15
        if dev > HARD_MAX_DEV:
            result["hard_fails"].append(
                f"{pid}: deviation {dev:.3f} > {HARD_MAX_DEV}")

        # Soft warn: individual deviation > 0.03
        if dev > SOFT_SINGLE_DEV:
            result["warnings"].append(
                f"{pid}: deviation {dev:.3f} > {SOFT_SINGLE_DEV}")

    mean_dev = sum(deviations) / len(deviations) if deviations else 0
    max_dev = max(deviations) if deviations else 0
    result["mean_absolute_deviation"] = round(mean_dev, 4)
    result["max_deviation"] = round(max_dev, 4)

    # Hard fail: mean deviation > 0.05
    if mean_dev > HARD_MEAN_DEV:
        result["hard_fails"].append(
            f"mean deviation {mean_dev:.3f} > {HARD_MEAN_DEV}")

    # Soft warn: mean deviation > 0.02
    if mean_dev > SOFT_MEAN_DEV:
        result["warnings"].append(
            f"mean deviation {mean_dev:.3f} > {SOFT_MEAN_DEV}")

    if result["hard_fails"]:
        result["verdict"] = "REJECTED"
    elif result["warnings"]:
        result["verdict"] = "ADMITTED_WITH_WARNINGS"
    else:
        result["verdict"] = "ADMITTED"

    return result


def sentinel_check() -> dict:
    """Spot-check non-anchor sentinels."""
    print("\n  Sentinel spot-check...")
    scores = run_probes(SENTINEL_PROBES)
    result = {"sentinels": {}, "warnings": []}

    for pid in SENTINEL_PROBES:
        ms = scores.get(pid, {}).get("score", 0)
        ref = SENTINEL_REFERENCE.get(pid, 0)
        dev = abs(ms - ref)
        result["sentinels"][pid] = {"score": ms, "reference": ref, "deviation": round(dev, 4)}

        if dev > SENTINEL_WARN_DEV:
            result["warnings"].append(f"{pid}: deviation {dev:.3f} > {SENTINEL_WARN_DEV}")

        print(f"    {pid:22s} score={ms:.3f} ref={ref:.3f} dev={dev:.3f}"
              f"{'  WARNING' if dev > SENTINEL_WARN_DEV else ''}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Session Admission Gate")
    parser.add_argument("--skip-warmup", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  Evidence Campaign v1 — Session Admission Gate")
    print(f"  Server: {SERVER_URL}")
    print(f"{'='*65}\n")

    # Step 1: Warmup
    if not args.skip_warmup:
        warmup()
    else:
        print("  Warmup skipped (--skip-warmup)")

    # Step 2: Stabilization
    print("\n--- Stabilization Check ---")
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        stable, scores = stabilization_check()
        if stable:
            print(f"  Session stabilized on attempt {attempt}.")
            break
        if attempt < max_attempts:
            print(f"  Not stable. Re-warming (attempt {attempt+1}/{max_attempts})...")
            warmup()
    else:
        print("  FAILED: Session did not stabilize after 3 attempts.")
        sys.exit(1)

    # Step 3: Admission check
    print("\n--- Admission Check ---")
    admission = admission_check(scores)

    print(f"\n  Verdict: {admission['verdict']}")
    print(f"  Mean deviation: {admission['mean_absolute_deviation']:.4f}")
    print(f"  Max deviation:  {admission['max_deviation']:.4f}")

    if admission["hard_fails"]:
        print(f"\n  HARD FAILS:")
        for f in admission["hard_fails"]:
            print(f"    - {f}")

    if admission["warnings"]:
        print(f"\n  WARNINGS:")
        for w in admission["warnings"]:
            print(f"    - {w}")

    for pid, data in admission["anchor_scores"].items():
        ref = REFERENCE[pid]
        dev = admission["deviations"][pid]
        label_ok = data["weakness_type"] == ref["weakness_type"]
        print(f"  {pid:18s} measured={data['score']:.3f} ref={ref['score']:.3f} "
              f"dev={dev:.3f} wt={'OK' if label_ok else 'MISMATCH'}")

    # Step 4: Sentinel check (only if admitted)
    sentinel_result = None
    if admission["verdict"] != "REJECTED":
        sentinel_result = sentinel_check()

    # Write session log
    log_entry = {
        "session_id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "admission": admission,
        "sentinels": sentinel_result,
    }

    log_path = PROJECT_ROOT / "evidence_campaign" / "session_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(f"\n  Session log appended: {log_path}")

    print(f"\n{'='*65}")
    print(f"  FINAL: {admission['verdict']}")
    print(f"{'='*65}")

    sys.exit(0 if admission["verdict"] != "REJECTED" else 1)


if __name__ == "__main__":
    main()
