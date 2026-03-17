#!/usr/bin/env python3
"""
Evidence Campaign v1 — Day 1 Anchor Probe Evaluation

Runs the 6 anchor probes (5 primary + 1 reserve) against v5-think via llama-server,
scores each, classifies weakness_type, and outputs the frozen anchor manifest.

Usage:
    python scripts/campaign_anchor_eval.py                    # single run
    python scripts/campaign_anchor_eval.py --runs 2           # 2 runs for variance check
    python scripts/campaign_anchor_eval.py --output manifest  # write manifest JSON
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.probe_library import (
    PYTHON_PROBES, RUST_PROBES, GO_PROBES, CPP_PROBES, JS_PROBES, HIVE_PROBES,
)
from scripts.weakness_trend import classify_weakness_type, WEAKNESS_CLASSIFIER_VERSION

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:11435")
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

# 5 primary anchors + dead reserves (canonical_buckets.json is source of truth)
ANCHOR_IDS = {
    "B1": "js-generics",
    "B2": "py-metaclass",
    "B3": "rs-ownership",
    "B4": "cpp-variadic",
    "B5": "rs-errors",
}

# Template assignment per bucket
BUCKET_TEMPLATES = {
    "B1": "implement",
    "B2": "explain",
    "B3": "debug_fix",
    "B4": "implement",
    "B5": "debug_fix",
}


def _find_probe(probe_id: str):
    """Find a probe by ID across all domain lists."""
    all_probes = PYTHON_PROBES + RUST_PROBES + GO_PROBES + CPP_PROBES + JS_PROBES + HIVE_PROBES
    for p in all_probes:
        if p.id == probe_id:
            return p
    return None


def _call_llama(prompt: str, max_retries: int = 2) -> str:
    """Call llama-server and return the response text."""
    payload = json.dumps({
        "model": "hiveai",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
        "top_k": 1,
        "seed": 42,
    }).encode()

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{SERVER_URL}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"].get("content", "")
            if not content:
                content = result["choices"][0]["message"].get("reasoning_content", "")
            if content:
                return content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(2)
    return ""


def score_response(response: str, expected_keywords: list) -> dict:
    """Score a probe response — IDENTICAL to regression_eval.py scoring.

    DO NOT modify this function without also updating regression_eval.py.
    Any divergence invalidates campaign baselines.
    """
    if not response or not response.strip():
        return {"score": 0.0, "keyword_score": 0.0, "structure_score": 0.0,
                "keywords_hit": 0, "keywords_total": len(expected_keywords)}
    text = response.lower()

    # Keyword coverage (unique matches, case-insensitive substring)
    found = sum(1 for kw in expected_keywords if kw.lower() in text)
    keyword_score = found / len(expected_keywords) if expected_keywords else 0.0

    # Structural quality signals (4 binary signals)
    structure_signals = []

    # Has fenced code blocks (regex: requires newline after opening fence)
    has_code = bool(re.search(r"```\w*\n", response))
    structure_signals.append(1.0 if has_code else 0.0)

    # Has function/class/struct definitions (word-boundary regex)
    has_definitions = bool(re.search(
        r"\b(def |fn |func |function |class |struct |impl |interface )\b",
        response
    ))
    structure_signals.append(1.0 if has_definitions else 0.0)

    # Reasonable length (>200 chars stripped)
    structure_signals.append(1.0 if len(response.strip()) > 200 else 0.3)

    # Has explanatory prose (not just a code dump)
    prose_text = re.sub(r"```[\s\S]*?```", "", response).strip()
    structure_signals.append(1.0 if len(prose_text) > 50 else 0.2)

    structure_score = sum(structure_signals) / len(structure_signals)

    # Combined: 70% keyword, 30% structure
    combined = keyword_score * 0.7 + structure_score * 0.3

    return {
        "score": round(combined, 4),
        "keyword_score": round(keyword_score, 4),
        "structure_score": round(structure_score, 4),
        "keywords_hit": found,
        "keywords_total": len(expected_keywords),
    }


def run_anchor_eval(run_id: int = 1) -> dict:
    """Run all 6 anchor probes and return results."""
    results = {}

    for bucket, probe_id in ANCHOR_IDS.items():
        probe = _find_probe(probe_id)
        if not probe:
            print(f"  ERROR: probe {probe_id} not found!", file=sys.stderr)
            continue

        print(f"  [{bucket}] Running {probe_id} (run {run_id})...", end=" ", flush=True)
        t0 = time.time()
        response = _call_llama(probe.prompt)
        elapsed = time.time() - t0

        if not response:
            print(f"EMPTY RESPONSE ({elapsed:.1f}s)")
            results[bucket] = {
                "probe_id": probe_id,
                "domain": probe.domain,
                "template": BUCKET_TEMPLATES[bucket],
                "score": 0.0,
                "keyword_score": 0.0,
                "structure_score": 0.0,
                "keywords_hit": 0,
                "keywords_total": len(probe.expected_keywords),
                "weakness_type": "compound",
                "elapsed_s": round(elapsed, 1),
            }
            continue

        scores = score_response(response, probe.expected_keywords)
        wt = classify_weakness_type(scores["keyword_score"], scores["structure_score"])

        print(f"score={scores['score']:.3f} kw={scores['keyword_score']:.3f} "
              f"str={scores['structure_score']:.3f} wt={wt} ({elapsed:.1f}s)")

        results[bucket] = {
            "probe_id": probe_id,
            "domain": probe.domain,
            "template": BUCKET_TEMPLATES[bucket],
            **scores,
            "weakness_type": wt,
            "elapsed_s": round(elapsed, 1),
        }

    return results


def check_diversity(results: dict) -> dict:
    """Check diversity requirements across B1-B5 (primary buckets only)."""
    primary = {k: v for k, v in results.items() if k.startswith("B")}

    domains = set(v["domain"] for v in primary.values())
    weakness_types = set(v["weakness_type"] for v in primary.values())
    templates = set(v["template"] for v in primary.values())

    checks = {
        "domains_count": len(domains),
        "domains": sorted(domains),
        "domains_pass": len(domains) >= 3,
        "weakness_types_count": len(weakness_types),
        "weakness_types": sorted(weakness_types),
        "weakness_types_pass": len(weakness_types) >= 2,
        "templates_count": len(templates),
        "templates": sorted(templates),
        "templates_pass": len(templates) >= 3,
    }
    checks["all_pass"] = all([
        checks["domains_pass"],
        checks["weakness_types_pass"],
        checks["templates_pass"],
    ])
    return checks


def compute_variance(all_runs: list[dict]) -> dict:
    """Compute per-bucket score variance across runs."""
    if len(all_runs) < 2:
        return {"note": "Need 2+ runs for variance", "max_variance": 0.0}

    buckets = list(all_runs[0].keys())
    variances = {}
    for b in buckets:
        scores = [run[b]["score"] for run in all_runs if b in run]
        if len(scores) < 2:
            continue
        mean = sum(scores) / len(scores)
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        variances[b] = {
            "scores": scores,
            "mean": round(mean, 4),
            "variance": round(var, 6),
            "max_delta": round(max(scores) - min(scores), 4),
        }

    max_var = max(v["variance"] for v in variances.values()) if variances else 0.0
    return {
        "per_bucket": variances,
        "max_variance": round(max_var, 6),
        "max_delta": round(max(v["max_delta"] for v in variances.values()), 4) if variances else 0.0,
        "stable": max_var < 0.005,  # variance < 0.5% threshold
    }


def _get_git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                           cwd=str(PROJECT_ROOT), timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _file_sha256(path: str) -> str:
    try:
        h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return h
    except Exception:
        return "unknown"


def build_manifest(results: dict, diversity: dict, variance: dict, num_runs: int) -> dict:
    """Build the frozen campaign manifest."""
    # Use the last run's results as the canonical scores
    return {
        "campaign": "evidence_campaign_v1",
        "day": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_parameters": {
            "base_model": "v5-think-consolidated",
            "base_model_quant": "Q5_K_M",
            "eval_mode": "full",
            "weakness_classifier_version": WEAKNESS_CLASSIFIER_VERSION,
            "success_threshold": 0.01,
            "attribution": "isolated",
            "critique_memory_influence": False,
            "bayesian_calibration_enabled": False,
            "serving_checkpoint": "unchanged",
            "shadow_data_usable_for_live_calibration": False,
        },
        "hashes": {
            "git_sha": _get_git_sha(),
            "probe_library_sha256": _file_sha256(PROJECT_ROOT / "scripts" / "probe_library.py"),
            "regression_eval_sha256": _file_sha256(PROJECT_ROOT / "scripts" / "regression_eval.py"),
            "weakness_trend_sha256": _file_sha256(PROJECT_ROOT / "scripts" / "weakness_trend.py"),
            "campaign_anchor_eval_sha256": _file_sha256(PROJECT_ROOT / "scripts" / "campaign_anchor_eval.py"),
        },
        "anchor_probes": results,
        "diversity_check": diversity,
        "baseline_variance": variance,
        "num_baseline_runs": num_runs,
        "notes": [
            "Day 1: Manifest frozen with anchor probe scores and weakness classifications.",
            "Model is frozen v5-think. No serving-path changes for 30 days.",
            f"Weakness classifier v{WEAKNESS_CLASSIFIER_VERSION}: keyword<0.70=keyword_only, structure<0.50=structure_only, both=compound, neither=none.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Evidence Campaign v1 — Anchor Probe Eval")
    parser.add_argument("--runs", type=int, default=2, help="Number of eval runs (default: 2)")
    parser.add_argument("--output", type=str, default="manifest",
                        choices=["manifest", "table", "json"],
                        help="Output format (default: manifest)")
    parser.add_argument("--server", type=str, default=None, help="Override llama-server URL")
    args = parser.parse_args()

    if args.server:
        global SERVER_URL
        SERVER_URL = args.server

    print(f"\n{'='*65}")
    print(f"  Evidence Campaign v1 — Day 1 Anchor Evaluation")
    print(f"  Server: {SERVER_URL}")
    print(f"  Runs: {args.runs}")
    print(f"  Weakness classifier: v{WEAKNESS_CLASSIFIER_VERSION}")
    print(f"{'='*65}\n")

    all_runs = []
    for run_idx in range(1, args.runs + 1):
        print(f"--- Run {run_idx}/{args.runs} ---")
        results = run_anchor_eval(run_id=run_idx)
        all_runs.append(results)
        print()

    # Use last run as canonical
    canonical = all_runs[-1]

    # Diversity check
    diversity = check_diversity(canonical)

    # Variance check
    variance = compute_variance(all_runs)

    if args.output == "table":
        print(f"\n{'Bucket':>6} {'Probe':>16} {'Domain':>8} {'Template':>10} "
              f"{'Score':>6} {'KW':>6} {'Str':>6} {'Weakness':>14}")
        print("-" * 80)
        for bucket in ["B1", "B2", "B3", "B4", "B5", "R1"]:
            r = canonical.get(bucket, {})
            print(f"  {bucket:>4} {r.get('probe_id',''):>16} {r.get('domain',''):>8} "
                  f"{r.get('template',''):>10} {r.get('score',0):6.3f} "
                  f"{r.get('keyword_score',0):6.3f} {r.get('structure_score',0):6.3f} "
                  f"{r.get('weakness_type',''):>14}")

        print(f"\nDiversity: domains={diversity['domains_count']} "
              f"weakness_types={diversity['weakness_types_count']} "
              f"templates={diversity['templates_count']} "
              f"{'PASS' if diversity['all_pass'] else 'FAIL'}")

        if args.runs >= 2:
            print(f"Variance: max_delta={variance.get('max_delta', 0):.4f} "
                  f"{'STABLE' if variance.get('stable', False) else 'UNSTABLE'}")

    elif args.output == "json":
        print(json.dumps(canonical, indent=2))

    else:  # manifest
        manifest = build_manifest(canonical, diversity, variance, args.runs)
        manifest_path = PROJECT_ROOT / "evidence_campaign" / "manifest_v1.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"  Manifest written: {manifest_path}")

        # Also print summary
        print(f"\n{'='*65}")
        print(f"  CAMPAIGN MANIFEST v1 — FROZEN")
        print(f"{'='*65}")
        for bucket in ["B1", "B2", "B3", "B4", "B5", "R1"]:
            r = canonical.get(bucket, {})
            wt = r.get("weakness_type", "?")
            marker = " *" if wt != "none" else ""
            print(f"  {bucket}: {r.get('probe_id',''):16s} | {r.get('domain',''):6s} | "
                  f"{r.get('template',''):10s} | score={r.get('score',0):.3f} | "
                  f"wt={wt}{marker}")

        print(f"\n  Diversity: {'PASS' if diversity['all_pass'] else 'FAIL'}")
        print(f"    Domains: {diversity['domains_count']} ({', '.join(diversity['domains'])})")
        print(f"    Weakness types: {diversity['weakness_types_count']} ({', '.join(diversity['weakness_types'])})")
        print(f"    Templates: {diversity['templates_count']} ({', '.join(diversity['templates'])})")

        if args.runs >= 2:
            print(f"\n  Baseline variance: max_delta={variance.get('max_delta', 0):.4f} "
                  f"{'STABLE' if variance.get('stable', False) else 'UNSTABLE'}")

        print(f"\n  Git SHA: {manifest['hashes']['git_sha'][:12]}")
        print(f"{'='*65}")


if __name__ == "__main__":
    main()
