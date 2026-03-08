# Writing Agent Skills — Meta-Skill

How to create new SKILL.md files for HiveAI's skill injection system.

## Skill File Structure

Every skill lives in `skills/{skill_name}/` with two files:

```
skills/
  {skill_name}/
    SKILL.md          # Domain knowledge (~300-800 tokens)
    skill_meta.json   # Test cases for skill_lift.py evaluation
```

## SKILL.md Format Rules

1. **Title**: Single `# Heading` with the domain name
2. **Sections**: 3-6 focused sections with `##` headings
3. **Code examples**: Fenced blocks with language tags (````python`, ````rust`, etc.)
4. **Key gotchas**: A final section with common mistakes and warnings
5. **Token budget**: Stay under 800 tokens — skills are injected into every prompt

### Template

```markdown
# {Domain} Patterns

## Pattern 1: {Name}
{2-3 sentence explanation}
\```{language}
// Concrete, production-ready example
\```

## Pattern 2: {Name}
{Explanation with trade-offs}
\```{language}
// Another example
\```

## Quick Reference
| Pattern | When to Use | Complexity |
|---------|-------------|------------|
| ...     | ...         | ...        |

## Key Gotchas
- **{Mistake}**: {Why it's wrong and the fix}
- **{Mistake}**: {Explanation}
```

## skill_meta.json Format

```json
{
  "name": "skill_name",
  "description": "One-line description",
  "version": "1.0",
  "categories": ["python", "rust"],
  "test_queries": [
    "A query that SHOULD trigger this skill",
    "Another relevant query"
  ],
  "negative_queries": [
    "A query that should NOT trigger this skill"
  ]
}
```

## Adding Route Patterns

After creating the skill, register it in `skills/skill_loader.py`:

```python
# In SKILL_ROUTES list, add:
("skill_name", [
    r"keyword1|keyword2",
    r"multi word phrase",
], priority),  # priority 3-10, higher = checked first
```

Priority guidelines:
- **10**: Very specific domain (e.g., `hive_security` for "key hierarchy")
- **7-9**: Specific language/framework
- **3-5**: General patterns (e.g., `debugging_patterns`)

## Quality Checklist

Before committing a new skill:

1. Code examples compile/run without errors
2. Examples show production patterns, not toy code
3. Gotchas section covers real mistakes developers make
4. Token count under 800 (`len(content.split()) * 4 // 3`)
5. `skill_lift.py` shows positive lift on relevant eval challenges
6. At least 2 test queries in skill_meta.json match correctly
7. No overlap with existing skills (check `skill_loader.py` routes)

## Measuring Skill Impact

```bash
# Test if skill helps or hurts
python scripts/skill_lift.py --skill {skill_name} --limit 5

# Expected output:
#   Result: HELPS — lift=+0.0450 (+4.50%)
#   [3 improved, 0 degraded, 2 neutral]
```

If lift is negative or neutral, iterate on the skill content before shipping.
