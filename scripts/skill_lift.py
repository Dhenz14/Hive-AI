#!/usr/bin/env python3
"""
scripts/skill_lift.py — Measure the impact of each agent skill on eval scores.

For each skill, runs a subset of relevant eval challenges WITH the skill injected
into the system prompt vs WITHOUT (baseline). Reports the delta ("skill lift")
per skill and per category.

This implements the ACE feedback loop (improvement_notes.md §30): measure which
skills actually help, which are dead weight, and which need improvement.

Requires llama-server running at http://localhost:11435 with LoRA adapter.

Usage:
    python scripts/skill_lift.py                     # Test all skills
    python scripts/skill_lift.py --skill rust_async   # Test one skill
    python scripts/skill_lift.py --limit 5            # Max challenges per skill
    python scripts/skill_lift.py --json               # Machine-readable output
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from skills.skill_loader import load_skill, list_available_skills, SKILL_ROUTES

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:11435"
TEMPERATURE = 0.1
MAX_TOKENS = 1024
TIMEOUT = 120

# Map skill names → eval challenge categories they should help
SKILL_CATEGORY_MAP = {
    "rust_async":       ["rust"],
    "go_concurrency":   ["go"],
    "cpp_modern":       ["cpp"],
    "js_typescript":    ["javascript", "web"],
    "hive_sdk":         ["hive_sdk"],
    "hive_architecture": ["hive_architecture"],
    "hive_economics":   ["hive_economics"],
    "hive_layer2":      ["hive_layer2"],
    "hive_security":    ["hive_security"],
    "hive_custom_json": ["hive_sdk", "hive_layer2"],  # custom_json spans both
    "debugging_patterns": ["python", "algorithms"],   # general debugging
    "long_context":     [],  # no direct eval category, skip
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_challenges() -> list[dict]:
    """Load eval challenges from JSON."""
    path = PROJECT_ROOT / "scripts" / "eval_challenges.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chat_completion(prompt: str, system_prompt: str) -> str:
    """Send a chat completion and return the response text."""
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": "hiveai",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def score_response(text: str, challenge: dict) -> dict:
    """Quick scoring: keyword coverage + code presence + test execution."""
    concepts = challenge.get("expected_concepts", [])

    # Concept coverage (keyword match)
    if concepts:
        found = sum(1 for kw in concepts if kw.lower() in text.lower())
        concept_score = found / len(concepts)
    else:
        concept_score = 0.5

    # Code presence
    has_code = 1.0 if "```" in text else (0.5 if "`" in text else 0.0)

    # Test execution (Python only)
    test_score = None
    test_code = challenge.get("test_code")
    if test_code and challenge.get("category") == "python":
        test_score = _try_run_test(text, test_code)

    # Explanation quality (heuristic: non-code text length)
    stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    word_count = len(stripped.split())
    explanation = min(word_count / 80, 1.0)

    # Weighted overall
    dims = [concept_score * 0.35, has_code * 0.25, explanation * 0.20]
    if test_score is not None:
        dims.append(test_score * 0.20)
    else:
        # Redistribute test weight
        dims = [concept_score * 0.40, has_code * 0.30, explanation * 0.30]

    overall = sum(dims)
    return {
        "concept_coverage": round(concept_score, 3),
        "has_code": has_code,
        "test_passing": test_score,
        "explanation": round(explanation, 3),
        "overall": round(overall, 3),
    }


def _try_run_test(response_text: str, test_code: str) -> float:
    """Extract Python code from response, append test_code, run it."""
    import subprocess
    import tempfile

    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", response_text,
                        re.DOTALL | re.IGNORECASE)
    if not blocks:
        return 0.0

    combined = "\n\n".join(blocks) + "\n\n" + test_code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(combined)
        tmp = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp], capture_output=True, timeout=15, text=True,
        )
        return 1.0 if result.returncode == 0 else 0.0
    except Exception:
        return 0.0
    finally:
        Path(tmp).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Core: Skill Lift Measurement
# ---------------------------------------------------------------------------

def measure_skill_lift(skill_name: str, challenges: list[dict],
                       limit: int = 10, verbose: bool = True) -> dict:
    """Run challenges with and without a skill, return lift metrics."""
    skill_content = load_skill(skill_name)
    if not skill_content:
        return {"error": f"Skill '{skill_name}' not found"}

    # Get relevant categories for this skill
    categories = SKILL_CATEGORY_MAP.get(skill_name, [])
    if not categories:
        return {"error": f"No eval categories mapped for skill '{skill_name}'"}

    # Filter challenges to relevant categories
    relevant = [c for c in challenges if c["category"] in categories]
    if not relevant:
        return {"error": f"No challenges found for categories {categories}"}

    # Limit
    relevant = relevant[:limit]

    base_system = "You are HiveAI, an expert coding assistant."
    skill_system = (
        "You are HiveAI, an expert coding assistant.\n\n"
        "--- DOMAIN EXPERTISE (use as reference) ---\n\n"
        f"{skill_content}"
    )

    baseline_scores = []
    skill_scores = []

    for i, challenge in enumerate(relevant):
        cid = challenge["id"]
        instruction = challenge["instruction"]

        if verbose:
            print(f"  [{i+1}/{len(relevant)}] {cid}...", end=" ", flush=True)

        # Baseline (no skill)
        try:
            t0 = time.time()
            resp_base = chat_completion(instruction, base_system)
            base_time = time.time() - t0
            sc_base = score_response(resp_base, challenge)
        except Exception as e:
            sc_base = {"overall": 0.0, "error": str(e)}
            base_time = 0

        # With skill
        try:
            t0 = time.time()
            resp_skill = chat_completion(instruction, skill_system)
            skill_time = time.time() - t0
            sc_skill = score_response(resp_skill, challenge)
        except Exception as e:
            sc_skill = {"overall": 0.0, "error": str(e)}
            skill_time = 0

        delta = sc_skill["overall"] - sc_base["overall"]
        if verbose:
            print(f"base={sc_base['overall']:.3f} skill={sc_skill['overall']:.3f} "
                  f"delta={delta:+.3f} ({base_time:.1f}s/{skill_time:.1f}s)")

        baseline_scores.append(sc_base)
        skill_scores.append(sc_skill)

    # Aggregate
    avg_base = sum(s["overall"] for s in baseline_scores) / len(baseline_scores)
    avg_skill = sum(s["overall"] for s in skill_scores) / len(skill_scores)
    lift = avg_skill - avg_base

    # Per-challenge deltas
    deltas = [s["overall"] - b["overall"]
              for s, b in zip(skill_scores, baseline_scores)]
    improved = sum(1 for d in deltas if d > 0.02)
    degraded = sum(1 for d in deltas if d < -0.02)
    neutral = len(deltas) - improved - degraded

    return {
        "skill": skill_name,
        "categories": categories,
        "n_challenges": len(relevant),
        "avg_baseline": round(avg_base, 4),
        "avg_with_skill": round(avg_skill, 4),
        "lift": round(lift, 4),
        "lift_pct": round(lift * 100, 2),
        "improved": improved,
        "degraded": degraded,
        "neutral": neutral,
        "per_challenge": [
            {
                "id": relevant[i]["id"],
                "baseline": baseline_scores[i]["overall"],
                "with_skill": skill_scores[i]["overall"],
                "delta": round(deltas[i], 4),
            }
            for i in range(len(relevant))
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Measure skill lift: eval scores WITH vs WITHOUT each skill")
    parser.add_argument("--skill", type=str, default=None,
                        help="Test a single skill (e.g. 'rust_async')")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max challenges per skill (default: 10)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of table")
    parser.add_argument("--base-url", type=str, default=BASE_URL,
                        help=f"llama-server URL (default: {BASE_URL})")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    # Connectivity check
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
    except requests.ConnectionError:
        print(f"ERROR: Cannot reach llama-server at {BASE_URL}", file=sys.stderr)
        sys.exit(1)

    challenges = load_challenges()
    available = list_available_skills()
    available_names = {s["name"] for s in available}

    # Determine which skills to test
    if args.skill:
        if args.skill not in available_names:
            print(f"ERROR: Skill '{args.skill}' not found. Available: "
                  f"{sorted(available_names)}", file=sys.stderr)
            sys.exit(1)
        skills_to_test = [args.skill]
    else:
        # All skills that have category mappings
        skills_to_test = [
            name for name in SKILL_CATEGORY_MAP
            if name in available_names and SKILL_CATEGORY_MAP[name]
        ]

    print(f"Testing {len(skills_to_test)} skills against {len(challenges)} challenges "
          f"(limit {args.limit}/skill)\n")

    all_results = []
    for skill_name in sorted(skills_to_test):
        print(f"\n{'='*60}")
        print(f"  Skill: {skill_name}")
        print(f"{'='*60}")
        result = measure_skill_lift(skill_name, challenges, args.limit, verbose=True)
        all_results.append(result)

        if "error" not in result:
            lift = result["lift"]
            pct = result["lift_pct"]
            verdict = ("HELPS" if lift > 0.02 else
                      "HURTS" if lift < -0.02 else
                      "NEUTRAL")
            print(f"\n  Result: {verdict} — lift={lift:+.4f} ({pct:+.2f}%) "
                  f"[{result['improved']} improved, {result['degraded']} degraded, "
                  f"{result['neutral']} neutral]")
        else:
            print(f"\n  Skipped: {result['error']}")

    # Summary table
    if not args.json:
        print(f"\n{'='*70}")
        print(f"  SKILL LIFT SUMMARY")
        print(f"{'='*70}")
        print(f"{'Skill':<22} {'Lift':>8} {'Pct':>7} {'N':>4} {'Up':>4} {'Down':>4} {'Verdict'}")
        print("-" * 70)

        for r in sorted(all_results, key=lambda x: x.get("lift", -99), reverse=True):
            if "error" in r:
                print(f"{r['skill']:<22} {'—':>8} {'—':>7} {'—':>4} {'—':>4} {'—':>4} SKIP: {r['error'][:30]}")
                continue
            verdict = ("HELPS" if r["lift"] > 0.02 else
                      "HURTS" if r["lift"] < -0.02 else
                      "NEUTRAL")
            print(f"{r['skill']:<22} {r['lift']:>+8.4f} {r['lift_pct']:>+6.2f}% "
                  f"{r['n_challenges']:>4} {r['improved']:>4} {r['degraded']:>4} {verdict}")
    else:
        print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
