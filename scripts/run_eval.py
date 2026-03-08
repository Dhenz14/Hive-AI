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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Certificate verification for non-Python code (§23)
_CERT_VERIFY_ENABLED: bool = False  # Set True when --llm-judge + --cert-verify
_CERT_VERIFY_TIMEOUT: int = 60     # Shorter than judge's 180s
_cert_verify_stats = {"calls": 0, "successes": 0, "failures": 0}

CERTIFICATE_PROMPT = """Analyze this {language} code for correctness:

```{language}
{code}
```

Provide a verification certificate:
1. CLAIM: What this code is supposed to do
2. PREMISES: Key facts from the code (P1, P2, P3...)
3. CODE TRACE: Step through execution, referencing premises
4. CONCLUSION: VALID or INVALID with specific reasoning
5. SCORE: 0.0-1.0 confidence in correctness

Respond with JSON: {{"valid": true, "score": 0.8, "reasoning": "..."}}"""

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
def _score_non_python_block(code: str, language: str) -> float:
    """
    Score a non-Python code block (Rust, Go, C++, etc.) by structural analysis.
    Can't execute these, so we check for language-specific structural markers.
    Returns 0.0-1.0.
    """
    score = 0.0
    markers_hit = 0
    markers_total = 0

    if language in ("rust", "rs"):
        markers = ["fn ", "let ", "->", "::", "impl ", "struct ", "enum ",
                    "use ", "pub ", "mod ", "mut ", "&", "String", "Vec<"]
        markers_total = 6  # expect at least 6 of these
    elif language in ("go", "golang"):
        markers = ["func ", "package ", "import ", "var ", "type ", "struct ",
                    "interface ", "go ", "chan ", "defer ", "range ", ":="]
        markers_total = 5
    elif language in ("cpp", "c++", "c"):
        markers = ["#include", "int ", "void ", "class ", "std::", "return ",
                    "template", "namespace", "auto ", "const ", "->", "new "]
        markers_total = 5
    elif language in ("javascript", "js", "typescript", "ts"):
        markers = ["function ", "const ", "let ", "var ", "=>", "async ",
                    "await ", "export ", "import ", "require(", "class "]
        markers_total = 4
    else:
        # Unknown language — give benefit of doubt if it has code structure
        markers = ["(", ")", "{", "}", ";", "="]
        markers_total = 4

    markers_hit = sum(1 for m in markers if m in code)
    marker_ratio = min(markers_hit / max(markers_total, 1), 1.0)

    # Check structural signals
    lines = code.strip().split("\n")
    has_functions = any(l.strip().startswith(("fn ", "func ", "def ", "void ", "int ",
                                              "pub fn", "async fn", "function "))
                        for l in lines)
    has_braces = "{" in code and "}" in code
    reasonable_length = len(lines) >= 3

    structure = 0.0
    if has_functions:
        structure += 0.3
    if has_braces:
        structure += 0.1
    if reasonable_length:
        structure += 0.1

    # Blend: 50% marker coverage + 50% structure
    score = 0.5 * marker_ratio + 0.5 * min(structure, 0.5) / 0.5
    return round(min(score, 1.0), 3)


def certificate_verify_code(code: str, language: str,
                            llm_url: str, model: str) -> tuple[float | None, str | None]:
    """Verify non-Python code correctness via LLM certificate analysis.

    Calls the LLM judge with a structured certificate prompt that asks it to
    trace execution paths and verify correctness semi-formally.

    Args:
        code: The code to verify.
        language: Programming language (e.g. "rust", "go", "cpp").
        llm_url: Ollama base URL for the judge (e.g. http://localhost:11434).
        model: Judge model name (e.g. "qwen3:32b").

    Returns:
        (score, reasoning) where score is 0.0-1.0, or (None, None) on failure.
        Fail-open: any error returns (None, None) so code isn't penalized.
    """
    import requests

    _cert_verify_stats["calls"] += 1

    prompt = CERTIFICATE_PROMPT.format(language=language, code=code[:3000])

    try:
        r = requests.post(
            f"{llm_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a code correctness verifier. "
                     "Analyze code using semi-formal reasoning and respond with JSON."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.05,
                    "num_predict": 500,
                },
            },
            timeout=_CERT_VERIFY_TIMEOUT,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")

        # Strip thinking tags if present
        if "</think>" in content:
            content = content.split("</think>", 1)[1]

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*"valid"[^{}]*\}', content)
        if not json_match:
            json_match = re.search(r'\{[^{}]+\}', content)
        if not json_match:
            logger.debug("Certificate verify: no JSON found in response")
            _cert_verify_stats["failures"] += 1
            return (None, None)

        data = json.loads(json_match.group())
        cert_score = float(data.get("score", 0.5))
        cert_score = max(0.0, min(1.0, cert_score))
        reasoning = data.get("reasoning", "")

        _cert_verify_stats["successes"] += 1
        return (round(cert_score, 3), reasoning)

    except Exception as e:
        logger.debug(f"Certificate verify failed: {e}")
        _cert_verify_stats["failures"] += 1
        return (None, None)


def score_code_validity(response: str) -> float:
    """
    Dimension 1: Code validity (0.0-1.0).
    v3: Language-aware — executes Python, scores non-Python by structure.

    Python blocks: syntax check + execution (0.0-1.0)
    Non-Python blocks (Rust/Go/C++/JS): structural analysis (0.0-1.0)
    Mixed responses: weighted average across all blocks.
    """
    from hiveai.sandbox import (
        extract_code_blocks, validate_syntax, execute_python,
        execute_cpp, execute_rust, execute_go, execute_javascript,
        strip_typescript_annotations,
    )

    blocks = extract_code_blocks(response)
    if not blocks:
        code_indicators = ["def ", "class ", "import ", "return ", "for ", "while ",
                           "fn ", "func ", "#include", "function "]
        hits = sum(1 for k in code_indicators if k in response)
        return min(hits * 0.1, 0.3)

    # Language → executor mapping for compiled/interpreted languages
    _compiled_executors = {
        "go": execute_go,
        "golang": execute_go,
        "cpp": execute_cpp,
        "c++": execute_cpp,
        "c": execute_cpp,
        "rust": execute_rust,
        "rs": execute_rust,
        "javascript": execute_javascript,
        "js": execute_javascript,
        "typescript": execute_javascript,
        "ts": execute_javascript,
    }

    python_scores = []
    non_python_scores = []
    # Track (index, code, lang) for structural-only scores eligible for cert verify
    _structural_entries: list[tuple[int, str, str]] = []

    def _append_structural(code: str, lang: str, score: float):
        """Append a structural score and track it for potential cert verification."""
        idx = len(non_python_scores)
        non_python_scores.append(score)
        _structural_entries.append((idx, code, lang))

    for block in blocks:
        lang = block.get("language", "").lower()

        if lang in ("python", "py", ""):
            # Python: try syntax check + execution
            syn = validate_syntax(block["code"])
            if syn["valid"]:
                result = execute_python(block["code"], timeout=10)
                # Blend syntax (0.3) + execution (0.7)
                python_scores.append(0.3 + 0.7 * (1.0 if result["success"] else 0.0))
            else:
                # If untagged block fails Python parse, try structural scoring
                if lang == "":
                    _append_structural(block["code"], "unknown",
                                       _score_non_python_block(block["code"], "unknown"))
                else:
                    python_scores.append(0.0)
        elif lang in _compiled_executors:
            # Compiled/interpreted languages: try execution, fall back to structural
            executor = _compiled_executors[lang]
            exec_code = block["code"]
            # Strip TypeScript annotations before running through Node.js
            if lang in ("typescript", "ts"):
                exec_code = strip_typescript_annotations(exec_code)
            try:
                result = executor(exec_code, timeout=15)
                if result["error_type"] == "EnvironmentError":
                    # Compiler not installed — fall back to structural analysis
                    _append_structural(block["code"], lang,
                                       _score_non_python_block(block["code"], lang))
                elif result["success"]:
                    # Compiles and runs: full score
                    non_python_scores.append(1.0)
                elif result.get("compile_stderr"):
                    # Compile error: partial credit based on structural analysis
                    structural = _score_non_python_block(block["code"], lang)
                    non_python_scores.append(min(structural, 0.3))
                else:
                    # Compiled but runtime error: good code, bad logic
                    non_python_scores.append(0.7)
            except Exception:
                # Executor failed — fall back to structural
                _append_structural(block["code"], lang,
                                   _score_non_python_block(block["code"], lang))
        else:
            # Other/unknown languages: structural analysis
            _append_structural(block["code"], lang,
                               _score_non_python_block(block["code"], lang))

    # --- Certificate verification for structural-only non-Python scores (§23) ---
    # Only runs when --llm-judge is configured AND --cert-verify is enabled.
    # Blends certificate score with structural score for blocks scoring < 0.8.
    if _CERT_VERIFY_ENABLED and _LLM_JUDGE_URL and _structural_entries:
        for idx, code, lang in _structural_entries:
            structural_score = non_python_scores[idx]
            if structural_score < 0.8:
                cert_score, cert_reasoning = certificate_verify_code(
                    code, lang, _LLM_JUDGE_URL, _LLM_JUDGE_MODEL
                )
                if cert_score is not None:
                    # Blend: structural stays primary (60%), certificate supplements (40%)
                    blended = 0.6 * structural_score + 0.4 * cert_score
                    non_python_scores[idx] = round(blended, 3)
                    logger.debug(
                        f"Certificate verify [{lang}]: structural={structural_score:.3f} "
                        f"cert={cert_score:.3f} blended={blended:.3f} — {cert_reasoning}"
                    )

    all_scores = python_scores + non_python_scores
    if not all_scores:
        return 0.0

    return round(sum(all_scores) / len(all_scores), 3)


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
    v4 scorer — calibrated against real Qwen2.5-Coder-14B output patterns.

    The model explains via structured prose (headers, numbered lists, bold
    definitions, inline comments) more than via academic connector phrases.
    This scorer weights structure heavily and uses relaxed word thresholds.
    """
    if not response:
        return 0.0

    response_lower = response.lower()
    word_count = len(response.split())
    score = 0.0

    # --- Content depth (0.20 max, relaxed thresholds) ---
    if word_count >= 500:
        score += 0.20
    elif word_count >= 300:
        score += 0.16
    elif word_count >= 200:
        score += 0.12
    elif word_count >= 100:
        score += 0.08
    elif word_count >= 50:
        score += 0.04

    # --- Prose ratio bonus (0.10 max) ---
    # Reward responses that balance code with explanation, not just dump code.
    code_text = "".join(re.findall(r"```.*?```", response, re.DOTALL))
    code_words = len(code_text.split())
    prose_words = max(word_count - code_words, 0)
    if word_count > 0:
        prose_ratio = prose_words / word_count
        if prose_ratio >= 0.40:
            score += 0.10
        elif prose_ratio >= 0.25:
            score += 0.06
        elif prose_ratio >= 0.10:
            score += 0.03

    # --- Reasoning markers (0.25 max) ---
    # Broad list matching how coding LLMs actually explain.
    causal = ["because", "therefore", "consequently", "as a result",
              "this means", "which leads to", "the reason", "due to", "hence",
              "which means", "in other words", "so that", "this ensures",
              "this allows", "this way", "this makes", "this is why",
              "the idea is", "the key insight"]
    nuance = ["however", "although", "on the other hand", "trade-off",
              "alternatively", "edge case", "caveat", "unless",
              "keep in mind", "be aware", "be careful", "downside",
              "limitation", "pitfall", "gotcha", "the catch",
              "in contrast", "compared to", "unlike", "whereas"]
    teaching = ["for example", "common mistake", "best practice",
                "note that", "important", "consider", "step 1", "first,",
                "let's", "here's how", "here is", "notice that",
                "the syntax", "this pattern", "in practice", "typically",
                "the approach", "works by", "step by step", "to summarize",
                "in summary", "the key", "remember that", "make sure"]

    causal_hits = sum(1 for m in causal if m in response_lower)
    nuance_hits = sum(1 for m in nuance if m in response_lower)
    teaching_hits = sum(1 for m in teaching if m in response_lower)

    reasoning = 0.0
    reasoning += min(causal_hits * 0.04, 0.10)
    reasoning += min(nuance_hits * 0.035, 0.08)
    reasoning += min(teaching_hits * 0.035, 0.07)
    score += min(reasoning, 0.25)

    # --- Structure (0.30 max — primary signal for coding LLMs) ---
    headers = re.findall(r"^#{1,3}\s+\w", response, re.MULTILINE)
    list_items = re.findall(r"^[\s]*(?:[-*]|\d+\.)\s+", response, re.MULTILINE)
    code_blocks = len(re.findall(r"```", response)) // 2
    inline_comments = re.findall(r"#\s+\w{3,}", response)
    docstrings = re.findall(r'""".*?"""', response, re.DOTALL)

    structure = 0.0
    # Headers (max 0.08)
    if len(headers) >= 3:
        structure += 0.08
    elif len(headers) >= 2:
        structure += 0.06
    elif len(headers) >= 1:
        structure += 0.03
    # List items (max 0.06)
    if len(list_items) >= 5:
        structure += 0.06
    elif len(list_items) >= 3:
        structure += 0.05
    elif len(list_items) >= 1:
        structure += 0.02
    # Code blocks (max 0.05)
    if code_blocks >= 2:
        structure += 0.05
    elif code_blocks >= 1:
        structure += 0.03
    # Inline comments (max 0.04)
    structure += min(len(inline_comments) * 0.01, 0.04)
    # Docstrings (max 0.03)
    structure += min(len(docstrings) * 0.015, 0.03)
    # Bold terms (max 0.05)
    bold = re.findall(r"\*\*[^*]{2,30}\*\*", response)
    if len(bold) >= 4:
        structure += 0.05
    elif len(bold) >= 2:
        structure += 0.04
    # Bold-definition patterns: **Term**: description (max 0.04)
    bold_defs = re.findall(r"\*\*[^*]{2,30}\*\*\s*[:—–-]", response)
    if len(bold_defs) >= 3:
        structure += 0.04
    elif len(bold_defs) >= 1:
        structure += 0.02
    # Numbered step patterns (max 0.03)
    numbered_steps = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]\s|step\s*\d)", response, re.IGNORECASE)
    if len(numbered_steps) >= 3:
        structure += 0.03
    score += min(structure, 0.30)

    # --- Penalties (up to -0.20) ---
    penalties = 0.0
    if word_count < 30:
        penalties += 0.20
    elif word_count < 50:
        penalties += 0.10

    # Repetitive content
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', response) if len(s.strip()) > 20]
    if len(sentences) >= 3:
        unique_ratio = len(set(s.lower()[:50] for s in sentences)) / len(sentences)
        if unique_ratio < 0.7:
            penalties += 0.15

    final = max(0.0, score - penalties)
    return round(min(final, 1.0), 3)


# ---------------------------------------------------------------------------
# LLM-as-Judge scorer (optional, --llm-judge flag)
# ---------------------------------------------------------------------------
# Uses a separate LLM (typically a reasoning model like qwen3:32b via Ollama)
# to score concept_coverage and explanation_quality instead of keyword matching.
#
# This produces more meaningful scores because:
#   1. It understands whether code ACTUALLY implements the asked concept
#   2. It can evaluate explanation quality semantically, not just by word count
#   3. It handles non-Python languages equally well (no Python-specific bias)
#
# Usage:
#   python scripts/run_eval.py --model hiveai-v7 --base-url http://localhost:11435 \
#       --llm-judge http://localhost:11434 --judge-model qwen3:32b
#
# The judge model MUST be different from the model being evaluated to avoid
# circular scoring bias. Ollama on :11434 for judge, llama-server on :11435
# for the model under test is the recommended setup.
# ---------------------------------------------------------------------------

_LLM_JUDGE_URL: str | None = None
_LLM_JUDGE_MODEL: str = "qwen3:32b"
_LLM_JUDGE_RETRIES: int = 2
_LLM_JUDGE_TIMEOUT: int = 180  # seconds — reasoning models can be slow
_llm_judge_stats = {"calls": 0, "successes": 0, "failures": 0, "fallbacks": 0}

_JUDGE_SYSTEM_PROMPT = (
    "You are a senior software engineer evaluating AI coding assistant responses. "
    "You score responses objectively on specific dimensions. You MUST explain your "
    "reasoning before giving scores — analyze the response first, then commit to numbers."
)

_JUDGE_PROMPT_TEMPLATE = """Evaluate this AI coding assistant response.

## Task given to the assistant
{instruction}

## Expected concepts
{concepts}

## Assistant's response (may be truncated)
{response}

---

Score on exactly TWO dimensions (0.0 to 1.0, one decimal place):

**concept_coverage** — Does the response actually cover the expected concepts?
- 1.0 = all concepts present, code correctly implements the topic
- 0.8 = most concepts covered, minor omissions
- 0.6 = core concept present but missing important details
- 0.4 = partial coverage, significant gaps
- 0.2 = barely touches the topic
- 0.0 = wrong topic or empty response

**explanation_quality** — Does it explain WHY, not just WHAT?
- 1.0 = excellent: explains reasoning, trade-offs, alternatives, edge cases
- 0.8 = good: clear explanations with some depth
- 0.6 = adequate: explains the basics but lacks depth
- 0.4 = minimal: mostly code with brief comments
- 0.2 = almost no explanation
- 0.0 = pure code dump with zero explanation

You MUST respond in this EXACT format (reasoning first, then scores):

<reasoning>
[2-4 sentences: What concepts are covered? What's missing? How good are the explanations?]
</reasoning>
<scores>
{{"concept_coverage": X.X, "explanation_quality": X.X}}
</scores>"""


def _parse_judge_response(content: str) -> dict | None:
    """Parse the judge's response, extracting JSON scores and optional reasoning.

    Handles (in priority order):
    1. <reasoning>...</reasoning><scores>{...}</scores> (preferred format)
    2. Raw JSON, JSON in markdown code blocks, JSON after thinking tags (legacy)
    Returns validated scores dict (with optional 'reasoning' key) or None.
    """
    # Extract reasoning if present (for logging / diagnostics)
    reasoning = None
    reasoning_match = re.search(r"<reasoning>(.*?)</reasoning>", content, flags=re.DOTALL)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()

    # Try structured <scores> tag first
    scores_match = re.search(r"<scores>\s*(\{.*?\})\s*</scores>", content, flags=re.DOTALL)
    if scores_match:
        try:
            scores = json.loads(scores_match.group(1))
        except json.JSONDecodeError:
            scores = None
    else:
        scores = None

    # Fallback: strip thinking tags and find JSON anywhere
    if scores is None:
        stripped = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        stripped = re.sub(r"<reasoning>.*?</reasoning>", "", stripped, flags=re.DOTALL).strip()
        stripped = re.sub(r"```(?:json)?\s*", "", stripped).strip()
        stripped = stripped.strip("`").strip()

        json_match = re.search(r'\{[^{}]*"concept_coverage"[^{}]*\}', stripped)
        if not json_match:
            json_match = re.search(r'\{[^{}]+\}', stripped)
        if not json_match:
            return None

        try:
            scores = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

    if scores is None:
        return None

    # Validate required keys and value ranges
    cc = scores.get("concept_coverage")
    eq = scores.get("explanation_quality")
    if cc is None or eq is None:
        return None

    try:
        cc = float(cc)
        eq = float(eq)
    except (ValueError, TypeError):
        return None

    # Sanity check: scores must be in [0, 1]
    cc = max(0.0, min(1.0, cc))
    eq = max(0.0, min(1.0, eq))

    result = {
        "concept_coverage": round(cc, 2),
        "explanation_quality": round(eq, 2),
    }
    if reasoning:
        result["reasoning"] = reasoning
    return result


def llm_judge_score(instruction: str, response: str,
                    expected_concepts: list[str]) -> dict | None:
    """Score concept coverage and explanation quality using an LLM judge.

    Makes up to _LLM_JUDGE_RETRIES+1 attempts. Returns None on failure,
    allowing the caller to fall back to keyword-based scoring.

    Args:
        instruction: The original coding challenge prompt.
        response: The model's response to score.
        expected_concepts: List of concept keywords expected in the response.

    Returns:
        {"concept_coverage": float, "explanation_quality": float} or None.
    """
    if not _LLM_JUDGE_URL:
        return None

    import requests

    _llm_judge_stats["calls"] += 1

    concepts_str = ", ".join(expected_concepts) if expected_concepts else "(none specified — judge by topic relevance)"
    # Truncate response to fit in judge's context window
    resp_truncated = response[:3500]
    if len(response) > 3500:
        resp_truncated += f"\n\n[... truncated, {len(response)} chars total]"

    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        instruction=instruction[:600],
        concepts=concepts_str,
        response=resp_truncated,
    )

    last_error = None
    for attempt in range(_LLM_JUDGE_RETRIES + 1):
        try:
            r = requests.post(
                f"{_LLM_JUDGE_URL}/api/chat",
                json={
                    "model": _LLM_JUDGE_MODEL,
                    "messages": [
                        {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.05,  # Near-deterministic for consistent scoring
                        "num_predict": 400,   # Reasoning + JSON scores
                    },
                },
                timeout=_LLM_JUDGE_TIMEOUT,
            )
            r.raise_for_status()
            content = r.json()["message"]["content"]
            result = _parse_judge_response(content)

            if result is not None:
                _llm_judge_stats["successes"] += 1
                return result

            # Parse failed — retry with a cleaner request
            last_error = f"Could not parse judge response: {content[:100]}"
            logger.debug(f"LLM judge parse failure (attempt {attempt + 1}): {last_error}")

        except requests.exceptions.Timeout:
            last_error = "timeout"
            logger.debug(f"LLM judge timeout (attempt {attempt + 1})")
        except requests.exceptions.ConnectionError:
            last_error = "connection refused"
            logger.warning(f"LLM judge connection failed — is Ollama running at {_LLM_JUDGE_URL}?")
            _llm_judge_stats["failures"] += 1
            return None  # Don't retry connection errors
        except Exception as e:
            last_error = str(e)
            logger.debug(f"LLM judge error (attempt {attempt + 1}): {e}")

    # All retries exhausted
    _llm_judge_stats["failures"] += 1
    _llm_judge_stats["fallbacks"] += 1
    logger.debug(f"LLM judge gave up after {_LLM_JUDGE_RETRIES + 1} attempts: {last_error}")
    return None


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

    # LLM-as-Judge for concept + explanation (if enabled), fallback to keyword scorers
    judge_result = llm_judge_score(
        challenge["instruction"], response, challenge.get("expected_concepts", [])
    )
    if judge_result:
        d3_concept = judge_result["concept_coverage"]
        d4_explain = judge_result["explanation_quality"]
    else:
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
        "llm_judge_used": judge_result is not None,
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

    # Judge stats (if LLM-as-Judge was used)
    judge_stats = None
    if _LLM_JUDGE_URL:
        judge_used = sum(1 for r in scored if r.get("llm_judge_used"))
        judge_stats = {
            "model": _LLM_JUDGE_MODEL,
            "url": _LLM_JUDGE_URL,
            "challenges_judged": judge_used,
            "challenges_fell_back": len(scored) - judge_used,
            **_llm_judge_stats,
        }

    # Certificate verification stats (§23)
    cert_stats = None
    if _CERT_VERIFY_ENABLED and _cert_verify_stats["calls"] > 0:
        cert_stats = {**_cert_verify_stats}

    return {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "scorer": "llm-judge" if _LLM_JUDGE_URL else "keyword-v4",
        "judge": judge_stats,
        "certificate_verify": cert_stats,
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
    print(f"  Scorer: {report.get('scorer', 'keyword-v4')}")
    if report.get("judge"):
        j = report["judge"]
        print(f"  Judge:  {j['model']} via {j['url']}  "
              f"({j['challenges_judged']} judged, {j['challenges_fell_back']} fell back)")

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
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel eval workers (default 1, try 3 for 3x speed)")
    parser.add_argument("--llm-judge", type=str, default=None,
                        help="Use LLM-as-Judge for concept/explain scoring via Ollama "
                             "(e.g. http://localhost:11434). Uses qwen3:32b by default.")
    parser.add_argument("--judge-model", type=str, default="qwen3:32b",
                        help="Model for LLM-as-Judge (default: qwen3:32b)")
    parser.add_argument("--cert-verify", action="store_true", default=None,
                        help="Enable certificate verification for non-Python code "
                             "(default: enabled when --llm-judge is set)")
    parser.add_argument("--no-cert-verify", action="store_true",
                        help="Disable certificate verification even with --llm-judge")
    args = parser.parse_args()

    # --- Wire llama-server URL if given ---
    global _LLAMA_SERVER_URL
    if args.base_url:
        _LLAMA_SERVER_URL = args.base_url
        logger.info(f"Using llama-server at {_LLAMA_SERVER_URL}")

    # --- Wire LLM-as-Judge if given ---
    global _LLM_JUDGE_URL, _LLM_JUDGE_MODEL, _CERT_VERIFY_ENABLED
    if args.llm_judge:
        _LLM_JUDGE_URL = args.llm_judge
        _LLM_JUDGE_MODEL = args.judge_model
        logger.info(f"LLM-as-Judge enabled: {_LLM_JUDGE_URL} ({_LLM_JUDGE_MODEL})")

        # Certificate verification: default ON with --llm-judge, unless --no-cert-verify
        if args.no_cert_verify:
            _CERT_VERIFY_ENABLED = False
        else:
            _CERT_VERIFY_ENABLED = True
            logger.info("Certificate verification enabled for non-Python code scoring")
    elif args.cert_verify:
        logger.warning("--cert-verify has no effect without --llm-judge")

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
    n_workers = max(1, args.workers)

    if n_workers == 1:
        # Sequential mode (original behavior)
        for i, challenge in enumerate(challenges, 1):
            logger.info(f"\n[{i}/{len(challenges)}] {challenge['id']}")
            result = evaluate_challenge(challenge, args.model)
            results.append(result)

            if i % 10 == 0:
                scored_so_far = [r for r in results if not r["error"]]
                if scored_so_far:
                    avg = sum(r["scores"]["overall"] for r in scored_so_far) / len(scored_so_far)
                    elapsed = time.time() - t_start
                    eta = (elapsed / i) * (len(challenges) - i)
                    logger.info(f"\n  --- Progress: {i}/{len(challenges)} | avg_score={avg:.3f} | "
                               f"ETA {eta/60:.1f}min ---\n")
    else:
        # Parallel mode — N workers evaluate challenges concurrently
        logger.info(f"Parallel eval with {n_workers} workers")
        results = [None] * len(challenges)
        completed = 0

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_to_idx = {
                executor.submit(evaluate_challenge, ch, args.model): idx
                for idx, ch in enumerate(challenges)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {
                        "id": challenges[idx]["id"],
                        "category": challenges[idx]["category"],
                        "topic": challenges[idx]["topic"],
                        "difficulty": challenges[idx]["difficulty"],
                        "error": str(e),
                        "scores": {"code_validity": 0, "test_passing": 0,
                                   "concept_coverage": 0, "explanation": 0, "overall": 0},
                        "duration_ms": 0,
                        "response_preview": "",
                    }
                completed += 1
                if completed % 10 == 0:
                    scored = [r for r in results if r and not r.get("error")]
                    if scored:
                        avg = sum(r["scores"]["overall"] for r in scored) / len(scored)
                        elapsed = time.time() - t_start
                        eta = (elapsed / completed) * (len(challenges) - completed)
                        logger.info(f"  --- Progress: {completed}/{len(challenges)} | "
                                   f"avg_score={avg:.3f} | ETA {eta/60:.1f}min ---")

    elapsed_total = time.time() - t_start

    # --- Generate and save report ---
    report = generate_report(results, args.model, elapsed_total)
    report_path = save_report(report)

    # --- Print summary ---
    print_summary(report)
    logger.info(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
