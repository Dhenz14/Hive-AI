"""
hiveai/orchestrator.py

Request classifier and orchestration logic for HiveAI v1.

Rule-based classifier — zero LLM calls, <1ms, deterministic.
Decides: intent, language, retrieval mode, verification need.
Everything downstream branches on this classification.
"""

import re
import time
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RequestClassification:
    """Structured classification of an incoming chat request."""
    intent: str              # general_chat | code_question | debugging | doc_lookup | refactor | project_rule
    language: str | None     # python | cpp | rust | go | js | hive | None
    needs_retrieval: bool
    retrieval_mode: str      # preinject | agent | hybrid
    needs_verification: bool
    response_contract: str   # none | executable_code — controls output format instruction
    scope: str               # project | global
    confidence: float        # 0.0-1.0 — how confident we are in the classification
    matched_signals: list    # which rules fired (for trace/debug)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Language detection patterns
# ---------------------------------------------------------------------------

_LANG_PATTERNS = {
    "cpp": [
        r"c\+\+", r"\bcpp\b", r"unique_ptr|shared_ptr|weak_ptr",
        r"std::\w+", r"#include\s*<", r"\btemplate\s*<",
        r"\bconstexpr\b", r"\bRAAI\b|\braii\b", r"move\s*semantic",
        r"\.cpp\b|\.hpp\b|\.h\b",
    ],
    "python": [
        r"\bpython\b", r"\bpythonic\b", r"\bpip\b",
        r"def\s+\w+\s*\(", r"import\s+\w+", r"from\s+\w+\s+import",
        r"\.py\b", r"\basyncio\b", r"\bdjango\b|\bflask\b|\bfastapi\b",
        r"dataclass|type\s*hint|\btyping\b",
    ],
    "rust": [
        r"\brust\b", r"\bcargo\b", r"\.rs\b",
        r"\btokio\b", r"fn\s+\w+", r"impl\s+\w+",
        r"&mut\b|&self\b|&str\b", r"\bResult<", r"\bOption<",
    ],
    "go": [
        r"\bgolang\b", r"\bgoroutine\b", r"\.go\b",
        r"\bgo\s+func\b", r"go\s+run\b", r"\bfmt\.\w+",
        r"\bchan\s+\w+", r"func\s+\w+\(",
    ],
    "js": [
        r"\bjavascript\b", r"\btypescript\b", r"\bnode\.?js\b",
        r"\bnpm\b|\byarn\b|\bbun\b|\bdeno\b",
        r"const\s+\w+\s*=", r"=>\s*\{", r"\bpromise\b",
        r"\.ts\b|\.tsx\b|\.js\b|\.jsx\b",
        r"\breact\b|\bnext\.?js\b|\bexpress\b",
    ],
    "hive": [
        r"\bhive\b", r"\bbeem\b", r"\bdhive\b",
        r"custom.?json", r"\bHBD\b", r"resource\s*credit",
        r"posting\s*key|active\s*key|owner\s*key",
        r"hivemind|condenser.api|database.api",
        r"witness|delegation|power\s*(up|down)",
    ],
}

# ---------------------------------------------------------------------------
# Intent detection patterns (checked in priority order)
# ---------------------------------------------------------------------------

_INTENT_RULES = [
    # Debugging signals — high priority
    {
        "intent": "debugging",
        "patterns": [
            r"traceback|exception|error\s*:",         # error traces
            r"segfault|core\s*dump|stack\s*overflow",  # crash patterns
            r"race\s*condition|deadlock|data\s*race",  # concurrency bugs
            r"memory\s*leak|use.after.free",           # memory bugs
            r"not\s*working|doesn't\s*work|broken",    # general failure
            r"wrong\s*(output|result|answer|value)",   # incorrect behavior
            r"fails?\s*(on|when|intermittent|random)",  # intermittent failures
            r"why\s*(does|is|doesn't|isn't)\s*\w+\s*(fail|crash|hang|slow)",
            r"\bbug\b",                                 # explicit "bug" mention
            r"fix\s*(this|the|my)\s*(code|function|error|issue|problem)",
        ],
        "priority": 10,
    },
    # Refactor signals
    {
        "intent": "refactor",
        "patterns": [
            r"\brefactor\b", r"\boptimize\b", r"\bclean\s*up\b",
            r"\bsimplify\b", r"\bextract\b.*\b(function|method|class)\b",
            r"\brewrite\b", r"\brestructure\b",
            r"make\s*(this|it)\s*(faster|cleaner|simpler|better)",
            r"improve\s*(performance|readability|structure)",
        ],
        "priority": 8,
    },
    # Code question — contains code or asks about code
    {
        "intent": "code_question",
        "patterns": [
            r"```",                                    # contains code fence
            r"write\s*(a|me|the)\s*.{0,20}\s*(function|class|script|program|code)",
            r"implement\s", r"create\s*(a|an)\s*\w*\s*(function|class|api|endpoint)",
            r"how\s*(do|would|can|to)\s*I?\s*(write|implement|create|build|code)",
            r"convert\s*.+\s*to\s*",                   # convert X to Y
            r"add\s*(a|an)?\s*\w*\s*(method|function|endpoint|feature|test)",
            r"\b(pattern|technique|idiom|approach|implementation|usage)s?\b",  # noun-phrase code queries
        ],
        "priority": 7,
    },
    # Doc lookup — explicit knowledge questions
    {
        "intent": "doc_lookup",
        "patterns": [
            r"^(what|who|where)\s+(is|are|was|were)\s",
            r"^explain\s", r"^describe\s", r"^tell\s*me\s*about\s",
            r"^how\s+(does|do|can|to|would)\s", r"^what\s+does\s",
            r"^(show|list|give)\s*me\s*(the|all)?\s*(example|doc|detail|info)",
            r"documentation|reference|spec(ification)?",
        ],
        "priority": 5,
    },
    # Project rule — Hive-specific methodology
    {
        "intent": "project_rule",
        "patterns": [
            r"hive\s*(rule|convention|standard|best\s*practice)",
            r"(posting|active|owner)\s*key\s*(should|must|rule)",
            r"hive\s*(security|policy|guideline)",
        ],
        "priority": 6,
    },
]

# ---------------------------------------------------------------------------
# Code indicators for verification detection
# ---------------------------------------------------------------------------

_CODE_INDICATORS = [
    r"```\w*\n",         # fenced code blocks
    r"write\s*(a|me|the)\s*\w*\s*(function|class|script|program)",
    r"implement\s",
    r"create\s*(a|an)\s*\w*\s*(function|class|api|endpoint)",
    r"code\s*(example|sample|snippet)",
    r"fix\s*(this|the|my)\s*(code|function|bug|error)",
]

# Errors that are fixable by the model (worth retrying)
FIXABLE_ERROR_TYPES = frozenset({
    "SyntaxError", "IndentationError", "TabError",     # Python syntax
    "NameError", "ImportError", "ModuleNotFoundError",  # Python imports
    "TypeError",                                        # often fixable
    "compile_error",                                    # C++/Rust/Go
    "ReferenceError",                                   # JS
})


def detect_language(text: str) -> str | None:
    """Detect programming language from message text. Returns best match or None."""
    text_lower = text.lower()
    scores = {}

    for lang, patterns in _LANG_PATTERNS.items():
        count = 0
        for pattern in patterns:
            if re.search(pattern, text_lower):
                count += 1
        if count > 0:
            scores[lang] = count

    if not scores:
        return None

    # Return the language with the most pattern matches
    return max(scores, key=scores.get)


def _has_code_fence(text: str) -> bool:
    """Check if the message contains a code fence."""
    return "```" in text


def _has_error_trace(text: str) -> bool:
    """Check if the message contains what looks like an error trace."""
    indicators = [
        r"Traceback \(most recent",
        r"Error:\s",
        r"error\[\w+\]:",          # Rust errors
        r"error:",                  # generic
        r"at\s+\w+\.go:\d+",      # Go stack traces
        r"at\s+Object\.",          # JS stack traces
        r"\.cpp:\d+:\d+:\s*error", # C++ errors
    ]
    return any(re.search(p, text) for p in indicators)


def _has_file_path(text: str) -> bool:
    """Check if the message contains file paths suggesting codebase work."""
    return bool(re.search(r'[\w/\\]+\.\w{1,5}\b', text) and
                re.search(r'(src/|lib/|app/|components/|\.py|\.ts|\.rs|\.go|\.cpp|\.js)', text))


def classify_request(
    message: str,
    history: list[dict] | None = None,
) -> RequestClassification:
    """
    Classify an incoming chat request. Zero GPU cost, <1ms.

    Returns a RequestClassification with intent, language, retrieval mode,
    verification need, and matched signals for debugging.
    """
    start = time.perf_counter()
    msg_lower = message.lower().strip()
    signals = []

    # --- Language detection ---
    language = detect_language(message)
    if language:
        signals.append(f"lang:{language}")

    # --- Intent detection (priority-ordered) ---
    intent = "general_chat"
    best_priority = 0

    for rule in _INTENT_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, msg_lower):
                if rule["priority"] > best_priority:
                    intent = rule["intent"]
                    best_priority = rule["priority"]
                    signals.append(f"intent:{intent}:{pattern[:30]}")
                break  # one match per rule is enough

    # --- Override: error traces always mean debugging ---
    if _has_error_trace(message) and intent != "debugging":
        intent = "debugging"
        signals.append("override:error_trace_detected")

    # --- Override: code fences in non-debugging context → code_question ---
    if _has_code_fence(message) and intent == "general_chat":
        intent = "code_question"
        signals.append("override:code_fence_detected")

    # --- Context from history ---
    history_is_code = False
    if history and len(history) >= 2:
        last_assistant = None
        for h in reversed(history):
            if h.get("role") == "assistant":
                last_assistant = h.get("content", "")
                break
        if last_assistant and "```" in last_assistant:
            history_is_code = True
            if intent == "general_chat":
                intent = "code_question"
                signals.append("override:history_has_code")

    # --- Retrieval mode ---
    if _has_file_path(message) or intent == "refactor":
        retrieval_mode = "agent"
        signals.append("mode:agent:file_paths_or_refactor")
    elif intent in ("debugging",) and history_is_code:
        retrieval_mode = "hybrid"
        signals.append("mode:hybrid:debugging_with_code_history")
    elif intent in ("doc_lookup", "code_question", "project_rule"):
        # Conceptual/code queries benefit from multi-hop + book refs
        retrieval_mode = "hybrid"
        signals.append(f"mode:hybrid:{intent}_deep_retrieval")
    else:
        retrieval_mode = "preinject"
        signals.append("mode:preinject:default")

    # --- Verification need ---
    needs_verification = False
    if intent in ("code_question", "debugging", "refactor"):
        needs_verification = True
        signals.append("verify:intent_requires_code")
    elif _has_code_fence(message):
        needs_verification = True
        signals.append("verify:code_fence_in_input")

    # --- Retrieval need ---
    needs_retrieval = intent != "general_chat" or bool(language)
    if intent == "general_chat" and len(msg_lower.split()) < 4:
        # Very short general messages like "hi" or "thanks" — skip retrieval
        needs_retrieval = False
        signals.append("no_retrieval:short_general_chat")

    # --- Scope ---
    scope = "global"
    if language == "hive" or intent == "project_rule":
        scope = "project"
        signals.append("scope:project:hive_domain")

    # --- Confidence ---
    confidence = min(1.0, 0.3 + best_priority * 0.07 + (0.1 if language else 0))

    elapsed_us = (time.perf_counter() - start) * 1_000_000

    # --- Response contract ---
    response_contract = "executable_code" if needs_verification else "none"

    result = RequestClassification(
        intent=intent,
        language=language,
        needs_retrieval=needs_retrieval,
        retrieval_mode=retrieval_mode,
        needs_verification=needs_verification,
        response_contract=response_contract,
        scope=scope,
        confidence=confidence,
        matched_signals=signals,
    )

    logger.info(
        f"Classified in {elapsed_us:.0f}µs: intent={intent}, lang={language}, "
        f"mode={retrieval_mode}, verify={needs_verification}, "
        f"signals={len(signals)}"
    )

    return result


def is_fixable_error(error_type: str) -> bool:
    """Check if a verification error type is worth retrying."""
    return error_type in FIXABLE_ERROR_TYPES


def should_retry_verification(verification_result: dict) -> bool:
    """
    Decide if a failed verification is worth retrying.

    Only retries for syntax/import/type errors — the model can likely fix these.
    Does NOT retry for logic errors, timeouts, or runtime crashes.
    """
    if verification_result.get("failed", 0) == 0:
        return False

    results = verification_result.get("results", [])
    fixable_count = 0
    for r in results:
        if not r.get("success", True):
            etype = r.get("error_type", "")
            if is_fixable_error(etype):
                fixable_count += 1

    return fixable_count > 0


def build_revision_prompt(verification_result: dict) -> str:
    """Build a concise error summary for the revision prompt."""
    errors = []
    for r in verification_result.get("results", []):
        if not r.get("success", True):
            etype = r.get("error_type", "unknown")
            stderr = r.get("stderr", "")[:200].strip()
            lang = r.get("language", "")
            if stderr:
                errors.append(f"- [{lang}] {etype}: {stderr}")
            else:
                errors.append(f"- [{lang}] {etype}")

    error_block = "\n".join(errors[:5])  # max 5 errors
    return (
        f"The code in your response has errors:\n{error_block}\n\n"
        "Fix the errors and respond with the corrected version. "
        "Keep the same structure but fix the broken code blocks."
    )
