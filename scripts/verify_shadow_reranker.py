#!/usr/bin/env python3
"""
Verify shadow reranker integration.

Sends the P1 residual cases through the live chat endpoint and checks that
shadow reranker trace fields are present and populated correctly.

Usage:
    python scripts/verify_shadow_reranker.py [--base-url http://localhost:5001]
"""
import argparse
import json
import sys
import requests

# P1 residual cases: 3 false accepts, 1 false reject, 3 borderline off-domain
RESIDUAL_QUERIES = [
    # False accepts (off-domain, nearest < 0.46)
    {"id": "XO-05", "query": "Write a React component that fetches data from a REST API and displays it in a table",
     "label": "off_domain", "category": "false_accept"},
    {"id": "XO-02", "query": "How do I train a TensorFlow model on ImageNet?",
     "label": "off_domain", "category": "false_accept"},
    {"id": "C3", "query": "How do I configure nginx reverse proxy with SSL termination?",
     "label": "off_domain", "category": "false_accept"},
    # False reject (in-domain, mean-top-5 >= 0.46)
    {"id": "A2", "query": "How does HiveAI's RAG retrieval pipeline work with BGE-M3 embeddings?",
     "label": "in_domain", "category": "false_reject"},
    # Borderline off-domain (0.46 <= nearest < 0.52) — sample
    {"id": "XO-07", "query": "Explain the difference between SQL and NoSQL databases",
     "label": "off_domain", "category": "borderline"},
    {"id": "XO-11", "query": "What is the CAP theorem and how does it apply to distributed systems?",
     "label": "off_domain", "category": "borderline"},
]

REQUIRED_TRACE_FIELDS = [
    "reranker_shadow_applied",
    "reranker_best_score",
    "reranker_score_count",
    "reranker_top_scores",
    "reranker_per_section",
    "reranker_candidate_threshold",
    "would_suppress_reranker",
    "would_filter_sections_reranker",
    "reranker_shadow_latency_ms",
]


def send_query(base_url, query_text):
    """Send a query to the chat endpoint and return the full response."""
    resp = requests.post(
        f"{base_url}/api/chat",
        json={"message": query_text, "history": []},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def check_trace(response_json, query_id):
    """Validate shadow reranker fields in the response trace."""
    trace = response_json.get("trace", {}).get("retrieval_trace", {})
    if not trace:
        return False, "no retrieval_trace in response"

    missing = [f for f in REQUIRED_TRACE_FIELDS if f not in trace]
    if missing:
        return False, f"missing fields: {missing}"

    if not trace.get("reranker_shadow_applied"):
        reason = trace.get("reranker_shadow_reason", "unknown")
        return False, f"shadow not applied: {reason}"

    # Validate types
    best = trace["reranker_best_score"]
    if not isinstance(best, (int, float)):
        return False, f"reranker_best_score not numeric: {type(best)}"

    top_scores = trace["reranker_top_scores"]
    if not isinstance(top_scores, list) or len(top_scores) == 0:
        return False, f"reranker_top_scores not a non-empty list"

    per_section = trace["reranker_per_section"]
    if not isinstance(per_section, list):
        return False, f"reranker_per_section not a list"

    latency = trace["reranker_shadow_latency_ms"]
    if not isinstance(latency, (int, float)) or latency < 0:
        return False, f"reranker_shadow_latency_ms invalid: {latency}"

    return True, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5001")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    args = parser.parse_args()

    results = []
    all_pass = True

    print(f"Shadow reranker verification — {args.base_url}")
    print(f"Sending {len(RESIDUAL_QUERIES)} residual queries...\n")

    for q in RESIDUAL_QUERIES:
        print(f"  [{q['id']}] {q['query'][:60]}...", end=" ", flush=True)
        try:
            resp = send_query(args.base_url, q["query"])
            ok, err = check_trace(resp, q["id"])

            trace = resp.get("trace", {}).get("retrieval_trace", {})
            result = {
                "id": q["id"],
                "label": q["label"],
                "category": q["category"],
                "trace_pass": ok,
                "error": err,
                "reranker_best_score": trace.get("reranker_best_score"),
                "reranker_top_scores": trace.get("reranker_top_scores"),
                "would_suppress_reranker": trace.get("would_suppress_reranker"),
                "reranker_shadow_latency_ms": trace.get("reranker_shadow_latency_ms"),
                "reranker_score_count": trace.get("reranker_score_count"),
                "trace_schema_version": trace.get("trace_schema_version"),
            }
            results.append(result)

            if ok:
                print(f"PASS  best={trace['reranker_best_score']:.4f}  "
                      f"suppress={trace['would_suppress_reranker']}  "
                      f"latency={trace['reranker_shadow_latency_ms']:.0f}ms")
            else:
                print(f"FAIL  {err}")
                all_pass = False

        except Exception as e:
            print(f"ERROR  {e}")
            results.append({
                "id": q["id"], "label": q["label"], "category": q["category"],
                "trace_pass": False, "error": str(e),
            })
            all_pass = False

    # Summary
    print(f"\n{'='*70}")
    passed = sum(1 for r in results if r.get("trace_pass"))
    print(f"Result: {passed}/{len(results)} queries have valid shadow reranker traces")

    if all_pass:
        # Check separation
        fa_scores = [r["reranker_best_score"] for r in results
                     if r.get("category") == "false_accept" and r.get("reranker_best_score") is not None]
        fr_scores = [r["reranker_best_score"] for r in results
                     if r.get("category") == "false_reject" and r.get("reranker_best_score") is not None]
        if fa_scores and fr_scores:
            fa_max = max(fa_scores)
            fr_min = min(fr_scores)
            print(f"\nSeparation check (P1 residual):")
            print(f"  FA max reranker_best: {fa_max:.4f}")
            print(f"  FR min reranker_best: {fr_min:.4f}")
            print(f"  Gap: {fr_min - fa_max:.4f}")
            if fa_max < fr_min:
                print(f"  -> Clean separation confirmed in live trace")
            else:
                print(f"  -> Overlap detected — calibration needed")

        latencies = [r["reranker_shadow_latency_ms"] for r in results
                     if r.get("reranker_shadow_latency_ms") is not None]
        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            print(f"\nLatency (shadow reranker only):")
            print(f"  p50: {p50:.0f}ms  p95: {p95:.0f}ms  max: {max(latencies):.0f}ms")

    if args.json:
        print(f"\n{json.dumps(results, indent=2)}")

    print(f"\nVerdict: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
