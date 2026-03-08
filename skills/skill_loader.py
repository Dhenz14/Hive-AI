"""
Skill loader — matches user queries to relevant SKILL.md files
and returns their content for injection into the system prompt.

Usage:
    from skills.skill_loader import load_skills_for_query, load_skill

    # Auto-detect relevant skills from query
    context = load_skills_for_query("How do I post on Hive using beem?")

    # Load a specific skill
    context = load_skill("hive_sdk")
"""

import re
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent

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
        print()
