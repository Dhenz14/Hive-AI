#!/usr/bin/env python3
"""
eval_skills.py — Measure skill lift: how much skill injection improves responses.

For each skill with test cases, runs queries with and without skill injection,
measures keyword coverage, and reports the "skill lift" per skill.

Requires a running LLM server (Ollama or llama-server).

Usage:
    python scripts/eval_skills.py                                    # All skills
    python scripts/eval_skills.py --skill hive_sdk                   # Single skill
    python scripts/eval_skills.py --base-url http://localhost:11435   # Custom server
    python scripts/eval_skills.py --model qwen3:14b                  # Custom model
    python scripts/eval_skills.py --json                             # JSON output
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SKILLS_DIR = PROJECT_ROOT / "skills"
EVALS_DIR = PROJECT_ROOT / "evals"

DEFAULT_MODEL = "qwen3:14b"
DEFAULT_BASE_URL = None  # Use Ollama by default
TIMEOUT = 120


def call_model(prompt: str, system: str, model: str, base_url: str = None) -> str:
    """Call LLM and return response text."""
    import urllib.request

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    if base_url:
        # OpenAI-compatible endpoint (llama-server)
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3,
        }
    else:
        # Ollama native endpoint
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 2048},
        }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        result = json.loads(resp.read().decode())

        if base_url:
            return result["choices"][0]["message"]["content"]
        else:
            content = result.get("message", {}).get("content", "")
            # Strip thinking tags if present
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content

    except Exception as e:
        logger.error(f"Model call failed: {e}")
        return ""


def load_skill_tests() -> dict[str, dict]:
    """Load all skill_meta.json test cases.

    Returns {skill_name: {title, description, test_cases, skill_content}}.
    """
    skills = {}

    for meta_path in sorted(SKILLS_DIR.glob("*/skill_meta.json")):
        skill_name = meta_path.parent.name
        skill_md = meta_path.parent / "SKILL.md"

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        skill_content = ""
        if skill_md.exists():
            with open(skill_md, encoding="utf-8") as f:
                skill_content = f.read()

        if not meta.get("test_cases"):
            continue

        skills[skill_name] = {
            "title": meta.get("title", skill_name),
            "description": meta.get("description", ""),
            "test_cases": meta["test_cases"],
            "skill_content": skill_content,
        }

    return skills


def score_keyword_coverage(response: str, expected_keywords: list[str]) -> float:
    """Score keyword coverage (0.0-1.0)."""
    if not expected_keywords:
        return 1.0

    response_lower = response.lower()
    hits = 0
    for kw in expected_keywords:
        # Case-insensitive word boundary match for short keywords
        if len(kw) <= 6:
            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", response_lower):
                hits += 1
        else:
            if kw.lower() in response_lower:
                hits += 1

    return hits / len(expected_keywords)


def score_response_quality(response: str) -> dict:
    """Score response quality on multiple dimensions."""
    word_count = len(response.split())

    # Has code
    has_code = bool(re.search(r"```[\w]*\n", response))

    # Explanation depth
    explanation_markers = [
        "because", "this works", "note that", "important", "the reason",
        "for example", "however", "trade-off", "edge case", "best practice",
    ]
    marker_count = sum(1 for m in explanation_markers if m in response.lower())

    # Structure
    has_headers = bool(re.search(r"^#{1,3}\s", response, re.MULTILINE))
    has_bold = "**" in response

    return {
        "word_count": word_count,
        "has_code": has_code,
        "explanation_markers": marker_count,
        "has_structure": has_headers or has_bold,
        "quality_score": min(
            (0.3 if has_code else 0.0) +
            min(marker_count / 5.0, 0.3) +
            min(word_count / 300.0, 0.25) +
            (0.15 if has_headers or has_bold else 0.0),
            1.0
        ),
    }


def eval_skill(skill_name: str, skill_data: dict, model: str,
               base_url: str = None, system_prompt: str = "") -> dict:
    """Evaluate a single skill by comparing responses with/without skill injection.

    Returns {skill_name, test_results, avg_lift, ...}.
    """
    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    base_system = system_prompt or CODING_SYSTEM_PROMPT
    skill_system = base_system + "\n\n" + skill_data["skill_content"]

    test_results = []

    for i, test_case in enumerate(skill_data["test_cases"]):
        query = test_case["input"]
        expected = test_case.get("expected_keywords", [])

        logger.info(f"  [{skill_name}] Test {i+1}/{len(skill_data['test_cases'])}: {query[:60]}...")

        # Run WITHOUT skill
        t0 = time.time()
        response_without = call_model(query, base_system, model, base_url)
        time_without = time.time() - t0

        # Run WITH skill
        t0 = time.time()
        response_with = call_model(query, skill_system, model, base_url)
        time_with = time.time() - t0

        # Score both
        kw_without = score_keyword_coverage(response_without, expected)
        kw_with = score_keyword_coverage(response_with, expected)
        quality_without = score_response_quality(response_without)
        quality_with = score_response_quality(response_with)

        lift_keywords = kw_with - kw_without
        lift_quality = quality_with["quality_score"] - quality_without["quality_score"]

        test_results.append({
            "query": query,
            "expected_keywords": expected,
            "without_skill": {
                "keyword_coverage": round(kw_without, 3),
                "quality": round(quality_without["quality_score"], 3),
                "word_count": quality_without["word_count"],
                "has_code": quality_without["has_code"],
                "time_ms": int(time_without * 1000),
                "response_preview": response_without[:200],
            },
            "with_skill": {
                "keyword_coverage": round(kw_with, 3),
                "quality": round(quality_with["quality_score"], 3),
                "word_count": quality_with["word_count"],
                "has_code": quality_with["has_code"],
                "time_ms": int(time_with * 1000),
                "response_preview": response_with[:200],
            },
            "lift_keywords": round(lift_keywords, 3),
            "lift_quality": round(lift_quality, 3),
        })

    # Aggregate
    avg_kw_lift = sum(t["lift_keywords"] for t in test_results) / max(len(test_results), 1)
    avg_quality_lift = sum(t["lift_quality"] for t in test_results) / max(len(test_results), 1)
    avg_kw_without = sum(t["without_skill"]["keyword_coverage"] for t in test_results) / max(len(test_results), 1)
    avg_kw_with = sum(t["with_skill"]["keyword_coverage"] for t in test_results) / max(len(test_results), 1)

    return {
        "skill_name": skill_name,
        "title": skill_data["title"],
        "test_count": len(test_results),
        "avg_keyword_without": round(avg_kw_without, 3),
        "avg_keyword_with": round(avg_kw_with, 3),
        "avg_keyword_lift": round(avg_kw_lift, 3),
        "avg_quality_lift": round(avg_quality_lift, 3),
        "verdict": "POSITIVE" if avg_kw_lift > 0.05 else "NEUTRAL" if avg_kw_lift >= -0.05 else "NEGATIVE",
        "test_results": test_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate skill injection lift")
    parser.add_argument("--skill", type=str, help="Evaluate specific skill only")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model to use")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL,
                        help="LLM server URL (OpenAI-compatible)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="List test cases without running")
    args = parser.parse_args()

    # Load skills
    all_skills = load_skill_tests()
    if not all_skills:
        print("No skills with test cases found in skills/*/skill_meta.json")
        sys.exit(1)

    if args.skill:
        if args.skill not in all_skills:
            print(f"Skill '{args.skill}' not found. Available: {list(all_skills.keys())}")
            sys.exit(1)
        skills_to_eval = {args.skill: all_skills[args.skill]}
    else:
        skills_to_eval = all_skills

    if args.dry_run:
        print(f"\n{'Skill':<25} {'Tests':>5}  Test Cases")
        print("-" * 80)
        for name, data in skills_to_eval.items():
            print(f"{name:<25} {len(data['test_cases']):>5}")
            for tc in data["test_cases"]:
                print(f"  {'':23} - {tc['input'][:55]}...")
        total = sum(len(d["test_cases"]) for d in skills_to_eval.values())
        print(f"\nTotal: {len(skills_to_eval)} skills, {total} test cases")
        print(f"Estimated time: {total * 2 * 15}s ({total * 2} model calls @ ~15s each)")
        return

    # Run evaluations
    print(f"\nEvaluating {len(skills_to_eval)} skills against {args.model}...")
    print(f"Each test case requires 2 model calls (with/without skill)")
    print()

    results = []
    for name, data in skills_to_eval.items():
        logger.info(f"Evaluating skill: {name} ({len(data['test_cases'])} tests)")
        result = eval_skill(name, data, args.model, args.base_url)
        results.append(result)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Pretty print
        print("\n" + "=" * 70)
        print("  SKILL LIFT EVALUATION REPORT")
        print("=" * 70)
        print(f"\n{'Skill':<25} {'Tests':>5} {'Without':>8} {'With':>8} {'Lift':>8} {'Verdict':<10}")
        print("-" * 70)

        for r in sorted(results, key=lambda x: x["avg_keyword_lift"], reverse=True):
            marker = "+++" if r["verdict"] == "POSITIVE" else "---" if r["verdict"] == "NEGATIVE" else "   "
            print(f"{r['skill_name']:<25} {r['test_count']:>5} "
                  f"{r['avg_keyword_without']:>7.0%} {r['avg_keyword_with']:>7.0%} "
                  f"{r['avg_keyword_lift']:>+7.0%} {r['verdict']:<10} {marker}")

        # Overall stats
        avg_lift = sum(r["avg_keyword_lift"] for r in results) / max(len(results), 1)
        positive = sum(1 for r in results if r["verdict"] == "POSITIVE")
        print(f"\nOverall: {positive}/{len(results)} skills show positive lift (avg: {avg_lift:+.1%})")

        # Per-test breakdown for interesting results
        for r in results:
            if r["verdict"] != "NEUTRAL":
                print(f"\n  [{r['skill_name']}] {r['title']}:")
                for t in r["test_results"]:
                    arrow = "^" if t["lift_keywords"] > 0.1 else "v" if t["lift_keywords"] < -0.1 else "="
                    print(f"    {arrow} {t['query'][:50]:50} "
                          f"{t['without_skill']['keyword_coverage']:.0%} -> "
                          f"{t['with_skill']['keyword_coverage']:.0%} "
                          f"({t['lift_keywords']:+.0%})")

    # Save results
    EVALS_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_path = EVALS_DIR / f"skill_eval_{args.model.replace(':', '-')}_{timestamp}.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": args.model,
            "timestamp": timestamp,
            "skills_evaluated": len(results),
            "results": results,
        }, f, indent=2)
    logger.info(f"Results saved to: {save_path}")


if __name__ == "__main__":
    main()
