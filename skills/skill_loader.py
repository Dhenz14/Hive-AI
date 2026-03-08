"""
Skill loader — matches user queries to relevant SKILL.md files
and returns their content for injection into the system prompt.

Also provides workflow gates: optional pre/post conditions that can be
checked programmatically to validate query suitability and response quality.

Usage:
    from skills.skill_loader import load_skills_for_query, load_skill
    from skills.skill_loader import check_preconditions, validate_response
    from skills.skill_loader import plan_task

    # Auto-detect relevant skills from query
    context = load_skills_for_query("How do I post on Hive using beem?")

    # Load a specific skill
    context = load_skill("hive_sdk")

    # Validate a response against matched skill conditions
    result = validate_response(response_text, ["rust_async", "go_concurrency"])
    # result = {"valid": True/False, "violations": [...], "suggestions": [...]}
"""

import json
import re
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent

# Cache for loaded skill metadata (populated lazily)
_meta_cache: dict[str, dict] = {}

# Each route: (skill_name, keywords, priority)
# Higher priority = checked first. If multiple match, all are included.
SKILL_ROUTES = [
    # Hive Security (check first — "key" is common but security context matters)
    ("hive_security", [
        r"key\s*(hierarchy|management|storage|security|recover)",
        r"owner\s*key", r"active\s*key", r"posting\s*key", r"memo\s*key",
        r"multi.?sig", r"account\s*recovery", r"phishing",
        r"hive.*security", r"private\s*key.*safe",
        r"authority", r"weight.*threshold",
    ], 10),

    # Hive Economics
    ("hive_economics", [
        r"resource\s*credit", r"\bRC\b", r"voting\s*power",
        r"curation", r"reward", r"power\s*(up|down)",
        r"\bHBD\b", r"hive\s*backed", r"savings.*interest",
        r"delegation", r"delegate.*vests", r"vest",
        r"reward\s*(pool|fund)", r"payout",
        r"hive.*econom", r"inflation",
    ], 8),

    # Hive Custom JSON
    ("hive_custom_json", [
        r"custom.?json", r"ssc.mainnet", r"protocol\s*id",
        r"required_(posting_)?auths", r"layer.?2.*json",
        r"broadcast.*json", r"deterministic.*process",
        r"splinterland", r"sm_",
    ], 8),

    # Hive Layer 2
    ("hive_layer2", [
        r"hive.?engine", r"SWAP\.HIVE", r"\bHAF\b",
        r"sidechain", r"\bVSC\b", r"smart\s*contract.*hive",
        r"token.*creat", r"hive.*token", r"\bBEE\b",
        r"tribaldex", r"diesel\s*pool",
        r"hive.*defi", r"hive.*nft",
    ], 7),

    # Hive Architecture
    ("hive_architecture", [
        r"hive.*architect", r"\bDPoS\b", r"witness",
        r"block\s*(produc|structur|time)", r"consensus",
        r"hivemind", r"condenser.api", r"database.api",
        r"hive.*node", r"hive.*api", r"hive.*rpc",
        r"hive.*fork", r"steem.*hive",
        r"hive.*protocol",
    ], 6),

    # Hive SDK (broadest — catches remaining Hive queries)
    ("hive_sdk", [
        r"\bbeem\b", r"\bdhive\b", r"hive.*sdk",
        r"hive.*post", r"hive.*vote", r"hive.*transfer",
        r"hive.*stream", r"hive.*account",
        r"hive.*comment", r"hive.*blog",
        r"hive\s*blockchain", r"hive.*develop",
        r"hive.*python", r"hive.*javascript",
    ], 5),

    # Python Idioms
    ("python_idioms", [
        r"\bpython\b", r"\bpythonic\b", r"dataclass", r"type\s*hint",
        r"asyncio", r"\btyping\b", r"context\s*manager", r"f.string",
        r"walrus", r"pattern\s*match", r"\bitertools\b", r"\bfunctools\b",
        r"decorator", r"\bpep\b",
    ], 4),

    # Rust Async
    ("rust_async", [
        r"\brust\b.*async", r"\btokio\b", r"\basync\s*fn\b",
        r"rust.*concurren", r"rust.*spawn", r"rust.*future",
        r"rust.*channel", r"rust.*semaphore", r"rust.*select!",
        r"\brust\b", r"\.rs\b", r"cargo\b",
    ], 4),

    # Go Concurrency
    ("go_concurrency", [
        r"\bgoroutine\b", r"\bgo\s+func\b", r"go.*channel",
        r"go.*concurren", r"go.*waitgroup", r"go.*mutex",
        r"go.*context", r"go.*errgroup", r"go.*worker\s*pool",
        r"\bgolang\b", r"\bgo\b.*\b(pattern|async|parallel)\b",
        r"\.go\b",
    ], 4),

    # C++ Modern
    ("cpp_modern", [
        r"\bc\+\+\b", r"\bcpp\b", r"template.*c\+\+", r"smart\s*pointer",
        r"unique_ptr", r"shared_ptr", r"move\s*semantic", r"RAII",
        r"\braii\b", r"concepts?\s*c\+\+", r"constexpr",
        r"std::variant", r"std::optional", r"ranges?\s*view",
    ], 4),

    # JavaScript / TypeScript
    ("js_typescript", [
        r"\bjavascript\b", r"\btypescript\b", r"\bjs\b(?!on)", r"\bts\b",
        r"\bnode\.?js\b", r"\bdeno\b", r"\bbun\b",
        r"async\s*await", r"\bpromise\b", r"\bclosure\b",
        r"event\s*loop", r"\bproxy\b.*handler", r"generic.*type",
        r"\breact\b", r"\bnext\.?js\b", r"\bexpress\b",
    ], 4),

    # Debugging Patterns
    ("debugging_patterns", [
        r"\bdebug\b", r"\bbug\b", r"troubleshoot",
        r"race\s*condition", r"deadlock", r"segfault",
        r"memory\s*leak", r"off.by.one", r"not\s*working",
        r"wrong\s*(output|result)", r"fails?\s*(on|when|intermittent)",
        r"bisect", r"diagnos",
    ], 3),

    # Long Context / RLM
    ("long_context", [
        r"context\s*rot", r"context\s*window", r"long\s*(context|document)",
        r"\bRLM\b", r"recursive\s*language", r"recursive\s*decomposi",
        r"attention\s*dilut", r"large\s*document", r"too\s*much\s*context",
        r"token\s*limit", r"context\s*budget",
    ], 3),

    # Writing Skills (meta-skill for creating new skills)
    ("writing_skills", [
        r"creat.*skill", r"writ.*skill", r"new\s*skill",
        r"SKILL\.md", r"skill_meta", r"skill.*format",
        r"meta.?skill", r"bootstrap.*skill",
    ], 5),
]

# Maximum number of skills to inject per query (prevent context bloat)
MAX_SKILLS = 3


def load_skill(skill_name: str) -> Optional[str]:
    """Load a single SKILL.md by name."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return None


def match_skills(query: str) -> list[str]:
    """Return list of skill names matching the query, ordered by priority."""
    query_lower = query.lower()
    matches = []

    for skill_name, patterns, priority in SKILL_ROUTES:
        for pattern in patterns:
            if re.search(pattern, query_lower):
                matches.append((priority, skill_name))
                break  # One match per skill is enough

    # Sort by priority descending, deduplicate
    matches.sort(key=lambda x: -x[0])
    seen = set()
    result = []
    for _, name in matches:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result[:MAX_SKILLS]


def load_skills_for_query(query: str) -> str:
    """Load and concatenate relevant skills for a query.

    Returns empty string if no skills match.
    """
    skill_names = match_skills(query)
    if not skill_names:
        return ""

    sections = []
    for name in skill_names:
        content = load_skill(name)
        if content:
            sections.append(content)

    if not sections:
        return ""

    header = "--- DOMAIN EXPERTISE (use as reference) ---\n\n"
    return header + "\n\n---\n\n".join(sections)


def list_available_skills() -> list[dict]:
    """List all available skills with metadata."""
    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            # Extract title from first heading
            title = skill_dir.name
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            skills.append({
                "name": skill_dir.name,
                "title": title,
                "tokens_approx": len(content.split()) * 4 // 3,  # rough estimate
                "path": str(skill_file),
            })
    return skills


# ---------------------------------------------------------------------------
# Workflow gates: pre/post condition checking
# ---------------------------------------------------------------------------

def _load_skill_meta(skill_name: str) -> dict:
    """Load and cache skill_meta.json for a given skill."""
    if skill_name in _meta_cache:
        return _meta_cache[skill_name]

    meta_path = SKILLS_DIR / skill_name / "skill_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
    else:
        meta = {}

    _meta_cache[skill_name] = meta
    return meta


def check_preconditions(query: str, skill_name: str) -> dict:
    """Check whether a query satisfies the pre-conditions for a skill.

    Returns:
        {"passed": bool, "violations": list[str]}
    """
    meta = _load_skill_meta(skill_name)
    pre = meta.get("pre_conditions", {})
    if not pre:
        return {"passed": True, "violations": []}

    violations: list[str] = []
    query_lower = query.lower()

    # min_query_length — query must be at least N characters
    min_len = pre.get("min_query_length")
    if min_len is not None and len(query.strip()) < min_len:
        violations.append(
            f"Query too short ({len(query.strip())} chars, need {min_len}+)"
        )

    # must_mention — query must contain at least one of these terms
    must_mention = pre.get("must_mention")
    if must_mention:
        found = any(term.lower() in query_lower for term in must_mention)
        if not found:
            violations.append(
                f"Query should mention at least one of: {must_mention}"
            )

    # must_match_pattern — query must match at least one regex
    patterns = pre.get("must_match_pattern")
    if patterns:
        matched = any(re.search(p, query_lower) for p in patterns)
        if not matched:
            violations.append(
                f"Query did not match expected patterns for skill '{skill_name}'"
            )

    return {"passed": len(violations) == 0, "violations": violations}


def check_postconditions(response: str, skill_name: str) -> dict:
    """Check whether a response satisfies the post-conditions for a skill.

    Returns:
        {"passed": bool, "violations": list[str], "suggestions": list[str]}
    """
    meta = _load_skill_meta(skill_name)
    post = meta.get("post_conditions", {})
    if not post:
        return {"passed": True, "violations": [], "suggestions": []}

    violations: list[str] = []
    suggestions: list[str] = []

    # requires_code_block — response must contain a fenced code block
    if post.get("requires_code_block"):
        if "```" not in response:
            violations.append("Response should include a code block")
            suggestions.append("Add a concrete code example to the response")

    # min_response_length — response must be at least N characters
    min_len = post.get("min_response_length")
    if min_len is not None and len(response.strip()) < min_len:
        violations.append(
            f"Response too short ({len(response.strip())} chars, need {min_len}+)"
        )
        suggestions.append("Provide a more detailed explanation")

    # must_mention — response must address these concepts
    must_mention = post.get("must_mention")
    if must_mention:
        resp_lower = response.lower()
        missing = [
            term for term in must_mention if term.lower() not in resp_lower
        ]
        if missing:
            violations.append(f"Response missing key concepts: {missing}")
            suggestions.append(
                f"Address these topics in the response: {missing}"
            )

    # language_required — response must contain a code block in the specified language
    lang = post.get("language_required")
    if lang:
        # Match ```lang or ```Lang etc.
        pattern = rf"```\s*{re.escape(lang)}\b"
        if not re.search(pattern, response, re.IGNORECASE):
            violations.append(
                f"Response should include a {lang} code example"
            )
            suggestions.append(f"Add a ```{lang} code block to the response")

    # must_not_contain — response must NOT contain these (anti-patterns)
    must_not = post.get("must_not_contain")
    if must_not:
        resp_lower = response.lower()
        found = [term for term in must_not if term.lower() in resp_lower]
        if found:
            violations.append(f"Response contains discouraged terms: {found}")
            suggestions.append(
                f"Remove or replace these terms: {found}"
            )

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "suggestions": suggestions,
    }


def validate_response(
    response: str, matched_skills: list[str]
) -> dict:
    """Main entry point: validate a response against all post-conditions
    for the matched skills.

    Returns:
        {
            "valid": bool,
            "violations": list[str],     # all violations across skills
            "suggestions": list[str],    # actionable fix suggestions
            "per_skill": dict[str, dict] # individual skill results
        }
    """
    all_violations: list[str] = []
    all_suggestions: list[str] = []
    per_skill: dict[str, dict] = {}

    for skill_name in matched_skills:
        result = check_postconditions(response, skill_name)
        per_skill[skill_name] = result
        if not result["passed"]:
            # Prefix violations with skill name for clarity
            for v in result["violations"]:
                all_violations.append(f"[{skill_name}] {v}")
            all_suggestions.extend(result["suggestions"])

    return {
        "valid": len(all_violations) == 0,
        "violations": all_violations,
        "suggestions": all_suggestions,
        "per_skill": per_skill,
    }


# ---------------------------------------------------------------------------
# Plan-then-execute gate (§31): decompose complex queries into subtasks
# ---------------------------------------------------------------------------

# Action verbs that suggest implementation work (not just questions)
_ACTION_VERBS = re.compile(
    r"\b(implement|create|build|add|write|refactor|migrate|deploy|configure|"
    r"set up|integrate|convert|redesign|optimize|fix|update|replace|remove|"
    r"upgrade|install|train|evaluate|test|benchmark)\b",
    re.IGNORECASE,
)

# Complexity signals: multiple actions, conditionals, cross-file references
_COMPLEXITY_SIGNALS = re.compile(
    r"\b(then|after that|also|additionally|and also|first.*then|both.*and|"
    r"across|multiple|several|each|every|all files)\b",
    re.IGNORECASE,
)

PLANNING_THRESHOLD_CHARS = 200


def plan_task(query: str) -> dict:
    """Decompose a complex query into subtasks with time estimates.

    Uses heuristics (instruction length, keyword complexity, action verb count)
    to decide if planning is needed. Returns a structured plan.

    Returns:
        {
            "needs_planning": bool,
            "subtasks": list[dict],  # each: {description, estimated_time, dependencies, validation_criteria}
            "estimated_total": str,  # e.g. "10-15 min"
        }
    """
    query_stripped = query.strip()

    # Quick reject: short queries never need planning
    if len(query_stripped) < PLANNING_THRESHOLD_CHARS:
        return {"needs_planning": False, "subtasks": [], "estimated_total": "0 min"}

    # Count action verbs
    action_matches = _ACTION_VERBS.findall(query_stripped)
    n_actions = len(action_matches)

    # Count complexity signals
    complexity_matches = _COMPLEXITY_SIGNALS.findall(query_stripped)
    n_complexity = len(complexity_matches)

    # Decision: need planning if (long + action verbs) or (multiple actions + complexity)
    needs_planning = (n_actions >= 1 and len(query_stripped) >= PLANNING_THRESHOLD_CHARS) or (
        n_actions >= 3
    ) or (n_actions >= 2 and n_complexity >= 2)

    if not needs_planning:
        return {"needs_planning": False, "subtasks": [], "estimated_total": "0 min"}

    # Decompose: split on sentence boundaries that contain action verbs
    sentences = re.split(r'(?<=[.!?\n])\s+', query_stripped)
    subtasks: list[dict] = []
    task_idx = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Check if this sentence contains an action verb
        verbs_in_sentence = _ACTION_VERBS.findall(sentence)
        if not verbs_in_sentence:
            continue

        task_idx += 1
        # Estimate time based on sentence complexity
        word_count = len(sentence.split())
        if word_count > 40:
            est_time = "4-5 min"
        elif word_count > 20:
            est_time = "2-3 min"
        else:
            est_time = "1-2 min"

        subtasks.append({
            "description": sentence[:200],
            "estimated_time": est_time,
            "dependencies": [f"task_{i}" for i in range(1, task_idx)] if task_idx > 1 else [],
            "validation_criteria": f"Verify: {verbs_in_sentence[0]}d successfully",
        })

    # If we couldn't decompose meaningfully, treat as single task
    if len(subtasks) <= 1:
        subtasks = [{
            "description": query_stripped[:200],
            "estimated_time": "3-5 min",
            "dependencies": [],
            "validation_criteria": "Verify all requirements met",
        }]

    # Estimate total
    total_min = sum(2 for _ in subtasks)  # ~2 min average per subtask
    total_max = sum(5 for _ in subtasks)  # ~5 min max per subtask
    estimated_total = f"{total_min}-{total_max} min"

    return {
        "needs_planning": True,
        "subtasks": subtasks,
        "estimated_total": estimated_total,
    }


if __name__ == "__main__":
    # Demo / test
    test_queries = [
        "How do I post on Hive using beem?",
        "How do I transfer tokens on Hive-Engine?",
        "Explain the Hive key hierarchy and account recovery",
        "What are resource credits and how does voting power work?",
        "How do I build a custom_json protocol for my dApp?",
        "Set up a Hive API node with Docker",
        "Write a Python function to sort a list",  # Should NOT match
    ]

    print("Available skills:")
    for s in list_available_skills():
        print(f"  {s['name']}: {s['title']} (~{s['tokens_approx']} tokens)")

    print()
    for q in test_queries:
        matches = match_skills(q)
        print(f"Q: {q}")
        print(f"  -> {matches if matches else '(no skill match)'}")
        # Demo pre-condition check
        for m in matches:
            pre = check_preconditions(q, m)
            if not pre["passed"]:
                print(f"     PRE-CONDITION FAIL ({m}): {pre['violations']}")
        print()

    # Demo post-condition validation
    print("--- Post-condition demo ---")
    demo_response = "Use tokio::spawn to run tasks concurrently."
    demo_skills = ["rust_async"]
    result = validate_response(demo_response, demo_skills)
    print(f"Response: {demo_response!r}")
    print(f"Skills: {demo_skills}")
    print(f"Valid: {result['valid']}")
    if result["violations"]:
        print(f"Violations: {result['violations']}")
        print(f"Suggestions: {result['suggestions']}")
    print()

    # Demo plan-then-execute gate
    print("--- Plan-then-execute demo ---")
    short_q = "Fix the bug in app.py"
    plan = plan_task(short_q)
    print(f"Q: {short_q!r} (len={len(short_q)})")
    print(f"  needs_planning: {plan['needs_planning']}")

    long_q = (
        "Implement a new training pipeline that first preprocesses the JSONL data, "
        "then splits it into category-specific subsets, trains a LoRA adapter for each "
        "category using warm-start from v7, and finally merges all adapters using TIES "
        "merge. Also add validation checks after each stage and write the results to a "
        "JSON report file. Additionally, update the documentation to reflect the new "
        "pipeline architecture and add unit tests for the preprocessing step."
    )
    plan = plan_task(long_q)
    print(f"\nQ: {long_q[:80]}... (len={len(long_q)})")
    print(f"  needs_planning: {plan['needs_planning']}")
    print(f"  estimated_total: {plan['estimated_total']}")
    for i, st in enumerate(plan["subtasks"], 1):
        print(f"  [{i}] {st['description'][:80]}...")
        print(f"      time={st['estimated_time']}, deps={st['dependencies']}")
    print()
