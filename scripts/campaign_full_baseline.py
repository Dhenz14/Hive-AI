#!/usr/bin/env python3
"""
Evidence Campaign v1 — Full baseline for all probes in campaign domains.

Runs all probes for JS, Python, Rust, C++ with the SAME scorer as regression_eval.py.
Outputs per-probe scores, keyword/structure breakdown, and weakness classification.
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.probe_library import PYTHON_PROBES, RUST_PROBES, GO_PROBES, CPP_PROBES, JS_PROBES
from scripts.weakness_trend import classify_weakness_type, WEAKNESS_CLASSIFIER_VERSION

SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:11435")
SYSTEM_PROMPT = "You are HiveAI, an expert coding assistant. Answer directly without chain-of-thought reasoning."

# Campaign domains only (not hive, not go — go's anchor is dead)
CAMPAIGN_PROBES = {
    "js": JS_PROBES,
    "python": PYTHON_PROBES,
    "rust": RUST_PROBES,
    "cpp": CPP_PROBES,
}


def call_llama(prompt: str, max_retries: int = 2) -> str:
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
            print(f"    retry {attempt+1}: {e}", file=sys.stderr)
            time.sleep(2)
    return ""


def score_response(response: str, expected_keywords: list) -> dict:
    """IDENTICAL to regression_eval.py scoring."""
    if not response or not response.strip():
        return {"score": 0.0, "keyword_score": 0.0, "structure_score": 0.0,
                "keywords_hit": 0, "keywords_total": len(expected_keywords),
                "keywords_missed": [kw for kw in expected_keywords]}
    text = response.lower()

    found_kws = [kw for kw in expected_keywords if kw.lower() in text]
    missed_kws = [kw for kw in expected_keywords if kw.lower() not in text]
    keyword_score = len(found_kws) / len(expected_keywords) if expected_keywords else 0.0

    structure_signals = []
    has_code = bool(re.search(r"```\w*\n", response))
    structure_signals.append(1.0 if has_code else 0.0)
    has_definitions = bool(re.search(
        r"\b(def |fn |func |function |class |struct |impl |interface )\b", response))
    structure_signals.append(1.0 if has_definitions else 0.0)
    structure_signals.append(1.0 if len(response.strip()) > 200 else 0.3)
    prose_text = re.sub(r"```[\s\S]*?```", "", response).strip()
    structure_signals.append(1.0 if len(prose_text) > 50 else 0.2)
    structure_score = sum(structure_signals) / len(structure_signals)

    combined = keyword_score * 0.7 + structure_score * 0.3

    return {
        "score": round(combined, 4),
        "keyword_score": round(keyword_score, 4),
        "structure_score": round(structure_score, 4),
        "keywords_hit": len(found_kws),
        "keywords_total": len(expected_keywords),
        "keywords_missed": missed_kws,
    }


def main():
    print(f"\nEvidence Campaign v1 — Full Domain Baseline")
    print(f"Server: {SERVER_URL}")
    print(f"Domains: {', '.join(CAMPAIGN_PROBES.keys())}")
    print(f"Total probes: {sum(len(v) for v in CAMPAIGN_PROBES.values())}")
    print(f"Weakness classifier: v{WEAKNESS_CLASSIFIER_VERSION}")
    print()

    all_results = {}
    t_total = time.time()

    for domain, probes in CAMPAIGN_PROBES.items():
        print(f"--- {domain.upper()} ({len(probes)} probes) ---")
        domain_results = []

        for probe in probes:
            t0 = time.time()
            response = call_llama(probe.prompt)
            elapsed = time.time() - t0

            scores = score_response(response, probe.expected_keywords)
            wt = classify_weakness_type(scores["keyword_score"], scores["structure_score"])

            result = {
                "probe_id": probe.id,
                "domain": domain,
                "difficulty": probe.difficulty,
                **scores,
                "weakness_type": wt,
            }
            domain_results.append(result)

            flag = " *" if wt != "none" else ""
            missed = f" missed={scores['keywords_missed']}" if scores["keywords_missed"] else ""
            print(f"  {probe.id:22s} score={scores['score']:.3f} "
                  f"kw={scores['keyword_score']:.3f} ({scores['keywords_hit']}/{scores['keywords_total']}) "
                  f"str={scores['structure_score']:.3f} wt={wt}{flag} ({elapsed:.1f}s){missed}")

        avg = sum(r["score"] for r in domain_results) / len(domain_results)
        print(f"  Domain avg: {avg:.3f}\n")
        all_results[domain] = domain_results

    total_time = time.time() - t_total
    print(f"Total: {sum(len(v) for v in all_results.values())} probes in {total_time:.0f}s")

    # Write results
    output_path = PROJECT_ROOT / "evidence_campaign" / "full_baseline.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Written: {output_path}")

    # Headroom summary
    print(f"\n--- Headroom Summary ---")
    for domain, results in all_results.items():
        below_90 = [r for r in results if r["score"] < 0.90]
        below_95 = [r for r in results if 0.90 <= r["score"] < 0.95]
        at_ceiling = [r for r in results if r["score"] >= 0.95]
        print(f"  {domain:8s}: {len(below_90)} below 0.90, "
              f"{len(below_95)} at 0.90-0.95, {len(at_ceiling)} at ceiling (≥0.95)")
        for r in below_90:
            print(f"    {r['probe_id']:22s} score={r['score']:.3f} headroom={1.0-r['score']:.1%}")


if __name__ == "__main__":
    main()
