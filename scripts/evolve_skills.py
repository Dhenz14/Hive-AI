#!/usr/bin/env python3
"""
scripts/evolve_skills.py — ACE generate→reflect→curate cycle for SKILL.md files.

Identifies underperforming skills (lift < 2%), generates improved variants via
local LLM, evaluates each variant, and promotes the best if it beats current by >1%.

Requires llama-server running at http://localhost:11435.

Usage:
    python scripts/evolve_skills.py                          # Evolve all weak skills
    python scripts/evolve_skills.py --skill rust_async       # Target one skill
    python scripts/evolve_skills.py --dry-run                # Show what would change
    python scripts/evolve_skills.py --variants 5             # Generate 5 variants
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from skills.skill_loader import load_skill, list_available_skills

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:11435"
SKILLS_DIR = PROJECT_ROOT / "skills"
EVALS_DIR = PROJECT_ROOT / "evals"
CHALLENGES_PATH = PROJECT_ROOT / "scripts" / "eval_challenges.json"

TEMPERATURE_GENERATE = 0.7  # Creative for variant generation
TEMPERATURE_EVAL = 0.1      # Deterministic for evaluation
MAX_TOKENS_GENERATE = 2048
MAX_TOKENS_EVAL = 1024
TIMEOUT = 180
LIFT_THRESHOLD = 0.02       # Skills below 2% lift are candidates
IMPROVEMENT_THRESHOLD = 0.01  # Variant must beat current by >1%

log = logging.getLogger("evolve_skills")

# Skill → eval category mapping (imported concept from skill_lift.py)
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
    "hive_custom_json": ["hive_sdk", "hive_layer2"],
    "debugging_patterns": ["python", "algorithms"],
    "long_context":     [],
    "writing_skills":   [],
}


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_challenges() -> list[dict]:
    """Load eval challenges from JSON."""
    with open(CHALLENGES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_latest_eval() -> dict | None:
    """Load the most recent eval results file."""
    if not EVALS_DIR.exists():
        return None
    eval_files = sorted(EVALS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    # Filter out failure_analysis files
    eval_files = [f for f in eval_files if not f.name.startswith("failure_")]
    if not eval_files:
        return None
    path = eval_files[-1]
    log.info("Loading eval results from %s", path.name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_skill_meta(skill_name: str) -> dict:
    """Load skill_meta.json for a skill."""
    meta_path = SKILLS_DIR / skill_name / "skill_meta.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_skill_meta(skill_name: str, meta: dict):
    """Save skill_meta.json for a skill."""
    meta_path = SKILLS_DIR / skill_name / "skill_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# LLM Interaction
# ---------------------------------------------------------------------------

def chat_completion(messages: list[dict], temperature: float = 0.1,
                    max_tokens: int = 1024) -> str:
    """Send a chat completion to local llama-server."""
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": "hiveai",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Scoring (reuses skill_lift.py patterns)
# ---------------------------------------------------------------------------

def score_response(text: str, challenge: dict) -> dict:
    """Score a response against a challenge. Mirrors skill_lift.py logic."""
    concepts = challenge.get("expected_concepts", [])

    # Concept coverage
    if concepts:
        found = sum(1 for kw in concepts if kw.lower() in text.lower())
        concept_score = found / len(concepts)
    else:
        concept_score = 0.5

    # Code presence
    has_code = 1.0 if "```" in text else (0.5 if "`" in text else 0.0)

    # Explanation quality
    stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    word_count = len(stripped.split())
    explanation = min(word_count / 80, 1.0)

    # Weighted (no test execution for speed)
    overall = concept_score * 0.40 + has_code * 0.30 + explanation * 0.30
    return {
        "concept_coverage": round(concept_score, 3),
        "has_code": has_code,
        "explanation": round(explanation, 3),
        "overall": round(overall, 3),
    }


def measure_skill_score(skill_content: str, challenges: list[dict],
                        limit: int = 5) -> tuple[float, list[dict]]:
    """Measure average score for a skill variant against relevant challenges.

    Returns (avg_score, per_challenge_results).
    """
    system_prompt = (
        "You are HiveAI, an expert coding assistant.\n\n"
        "--- DOMAIN EXPERTISE (use as reference) ---\n\n"
        f"{skill_content}"
    )

    results = []
    for challenge in challenges[:limit]:
        try:
            resp = chat_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": challenge["instruction"]},
                ],
                temperature=TEMPERATURE_EVAL,
                max_tokens=MAX_TOKENS_EVAL,
            )
            sc = score_response(resp, challenge)
            results.append({"id": challenge["id"], "overall": sc["overall"],
                            "concept_coverage": sc["concept_coverage"]})
        except Exception as e:
            log.warning("Error scoring challenge %s: %s", challenge["id"], e)
            results.append({"id": challenge["id"], "overall": 0.0,
                            "concept_coverage": 0.0})

    avg = sum(r["overall"] for r in results) / max(len(results), 1)
    return round(avg, 4), results


# ---------------------------------------------------------------------------
# Variant Generation
# ---------------------------------------------------------------------------

VARIANT_PROMPT = """You are an expert at writing concise, high-impact domain expertise documents (SKILL.md files) that improve LLM coding performance.

## Current SKILL.md
```
{current_content}
```

## Current Performance
- Skill lift: {lift_pct:+.2f}% (target: >2%)
- Average score with skill: {avg_score:.3f}

## Failing Challenges (scored low)
{failing_challenges}

## Your Task
Generate an IMPROVED version of the SKILL.md that will score better on the failing challenges.

**Rules:**
1. Keep it 500-2000 tokens (concise, no fluff)
2. Add concrete code examples for the failing topics
3. Remove any patterns that don't help with the challenge categories
4. Use markdown formatting with headers, code blocks, and bullet points
5. Focus on actionable patterns, not theory
6. Include common pitfalls and their solutions
7. Every code example must be correct and complete

**Output ONLY the new SKILL.md content, nothing else. No wrapper, no explanation.**"""


def format_failing_challenges(challenges: list[dict], scores: list[dict]) -> str:
    """Format failing challenges for the variant generation prompt."""
    lines = []
    for ch, sc in zip(challenges, scores):
        if sc["overall"] < 0.7:  # Below 70% = failing
            concepts = ", ".join(ch.get("expected_concepts", [])[:8])
            lines.append(
                f"- [{ch['id']}] {ch['instruction'][:120]}...\n"
                f"  Score: {sc['overall']:.3f} | Expected: {concepts}"
            )
    if not lines:
        # If nothing below 0.7, show lowest scorers
        paired = sorted(zip(challenges, scores), key=lambda x: x[1]["overall"])
        for ch, sc in paired[:3]:
            concepts = ", ".join(ch.get("expected_concepts", [])[:8])
            lines.append(
                f"- [{ch['id']}] {ch['instruction'][:120]}...\n"
                f"  Score: {sc['overall']:.3f} | Expected: {concepts}"
            )
    return "\n".join(lines) if lines else "(no specific failures identified)"


def generate_variants(skill_name: str, current_content: str,
                      challenges: list[dict], current_scores: list[dict],
                      avg_score: float, lift_pct: float,
                      n_variants: int = 3) -> list[str]:
    """Generate N improved SKILL.md variants via LLM."""
    failing_text = format_failing_challenges(challenges, current_scores)

    prompt = VARIANT_PROMPT.format(
        current_content=current_content,
        lift_pct=lift_pct,
        avg_score=avg_score,
        failing_challenges=failing_text,
    )

    variants = []
    for i in range(n_variants):
        log.info("  Generating variant %d/%d for %s...", i + 1, n_variants, skill_name)
        try:
            variant = chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=TEMPERATURE_GENERATE,
                max_tokens=MAX_TOKENS_GENERATE,
            )
            # Strip markdown wrapper if LLM added one
            variant = variant.strip()
            if variant.startswith("```markdown"):
                variant = variant[len("```markdown"):].strip()
            if variant.startswith("```"):
                variant = variant[3:].strip()
            if variant.endswith("```"):
                variant = variant[:-3].strip()

            # Basic quality check
            if len(variant) < 200:
                log.warning("  Variant %d too short (%d chars), skipping", i + 1, len(variant))
                continue
            if len(variant) > 8000:
                variant = variant[:8000]
                log.warning("  Variant %d truncated to 8000 chars", i + 1)

            variants.append(variant)
        except Exception as e:
            log.error("  Failed to generate variant %d: %s", i + 1, e)

    return variants


# ---------------------------------------------------------------------------
# Evolution Logic
# ---------------------------------------------------------------------------

def get_relevant_challenges(skill_name: str, all_challenges: list[dict]) -> list[dict]:
    """Get eval challenges relevant to a skill."""
    categories = SKILL_CATEGORY_MAP.get(skill_name, [])
    if not categories:
        return []
    return [c for c in all_challenges if c.get("category") in categories]


def evolve_skill(skill_name: str, all_challenges: list[dict],
                 n_variants: int = 3, dry_run: bool = False,
                 eval_limit: int = 5) -> dict:
    """Run the generate→reflect→curate cycle for one skill."""
    log.info("Evolving skill: %s", skill_name)

    # Load current skill
    current_content = load_skill(skill_name)
    if not current_content:
        return {"skill": skill_name, "status": "error", "reason": "SKILL.md not found"}

    # Get relevant challenges
    challenges = get_relevant_challenges(skill_name, all_challenges)
    if not challenges:
        return {"skill": skill_name, "status": "skip",
                "reason": "no mapped eval categories"}

    challenges = challenges[:eval_limit]

    # Score current skill
    log.info("  Scoring current SKILL.md (%d challenges)...", len(challenges))
    current_avg, current_scores = measure_skill_score(
        current_content, challenges, limit=eval_limit
    )
    log.info("  Current score: %.4f", current_avg)

    # Measure baseline (no skill)
    log.info("  Scoring baseline (no skill)...")
    baseline_avg, _ = measure_skill_score("", challenges, limit=eval_limit)
    lift = current_avg - baseline_avg
    lift_pct = lift * 100
    log.info("  Baseline: %.4f, Lift: %+.2f%%", baseline_avg, lift_pct)

    # Check if skill needs evolution
    if lift >= LIFT_THRESHOLD:
        log.info("  Skill lift %.2f%% >= threshold %.2f%%, no evolution needed",
                 lift_pct, LIFT_THRESHOLD * 100)
        return {"skill": skill_name, "status": "ok", "lift_pct": round(lift_pct, 2),
                "current_score": current_avg, "reason": "lift above threshold"}

    log.info("  Skill underperforming (lift=%.2f%%), generating variants...", lift_pct)

    if dry_run:
        return {"skill": skill_name, "status": "dry_run",
                "lift_pct": round(lift_pct, 2), "current_score": current_avg,
                "would_generate": n_variants}

    # Generate variants
    variants = generate_variants(
        skill_name, current_content, challenges, current_scores,
        current_avg, lift_pct, n_variants
    )
    if not variants:
        return {"skill": skill_name, "status": "error",
                "reason": "failed to generate any variants"}

    # Evaluate each variant
    best_variant = None
    best_score = current_avg
    variant_results = []

    for i, variant_content in enumerate(variants):
        log.info("  Evaluating variant %d/%d...", i + 1, len(variants))
        v_avg, v_scores = measure_skill_score(
            variant_content, challenges, limit=eval_limit
        )
        v_lift = v_avg - baseline_avg
        improvement = v_avg - current_avg
        log.info("    Score: %.4f (lift: %+.2f%%, vs current: %+.4f)",
                 v_avg, v_lift * 100, improvement)

        variant_results.append({
            "variant": i + 1,
            "score": v_avg,
            "lift_pct": round(v_lift * 100, 2),
            "improvement": round(improvement, 4),
        })

        if v_avg > best_score + IMPROVEMENT_THRESHOLD:
            best_score = v_avg
            best_variant = (i, variant_content)

    result = {
        "skill": skill_name,
        "current_score": current_avg,
        "baseline": baseline_avg,
        "lift_pct": round(lift_pct, 2),
        "variants_generated": len(variants),
        "variant_results": variant_results,
    }

    # Promote best variant if it improves
    if best_variant is not None:
        idx, content = best_variant
        improvement = best_score - current_avg

        log.info("  Promoting variant %d (score %.4f, +%.4f improvement)",
                 idx + 1, best_score, improvement)

        # Save audit trail
        skill_dir = SKILLS_DIR / skill_name
        version = _next_version(skill_dir)
        variant_path = skill_dir / f"SKILL_v{version}.md"
        variant_path.write_text(content, encoding="utf-8")
        log.info("  Saved variant as %s", variant_path.name)

        # Backup current
        backup_path = skill_dir / f"SKILL_v{version - 1}.md"
        if not backup_path.exists():
            backup_path.write_text(current_content, encoding="utf-8")

        # Promote
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content, encoding="utf-8")
        log.info("  Promoted to SKILL.md")

        # Update meta
        meta = load_skill_meta(skill_name)
        if "evolution_history" not in meta:
            meta["evolution_history"] = []
        meta["evolution_history"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": version,
            "previous_score": current_avg,
            "new_score": best_score,
            "improvement": round(improvement, 4),
            "lift_pct": round((best_score - baseline_avg) * 100, 2),
            "variants_tested": len(variants),
            "winning_variant": idx + 1,
        })
        save_skill_meta(skill_name, meta)

        result["status"] = "evolved"
        result["new_score"] = best_score
        result["improvement"] = round(improvement, 4)
        result["version"] = version
    else:
        log.info("  No variant beat current by >%.0f%%, keeping current SKILL.md",
                 IMPROVEMENT_THRESHOLD * 100)
        result["status"] = "no_improvement"

    return result


def _next_version(skill_dir: Path) -> int:
    """Find the next version number for SKILL_v{n}.md files."""
    existing = list(skill_dir.glob("SKILL_v*.md"))
    if not existing:
        return 1
    versions = []
    for p in existing:
        m = re.search(r"SKILL_v(\d+)\.md", p.name)
        if m:
            versions.append(int(m.group(1)))
    return max(versions, default=0) + 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ACE generate/reflect/curate cycle for SKILL.md evolution")
    parser.add_argument("--skill", type=str, default=None,
                        help="Target a specific skill (e.g. 'rust_async')")
    parser.add_argument("--variants", type=int, default=3,
                        help="Number of variants to generate per skill (default: 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without modifying files")
    parser.add_argument("--eval-dir", type=str, default="evals/",
                        help="Directory for eval results (default: evals/)")
    parser.add_argument("--eval-limit", type=int, default=5,
                        help="Max challenges per skill for scoring (default: 5)")
    parser.add_argument("--base-url", type=str, default=BASE_URL,
                        help=f"llama-server URL (default: {BASE_URL})")
    parser.add_argument("--force", action="store_true",
                        help="Evolve even if lift is above threshold")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    global BASE_URL, EVALS_DIR
    BASE_URL = args.base_url
    eval_path = Path(args.eval_dir)
    if eval_path.is_absolute():
        EVALS_DIR = eval_path
    else:
        EVALS_DIR = PROJECT_ROOT / eval_path

    # Connectivity check
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
    except requests.ConnectionError:
        log.error("Cannot reach llama-server at %s", BASE_URL)
        sys.exit(1)

    # Load data
    challenges = load_challenges()
    available = {s["name"] for s in list_available_skills()}

    # Determine skills to evolve
    if args.skill:
        if args.skill not in available:
            log.error("Skill '%s' not found. Available: %s",
                      args.skill, sorted(available))
            sys.exit(1)
        skills_to_evolve = [args.skill]
    else:
        skills_to_evolve = [
            name for name in SKILL_CATEGORY_MAP
            if name in available and SKILL_CATEGORY_MAP[name]
        ]

    log.info("Evolving %d skill(s), %d variants each, %d challenges/skill",
             len(skills_to_evolve), args.variants, args.eval_limit)
    if args.dry_run:
        log.info("DRY RUN — no files will be modified")

    # If --force, temporarily set threshold impossibly high
    original_threshold = None
    if args.force:
        global LIFT_THRESHOLD
        original_threshold = LIFT_THRESHOLD
        LIFT_THRESHOLD = 999.0  # Force all skills to be "underperforming"

    all_results = []
    for skill_name in sorted(skills_to_evolve):
        log.info("")
        log.info("=" * 60)
        log.info("  %s", skill_name)
        log.info("=" * 60)

        result = evolve_skill(
            skill_name, challenges,
            n_variants=args.variants,
            dry_run=args.dry_run,
            eval_limit=args.eval_limit,
        )
        all_results.append(result)

    # Restore threshold
    if original_threshold is not None:
        LIFT_THRESHOLD = original_threshold

    # Summary
    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        print(f"\n{'=' * 70}")
        print("  SKILL EVOLUTION SUMMARY")
        print(f"{'=' * 70}")
        print(f"{'Skill':<22} {'Status':<15} {'Lift':>7} {'Score':>7} {'Improv':>7}")
        print("-" * 70)

        for r in all_results:
            status = r.get("status", "?")
            lift = f"{r.get('lift_pct', 0):+.2f}%" if "lift_pct" in r else "—"
            score = f"{r.get('current_score', 0):.4f}" if "current_score" in r else "—"
            improv = (f"{r.get('improvement', 0):+.4f}"
                      if r.get("improvement") else "—")
            print(f"{r['skill']:<22} {status:<15} {lift:>7} {score:>7} {improv:>7}")

        evolved = [r for r in all_results if r.get("status") == "evolved"]
        if evolved:
            print(f"\nEvolved {len(evolved)} skill(s):")
            for r in evolved:
                print(f"  - {r['skill']}: {r['current_score']:.4f} -> "
                      f"{r['new_score']:.4f} (+{r['improvement']:.4f})")


if __name__ == "__main__":
    main()
