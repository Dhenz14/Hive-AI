# HiveAI Agent Skills

Domain expertise files injected as system context at inference time.
No training needed — instant quality boost.

## How It Works

Each skill is a `SKILL.md` file (~500-2000 tokens) containing condensed domain
expertise: key APIs, code patterns, gotchas, and common mistakes. When the model
receives a question about that domain, the relevant skill file is prepended to
the system prompt, giving it a "cheat sheet" for the answer.

## Available Skills

| Skill | Domain | Tokens |
|-------|--------|--------|
| `hive_sdk/` | beem (Python) + dhive (JS) SDK patterns | ~900 |
| `hive_custom_json/` | Custom JSON ops, protocol IDs, L2 patterns | ~800 |
| `hive_economics/` | RC, voting, rewards, HBD, delegation | ~1000 |
| `hive_layer2/` | Hive-Engine, HAF, VSC | ~900 |
| `hive_security/` | Key hierarchy, multi-sig, recovery, safety | ~900 |
| `hive_architecture/` | DPoS, blocks, APIs, Hivemind, nodes | ~900 |

## Usage

### Automatic (via skill_loader.py)
```python
from skills.skill_loader import load_skills_for_query

# Returns relevant skill content based on query keywords
skill_context = load_skills_for_query("How do I transfer tokens on Hive-Engine?")
system_prompt = CODING_SYSTEM_PROMPT + "\n\n" + skill_context
```

### Manual
```python
from skills.skill_loader import load_skill

# Load a specific skill
skill = load_skill("hive_sdk")
```

## Adding New Skills

1. Create `skills/<skill_name>/SKILL.md`
2. Add routing keywords to `skills/skill_loader.py` SKILL_ROUTES
3. Keep skills under ~2000 tokens for optimal context usage

## Philosophy: Robin Hood

Use expensive frontier models (Claude) to generate high-quality expertise once,
then deploy with cheap local models forever. The expensive model thinks ONCE,
the local model benefits FOREVER.
