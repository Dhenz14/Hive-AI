"""
scripts/run_eval.py

Evaluation harness for HiveAI models.

Sends coding challenges to an Ollama model, scores responses on 4 dimensions,
and produces a detailed JSON report. Supports comparison between runs.

Usage:
    python scripts/run_eval.py --model qwen3:14b                     # Full eval
    python scripts/run_eval.py --model qwen3:14b --limit 10          # Quick test
    python scripts/run_eval.py --model qwen3:14b --category python   # Single category
    python scripts/run_eval.py --compare evals/base.json evals/lora.json
    python scripts/run_eval.py --dry-run                              # List challenges
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path so we can import hiveai modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHALLENGES_PATH = Path(__file__).parent / "eval_challenges.json"
EVALS_DIR = PROJECT_ROOT / "evals"
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 600  # 10 min per challenge (generous for slow models)
SANDBOX_TIMEOUT = 30   # 30s for code execution

# Scoring weights
W_CODE_VALIDITY = 0.30
W_TEST_PASSING = 0.30
W_CONCEPT_COVERAGE = 0.20
W_EXPLANATION = 0.20


# ---------------------------------------------------------------------------
# Module-level call function — swapped at startup if --base-url is given
_LLAMA_SERVER_URL: str | None = None  # set to e.g. "http://localhost:11435" for llama-server


def _call_model(prompt: str, model: str, max_tokens: int = 4096,
                temperature: float = 0.3, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Route to Ollama or llama-server depending on --base-url."""
    if _LLAMA_SERVER_URL:
        return call_llama_server(prompt, model, max_tokens, temperature, timeout)
    return call_ollama(prompt, model, max_tokens, temperature, timeout)


# Ollama API — native /api/chat (same pattern as brain_mine._make_fast_call)
# ---------------------------------------------------------------------------
def call_ollama(prompt: str, model: str, max_tokens: int = 4096,
                temperature: float = 0.3, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Call Ollama's native /api/chat endpoint.

    Returns: {content, tokens_eval, duration_ms, error}
    """
    import requests

    from hiveai.config import OLLAMA_BASE_URL
    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": CODING_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.time() - t0) * 1000)

            content = data.get("message", {}).get("content", "")
            # Strip residual think blocks from reasoning models
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            content = content.strip()

            return {
                "content": content,
                "tokens_eval": data.get("eval_count", 0),
                "duration_ms": elapsed_ms,
                "error": None,
            }
        except Exception as e:
            last_err = str(e)
            wait = 10 * (attempt + 1)
            logger.warning(f"Ollama call attempt {attempt+1}/{MAX_RETRIES} failed: {e} — retry in {wait}s")
            time.sleep(wait)

    return {"content": "", "tokens_eval": 0, "duration_ms": 0, "error": last_err}


# llama-server OpenAI-compatible endpoint
# ---------------------------------------------------------------------------
def call_llama_server(prompt: str, model: str, max_tokens: int = 4096,
                      temperature: float = 0.3, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Call llama-server's /v1/chat/completions (OpenAI-compatible).
    Used when --base-url is given (e.g. http://localhost:11435).
    """
    import requests

    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    base = _LLAMA_SERVER_URL.rstrip("/")
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp = requests.post(
                f"{base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": CODING_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed_ms = int((time.time() - t0) * 1000)

            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            # reasoning_content is the thinking block (separate field in llama-server)
            reasoning = msg.get("reasoning_content", "")

            # Strip inline think tags if the model embedded them in content
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            content = content.strip()

            # full_for_explain: reasoning block + visible content — used only for
            # explanation scoring so the scorer sees the model's actual reasoning depth.
            full_for_explain = ((reasoning + "\n\n" + content).strip()
                                if reasoning else content)

            usage = data.get("usage", {})
            return {
                "content": content,
                "full_for_explain": full_for_explain,
                "tokens_eval": usage.get("completion_tokens", 0),
                "duration_ms": elapsed_ms,
                "error": None,
            }
        except Exception as e:
            last_err = str(e)
            wait = 10 * (attempt + 1)
            logger.warning(f"llama-server attempt {attempt+1}/{MAX_RETRIES} failed: {e} — retry in {wait}s")
            time.sleep(wait)

    return {"content": "", "tokens_eval": 0, "duration_ms": 0, "error": last_err}


# ---------------------------------------------------------------------------
# Scoring — 4 dimensions
# ---------------------------------------------------------------------------
def score_code_validity(response: str) -> float:
    """
    Dimension 1: Code validity (0.0-1.0).
    v2: Actually EXECUTES code, not just syntax checking.

    Scoring:
      - 0.0: No code blocks
      - 0.1-0.3: Inline code keywords only
      - 0.4: Code blocks with valid syntax but execution fails
      - 0.6: Some blocks execute successfully
      - 0.8: Most blocks execute successfully
      - 1.0: All blocks execute without errors
    """
    from hiveai.sandbox import extract_code_blocks, validate_syntax, execute_python

    blocks = extract_code_blocks(response)
    if not blocks:
        code_indicators = ["def ", "class ", "import ", "return ", "for ", "while "]
        hits = sum(1 for k in code_indicators if k in response)
        return min(hits * 0.1, 0.3)

    syntax_valid = 0
    exec_passed = 0
    exec_attempted = 0

    for block in blocks:
        syn = validate_syntax(block["code"])
        if syn["valid"]:
            syntax_valid += 1
            # Actually execute the code (with tight timeout for eval speed)
            result = execute_python(block["code"], timeout=10)
            exec_attempted += 1
            if result["success"]:
                exec_passed += 1

    total = len(blocks)

    if exec_attempted == 0:
        # All blocks had syntax errors
        return 0.2 * (syntax_valid / total) if total > 0 else 0.0

    # Blend syntax and execution scores:
    # - Syntax validity is the floor (0.4 max)
    # - Execution success raises it to 1.0
    syntax_score = syntax_valid / total  # 0.0-1.0
    exec_score = exec_passed / exec_attempted  # 0.0-1.0

    # Weighted: 30% syntax + 70% execution (execution is what matters)
    blended = 0.3 * syntax_score + 0.7 * exec_score
    return round(blended, 3)


def score_test_passing(response: str, test_code: str | None) -> float | None:
    """
    Dimension 2: Test passing (0.0-1.0).
    Returns None if no test_code (weight redistributed to other dimensions).
    """
    if not test_code:
        return None

    from hiveai.sandbox import run_test_code

    result = run_test_code(test_code, response, timeout=SANDBOX_TIMEOUT)

    if result["tests_passed"]:
        return 1.0

    # Partial credit: code ran but tests failed (not a crash)
    exec_result = result["execution"]
    if exec_result["success"]:
        # Code ran without error but didn't print ALL TESTS PASSED
        return 0.3
    if exec_result["error_type"] == "AssertionError" or "AssertionError" in exec_result.get("stderr", ""):
        return 0.2  # At least the code structure was right
    if exec_result["error_type"] == "AssertionError":
        return 0.2
    if not exec_result["timed_out"] and exec_result["return_code"] != -1:
        return 0.1  # Ran but errored

    return 0.0


def score_concept_coverage(response: str, expected_concepts: list[str]) -> float:
    """
    Dimension 3: Concept coverage (0.0-1.0).
    Fraction of expected_concepts found in the response using word-boundary matching.
    Trivial Python keywords that appear in any response are filtered out.
    """
    import re as _re

    if not expected_concepts:
        return 0.5  # No concepts to check — neutral score

    # Filter out trivial keywords that match in virtually any Python response
    trivial = {"def", "return", "for", "if", "else", "class", "import", "from",
               "in", "is", "not", "and", "or", "with", "as", "try", "except",
               "True", "False", "None", "self", "print", "int", "str", "list"}
    meaningful = [c for c in expected_concepts if c.lower() not in trivial]

    if not meaningful:
        return 0.5  # All concepts were trivial — neutral

    response_lower = response.lower()
    hits = 0
    for concept in meaningful:
        c_lower = concept.lower()
        # Use word-boundary matching for short concepts (<=8 chars), substring for longer
        if len(c_lower) <= 8:
            if _re.search(r'\b' + _re.escape(c_lower) + r'\b', response_lower):
                hits += 1
        else:
            if c_lower in response_lower:
                hits += 1
    return hits / len(meaningful)


def score_explanation_quality(response: str) -> float:
    """
    Dimension 4: Explanation quality (0.0-1.0).
    Measures reasoning depth, structure, and teaching signals.
    Adapted from distiller._score_quality markers.
    """
    if not response:
        return 0.0

    response_lower = response.lower()
    word_count = len(response.split())
    score = 0.0

    # --- Content depth (0.25 max) ---
    if word_count >= 800:
        score += 0.25
    elif word_count >= 500:
        score += 0.20
    elif word_count >= 300:
        score += 0.15
    elif word_count >= 150:
        score += 0.10
    elif word_count >= 50:
        score += 0.05

    # --- Reasoning markers (0.30 max) ---
    causal = ["because", "therefore", "consequently", "as a result",
              "this means", "which leads to", "the reason", "due to", "hence"]
    nuance = ["however", "although", "on the other hand", "trade-off",
              "alternatively", "edge case", "caveat", "unless"]
    teaching = ["for example", "common mistake", "best practice",
                "note that", "important", "consider", "step 1", "first,"]

    causal_hits = sum(1 for m in causal if m in response_lower)
    nuance_hits = sum(1 for m in nuance if m in response_lower)
    teaching_hits = sum(1 for m in teaching if m in response_lower)

    reasoning = 0.0
    reasoning += min(causal_hits * 0.03, 0.12)
    reasoning += min(nuance_hits * 0.025, 0.08)
    reasoning += min(teaching_hits * 0.025, 0.10)
    score += min(reasoning, 0.30)

    # --- Structure (0.20 max) ---
    headers = re.findall(r"^#{1,3}\s+\w", response, re.MULTILINE)
    list_items = re.findall(r"^[\s]*(?:[-*]|\d+\.)\s+", response, re.MULTILINE)
    code_blocks = len(re.findall(r"```", response)) // 2
    # Inline comments and docstrings — the coding AI's native explanation form
    inline_comments = re.findall(r"#\s+\w{3,}", response)
    docstrings = re.findall(r'""".*?"""', response, re.DOTALL)

    structure = 0.0
    if len(headers) >= 3:
        structure += 0.06
    elif len(headers) >= 1:
        structure += 0.03
    if len(list_items) >= 3:
        structure += 0.05
    elif len(list_items) >= 1:
        structure += 0.02
    if code_blocks >= 2:
        structure += 0.05
    elif code_blocks >= 1:
        structure += 0.03
    # Inline comments reward (up to 0.04)
    structure += min(len(inline_comments) * 0.01, 0.04)
    # Docstrings reward (up to 0.03)
    structure += min(len(docstrings) * 0.015, 0.03)
    # Bold terms
    bold = re.findall(r"\*\*[^*]{2,30}\*\*", response)
    if len(bold) >= 2:
        structure += 0.04
    score += min(structure, 0.20)

    # --- Penalties (up to -0.25) ---
    penalties = 0.0
    if word_count < 50:
        penalties += 0.20
    elif word_count < 100:
        penalties += 0.10

    # Repetitive content
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', response) if len(s.strip()) > 20]
    if len(sentences) >= 3:
        unique_ratio = len(set(s.lower()[:50] for s in sentences)) / len(sentences)
        if unique_ratio < 0.7:
            penalties += 0.15

    final = max(0.0, score - penalties)
    return round(min(final, 1.0), 3)


def compute_weighted_score(code_validity: float, test_passing: float | None,
                           concept_coverage: float, explanation: float) -> float:
    """
    Compute overall score from 4 dimensions.
    If test_passing is None (no test_code), redistribute its weight.
    """
    if test_passing is not None:
        return round(
            W_CODE_VALIDITY * code_validity +
            W_TEST_PASSING * test_passing +
            W_CONCEPT_COVERAGE * concept_coverage +
            W_EXPLANATION * explanation,
            3
        )
    else:
        # Redistribute test weight: 60% to code_validity, 40% to concept_coverage
        w_code = W_CODE_VALIDITY + W_TEST_PASSING * 0.6
        w_concept = W_CONCEPT_COVERAGE + W_TEST_PASSING * 0.4
        return round(
            w_code * code_validity +
            w_concept * concept_coverage +
            W_EXPLANATION * explanation,
            3
        )


# ---------------------------------------------------------------------------
# Challenge runner
# ---------------------------------------------------------------------------
def load_challenges(path: Path = CHALLENGES_PATH) -> list[dict]:
    """Load challenges from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_challenge(challenge: dict, model: str) -> dict:
    """
    Evaluate a single challenge:
    1. Send instruction to model
    2. Score response on 4 dimensions
    3. Return detailed result
    """
    cid = challenge["id"]
    logger.info(f"  [{cid}] {challenge['topic']} (D{challenge['difficulty']})...")

    # Call the model
    result = _call_model(challenge["instruction"], model)

    if result["error"]:
        logger.error(f"  [{cid}] FAILED: {result['error']}")
        return {
            "id": cid,
            "category": challenge["category"],
            "topic": challenge["topic"],
            "difficulty": challenge["difficulty"],
            "error": result["error"],
            "scores": {"code_validity": 0, "test_passing": 0, "concept_coverage": 0,
                       "explanation": 0, "overall": 0},
            "duration_ms": result["duration_ms"],
            "response_preview": "",
        }

    response = result["content"]
    # For explanation scoring: use reasoning_content + content so the scorer
    # sees the model's full thinking depth, not just the thin post-think answer.
    response_for_explain = result.get("full_for_explain", response)
    test_code = challenge.get("test_code")

    # Score all 4 dimensions
    d1_code = score_code_validity(response)
    d2_test = score_test_passing(response, test_code)
    d3_concept = score_concept_coverage(response, challenge.get("expected_concepts", []))
    d4_explain = score_explanation_quality(response_for_explain)
    overall = compute_weighted_score(d1_code, d2_test, d3_concept, d4_explain)

    status = "PASS" if overall >= 0.6 else "MARGINAL" if overall >= 0.4 else "FAIL"
    test_str = f"{d2_test:.2f}" if d2_test is not None else "N/A"
    logger.info(
        f"  [{cid}] {status} — overall={overall:.2f} "
        f"(code={d1_code:.2f} test={test_str} concept={d3_concept:.2f} explain={d4_explain:.2f}) "
        f"[{result['duration_ms']}ms]"
    )

    return {
        "id": cid,
        "category": challenge["category"],
        "topic": challenge["topic"],
        "difficulty": challenge["difficulty"],
        "scores": {
            "code_validity": round(d1_code, 3),
            "test_passing": round(d2_test, 3) if d2_test is not None else None,
            "concept_coverage": round(d3_concept, 3),
            "explanation": round(d4_explain, 3),
            "overall": overall,
        },
        "has_test_code": test_code is not None,
        "duration_ms": result["duration_ms"],
        "tokens_eval": result["tokens_eval"],
        "response_preview": response[:300],
        "error": None,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(results: list[dict], model: str, elapsed_total_s: float) -> dict:
    """Generate aggregate report from individual challenge results."""
    total = len(results)
    errors = sum(1 for r in results if r["error"])
    scored = [r for r in results if not r["error"]]

    # Overall
    if scored:
        overall_score = sum(r["scores"]["overall"] for r in scored) / len(scored)
    else:
        overall_score = 0.0

    # Dimension averages
    dim_scores = {}
    for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
        vals = [r["scores"][dim] for r in scored if r["scores"][dim] is not None]
        dim_scores[dim] = round(sum(vals) / max(len(vals), 1), 3)

    # By category
    by_category = {}
    for r in scored:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"scores": [], "test_results": []}
        by_category[cat]["scores"].append(r["scores"]["overall"])
        if r["scores"]["test_passing"] is not None:
            by_category[cat]["test_results"].append(r["scores"]["test_passing"])

    for cat, data in by_category.items():
        avg = sum(data["scores"]) / len(data["scores"])
        test_pass_rate = (sum(1 for t in data["test_results"] if t >= 1.0) /
                          max(len(data["test_results"]), 1))
        by_category[cat] = {
            "score": round(avg, 3),
            "count": len(data["scores"]),
            "test_pass_rate": round(test_pass_rate, 3),
            "tests_total": len(data["test_results"]),
        }

    # By difficulty
    by_difficulty = {}
    for r in scored:
        d = str(r["difficulty"])
        if d not in by_difficulty:
            by_difficulty[d] = {"scores": []}
        by_difficulty[d]["scores"].append(r["scores"]["overall"])

    for d, data in by_difficulty.items():
        by_difficulty[d] = {
            "score": round(sum(data["scores"]) / len(data["scores"]), 3),
            "count": len(data["scores"]),
        }

    # Timing
    total_tokens = sum(r.get("tokens_eval", 0) for r in scored)
    total_ms = sum(r["duration_ms"] for r in scored)
    avg_ms = total_ms // max(len(scored), 1)

    return {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "total_challenges": total,
        "errors": errors,
        "scored": len(scored),
        "overall_score": round(overall_score, 3),
        "dimension_scores": dim_scores,
        "by_category": dict(sorted(by_category.items())),
        "by_difficulty": dict(sorted(by_difficulty.items())),
        "timing": {
            "total_seconds": round(elapsed_total_s, 1),
            "avg_ms_per_challenge": avg_ms,
            "total_tokens": total_tokens,
        },
        "challenges": results,
    }


def save_report(report: dict) -> Path:
    """Save report to evals/ directory."""
    EVALS_DIR.mkdir(exist_ok=True)
    model_safe = report["model"].replace(":", "-").replace("/", "-")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EVALS_DIR / f"{model_safe}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def compare_reports(path_a: str, path_b: str):
    """Compare two eval reports and print a summary."""
    with open(path_a, "r") as f:
        a = json.load(f)
    with open(path_b, "r") as f:
        b = json.load(f)

    print(f"\n{'='*70}")
    print(f"  EVAL COMPARISON")
    print(f"{'='*70}")
    print(f"  Model A: {a['model']}  ({a['timestamp'][:10]})")
    print(f"  Model B: {b['model']}  ({b['timestamp'][:10]})")
    print(f"{'='*70}")

    # Overall
    delta = b["overall_score"] - a["overall_score"]
    arrow = "+" if delta > 0 else "-" if delta < 0 else "="
    print(f"\n  Overall Score:  {a['overall_score']:.3f}  ->  {b['overall_score']:.3f}  ({arrow} {abs(delta):.3f})")

    # Dimensions
    print(f"\n  Dimension Scores:")
    for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
        va = a["dimension_scores"].get(dim, 0)
        vb = b["dimension_scores"].get(dim, 0)
        d = vb - va
        arr = "+" if d > 0 else "-" if d < 0 else "="
        print(f"    {dim:20s}  {va:.3f}  ->  {vb:.3f}  ({arr} {abs(d):.3f})")

    # By category
    print(f"\n  By Category:")
    all_cats = sorted(set(list(a.get("by_category", {}).keys()) + list(b.get("by_category", {}).keys())))
    for cat in all_cats:
        sa = a.get("by_category", {}).get(cat, {}).get("score", 0)
        sb = b.get("by_category", {}).get(cat, {}).get("score", 0)
        d = sb - sa
        arr = "+" if d > 0 else "-" if d < 0 else "="
        print(f"    {cat:20s}  {sa:.3f}  ->  {sb:.3f}  ({arr} {abs(d):.3f})")

    # By difficulty
    print(f"\n  By Difficulty:")
    for d_level in ["1", "2", "3", "4", "5"]:
        sa = a.get("by_difficulty", {}).get(d_level, {}).get("score", 0)
        sb = b.get("by_difficulty", {}).get(d_level, {}).get("score", 0)
        d = sb - sa
        arr = "+" if d > 0 else "-" if d < 0 else "="
        print(f"    D{d_level}:               {sa:.3f}  ->  {sb:.3f}  ({arr} {abs(d):.3f})")

    # Timing
    print(f"\n  Timing:")
    ta = a.get("timing", {}).get("avg_ms_per_challenge", 0)
    tb = b.get("timing", {}).get("avg_ms_per_challenge", 0)
    print(f"    Avg ms/challenge: {ta}  ->  {tb}")
    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def print_summary(report: dict):
    """Print a human-readable summary of the eval report."""
    print(f"\n{'='*70}")
    print(f"  EVALUATION REPORT — {report['model']}")
    print(f"{'='*70}")
    print(f"  Challenges: {report['scored']}/{report['total_challenges']} scored ({report['errors']} errors)")
    print(f"  Overall Score: {report['overall_score']:.3f}")
    print(f"  Time: {report['timing']['total_seconds']:.0f}s ({report['timing']['avg_ms_per_challenge']}ms avg)")
    print(f"  Tokens: {report['timing']['total_tokens']:,}")

    print(f"\n  Dimension Scores:")
    for dim, val in report["dimension_scores"].items():
        filled = int(val * 20)
        bar = "#" * filled + "." * (20 - filled)
        print(f"    {dim:20s}  [{bar}]  {val:.3f}")

    print(f"\n  By Category:")
    for cat, data in report["by_category"].items():
        filled = int(data["score"] * 20)
        bar = "#" * filled + "." * (20 - filled)
        test_info = f"  tests: {data['test_pass_rate']:.0%} ({data['tests_total']})" if data["tests_total"] else ""
        print(f"    {cat:20s}  [{bar}]  {data['score']:.3f}  (n={data['count']}){test_info}")

    print(f"\n  By Difficulty:")
    for d_level, data in report["by_difficulty"].items():
        filled = int(data["score"] * 20)
        bar = "#" * filled + "." * (20 - filled)
        print(f"    D{d_level}:               [{bar}]  {data['score']:.3f}  (n={data['count']})")

    # Top failures
    challenges = report.get("challenges", [])
    failures = sorted(
        [c for c in challenges if not c["error"] and c["scores"]["overall"] < 0.4],
        key=lambda c: c["scores"]["overall"]
    )
    if failures:
        print(f"\n  Worst Performers (score < 0.4):")
        for f in failures[:10]:
            print(f"    {f['id']:20s}  {f['scores']['overall']:.3f}  ({f['topic']})")

    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="HiveAI Evaluation Harness")
    parser.add_argument("--model", type=str, help="Ollama model name (e.g. qwen3:14b)")
    parser.add_argument("--limit", type=int, default=0, help="Max challenges to run (0=all)")
    parser.add_argument("--category", type=str, help="Filter by category")
    parser.add_argument("--difficulty", type=int, help="Filter by difficulty level (1-5)")
    parser.add_argument("--compare", nargs=2, metavar=("REPORT_A", "REPORT_B"),
                        help="Compare two eval reports")
    parser.add_argument("--dry-run", action="store_true", help="List challenges without running")
    parser.add_argument("--temperature", type=float, default=0.3, help="LLM temperature")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens per response")
    parser.add_argument("--base-url", type=str, default=None,
                        help="Use llama-server instead of Ollama (e.g. http://localhost:11435)")
    args = parser.parse_args()

    # --- Wire llama-server URL if given ---
    global _LLAMA_SERVER_URL
    if args.base_url:
        _LLAMA_SERVER_URL = args.base_url
        logger.info(f"Using llama-server at {_LLAMA_SERVER_URL}")

    # --- Compare mode ---
    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    # --- Load challenges ---
    challenges = load_challenges()
    logger.info(f"Loaded {len(challenges)} challenges from {CHALLENGES_PATH}")

    # --- Filters ---
    if args.category:
        challenges = [c for c in challenges if c["category"] == args.category]
        logger.info(f"Filtered to category '{args.category}': {len(challenges)} challenges")

    if args.difficulty:
        challenges = [c for c in challenges if c["difficulty"] == args.difficulty]
        logger.info(f"Filtered to difficulty {args.difficulty}: {len(challenges)} challenges")

    if args.limit > 0:
        challenges = challenges[:args.limit]
        logger.info(f"Limited to {len(challenges)} challenges")

    if not challenges:
        logger.error("No challenges matched your filters.")
        return

    # --- Dry run ---
    if args.dry_run:
        print(f"\n{'='*70}")
        print(f"  {len(challenges)} CHALLENGES")
        print(f"{'='*70}")

        # Category summary
        cats = {}
        diffs = {}
        for c in challenges:
            cats[c["category"]] = cats.get(c["category"], 0) + 1
            diffs[c["difficulty"]] = diffs.get(c["difficulty"], 0) + 1

        print(f"\n  Categories: {dict(sorted(cats.items()))}")
        print(f"  Difficulties: {dict(sorted(diffs.items()))}")
        test_count = sum(1 for c in challenges if c.get("test_code"))
        print(f"  With test_code: {test_count}/{len(challenges)}")

        print(f"\n  {'ID':<22} {'Category':<18} {'Topic':<25} {'D':>2} {'Test':>5}")
        print(f"  {'-'*22} {'-'*18} {'-'*25} {'-':>2} {'-'*5}")
        for c in challenges:
            has_test = "yes" if c.get("test_code") else "—"
            print(f"  {c['id']:<22} {c['category']:<18} {c['topic']:<25} {c['difficulty']:>2} {has_test:>5}")
        print()
        return

    # --- Model required for actual eval ---
    if not args.model:
        # Default to fast model from config
        try:
            from hiveai.config import OLLAMA_MODEL_FAST
            args.model = OLLAMA_MODEL_FAST
            logger.info(f"No --model specified, using OLLAMA_MODEL_FAST: {args.model}")
        except ImportError:
            logger.error("--model is required (or set OLLAMA_MODEL_FAST in .env)")
            return

    # --- Verify model is reachable ---
    endpoint = _LLAMA_SERVER_URL or "Ollama"
    logger.info(f"Testing connection to {endpoint} with model {args.model}...")
    test = _call_model("Say 'ready' in one word.", args.model, max_tokens=32, timeout=120)
    if test["error"]:
        logger.error(f"Cannot reach {endpoint}: {test['error']}")
        logger.error("Make sure the server is running and the model is available.")
        return
    logger.info(f"{endpoint} ready ({test['duration_ms']}ms)")

    # --- Run eval ---
    logger.info(f"\n{'='*70}")
    logger.info(f"  STARTING EVAL: {args.model} — {len(challenges)} challenges")
    logger.info(f"{'='*70}")

    t_start = time.time()
    results = []

    for i, challenge in enumerate(challenges, 1):
        logger.info(f"\n[{i}/{len(challenges)}] {challenge['id']}")
        result = evaluate_challenge(challenge, args.model)
        results.append(result)

        # Progress summary every 10 challenges
        if i % 10 == 0:
            scored_so_far = [r for r in results if not r["error"]]
            if scored_so_far:
                avg = sum(r["scores"]["overall"] for r in scored_so_far) / len(scored_so_far)
                elapsed = time.time() - t_start
                eta = (elapsed / i) * (len(challenges) - i)
                logger.info(f"\n  --- Progress: {i}/{len(challenges)} | avg_score={avg:.3f} | "
                           f"ETA {eta/60:.1f}min ---\n")

    elapsed_total = time.time() - t_start

    # --- Generate and save report ---
    report = generate_report(results, args.model, elapsed_total)
    report_path = save_report(report)

    # --- Print summary ---
    print_summary(report)
    logger.info(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
