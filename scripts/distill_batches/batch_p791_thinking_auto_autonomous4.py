"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 4)

The model identifies and fixes its own systematic weaknesses.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-fix-inconsistency",
        r'''I notice I give inconsistent advice about error handling. Sometimes I recommend try/except around everything, other times I recommend letting errors propagate. How do I make my advice consistent?''',
        r'''<think>
Let me analyze my inconsistency:

**When I recommend try/except:**
- User has a web endpoint → catch errors, return proper HTTP responses
- User is processing a file → catch errors, log and continue
- The error is expected (file not found, invalid input)

**When I recommend letting errors propagate:**
- User is writing library code → let caller decide how to handle
- The error is unexpected (programmer error, assertion failure)
- Catching would hide a bug

**These aren't actually inconsistent — they're different contexts.** But I'm not EXPLAINING the rule, so it looks inconsistent.

**The underlying principle I should make explicit:**
- Catch errors at BOUNDARIES (API endpoints, user input, external services)
- Let errors propagate through INTERNAL code (libraries, utilities, business logic)
- Never catch errors you can't meaningfully handle (except to log and re-raise)

**The fix:** State the principle explicitly every time, then apply it to the specific context. This way my advice is clearly consistent even when the specific recommendation varies.
</think>

**Fixing my inconsistency: I need to state the PRINCIPLE, not just the recommendation.**

**The consistent rule:**
```
Catch errors at BOUNDARIES → return proper responses
Let errors propagate INTERNALLY → let callers decide
Never catch errors you can't handle → except to log and re-raise
```

**How to apply consistently:**

| Context | Recommendation | Why |
|---------|---------------|-----|
| API endpoint | Catch and return HTTP error | Boundary: user-facing |
| Library function | Let errors propagate | Internal: caller decides |
| Background job | Catch, log, and retry/skip | Boundary: no caller to propagate to |
| Database operation | Catch specific DB errors | Boundary: external service |
| Business logic | Let errors propagate | Internal: calling code handles |

**My improved response template:**
```
"Error handling depends on where you are in the code:

At boundaries (API, user input, external services):
    → Catch errors and handle them (return HTTP errors, retry, log)

In internal code (business logic, utilities):
    → Let errors propagate to the caller

Rule: Only catch errors you can meaningfully handle.
In your case, [specific advice based on context]."
```

**The meta-lesson:** When I give seemingly inconsistent advice, the fix isn't picking one side — it's making the underlying decision rule explicit. Context-dependent advice is fine as long as the rule for choosing is clear.'''
    ),
    (
        "thinking/auto-autonomous-improve-code-examples",
        r'''I notice my code examples sometimes use outdated patterns. How do I autonomously keep my code examples current?''',
        r'''<think>
Let me identify which patterns I tend to use that are outdated:

**Python patterns I might use:**
- `typing.List[str]` instead of `list[str]` (3.9+)
- `Union[X, None]` instead of `X | None` (3.10+)
- `.format()` instead of f-strings (3.6+)
- `os.path.join()` when `pathlib.Path` is cleaner
- `json.loads(open(f).read())` instead of `json.load(open(f))`

**JavaScript patterns I might use:**
- `var` instead of `const`/`let`
- `.then()` chains instead of `async/await`
- `module.exports` instead of ES modules
- jQuery patterns instead of vanilla DOM APIs

**How to autonomously update:**
1. Before writing code, check: "What's the current best practice for this pattern?"
2. Default to the most modern syntax that's widely supported
3. Specify the minimum version when using newer features
4. When showing both old and new: lead with new, mention old as fallback
</think>

**Autonomous Pattern Update Protocol**

**Pre-writing check for each language:**

**Python — default to 3.10+ unless specified:**
```python
# Outdated                      # Current
from typing import List         list[str]
Union[X, None]                  X | None
Optional[str]                   str | None
"{}.format(x)"                  f"{x}"
os.path.join(a, b)              Path(a) / b
```

**JavaScript — default to ES2022+ unless specified:**
```javascript
// Outdated                     // Current
var x = 1                       const x = 1
.then().then()                  async/await
require('x')                    import x from 'x'
callback(err, data)             async function
```

**Self-check before presenting code:**
1. Am I using type hints? → Use `list[str]` not `List[str]`
2. Am I using string formatting? → Use f-strings
3. Am I using file paths? → Consider pathlib
4. Am I using callbacks? → Consider async/await
5. Am I using var? → Use const/let

**Template for version-aware examples:**
```python
# Modern Python (3.10+):
def process(items: list[str]) -> dict[str, int] | None:
    ...

# If you need Python 3.8 compatibility:
from typing import List, Dict, Optional
def process(items: List[str]) -> Optional[Dict[str, int]]:
    ...
```

Lead with the modern version. Only mention the legacy version if the user specifies a constraint.'''
    ),
    (
        "thinking/auto-autonomous-calibrate-detail-level",
        r'''How do I autonomously determine the right level of detail for each answer? Sometimes I over-explain, sometimes I under-explain.''',
        r'''<think>
The right level of detail depends on:
1. **The question's specificity** — vague questions need more context, specific questions need focused answers
2. **The user's apparent skill level** — inferred from their question's vocabulary and context
3. **The risk of the topic** — security/money topics need more detail than style preferences
4. **Whether there's a follow-up opportunity** — if they can ask more, start concise

**Signals for MORE detail:**
- Beginner vocabulary ("what is X?")
- High-risk topic (security, database migration, deployment)
- Complex topic with common misconceptions
- The user explicitly asks for explanation

**Signals for LESS detail:**
- Expert vocabulary ("how do I configure X's Y parameter?")
- Simple factual question ("what's the default port for Redis?")
- User asks for "quick" or "brief" answer
- Follow-up conversation is possible

**My calibration heuristic:**
- Default: 3-5 sentences + code example
- Beginner: 5-10 sentences + explained code + gotchas
- Expert: 1-2 sentences + code, skip the explanation
- High-risk: Always detailed, regardless of apparent skill
</think>

**Detail Level Calibration Framework**

| Signal | Detail level | Example |
|--------|-------------|---------|
| "What is X?" | High (explain concept) | 5-10 sentences + analogy |
| "How do I X?" | Medium (show + explain) | 3-5 sentences + code |
| "Why does X?" | Medium-High (explain reasoning) | Explain the mechanism |
| "X doesn't work" | Focused (diagnose) | Ask diagnostic questions or fix |
| Expert terminology | Low (code + brief note) | Code snippet + 1-2 sentences |
| "Quick question" | Minimal | Direct answer, no preamble |

**Autonomous calibration check:**
```
Before answering, ask:
1. How specific is the question?
   Vague → more context needed
   Specific → focused answer

2. What vocabulary does the user use?
   "thingy" → beginner, explain more
   "middleware" → intermediate, moderate detail
   "RAFT consensus" → expert, be concise

3. What's the risk?
   Style preference → brief is fine
   Security/data → detailed regardless of skill level

4. Can they follow up?
   Interactive chat → start concise, elaborate if asked
   One-shot answer → be thorough
```

**The rule of thumb:** Start with the minimum viable answer. If it needs more detail, the user will ask. This is better than overwhelming them with a wall of text that buries the actual answer.'''
    ),
    (
        "thinking/auto-autonomous-monitor-own-patterns",
        r'''How do I detect when I'm falling into repetitive patterns in my responses?''',
        r'''<think>
Repetitive patterns in responses include:
1. Always suggesting the same libraries (requests, FastAPI, PostgreSQL)
2. Always structuring answers the same way (problem → solution → example)
3. Always giving the same caveats ("it depends", "consider your use case")
4. Using the same phrases repeatedly ("let me explain", "here's the thing")
5. Defaulting to the same architecture patterns regardless of context

**Why repetition is bad:**
- Not all problems need the same solution
- Users may notice and lose trust
- I miss better alternatives I don't frequently recommend
- My advice becomes predictable rather than thoughtful

**Detection heuristics:**
- If I'm about to suggest X, ask: "Am I suggesting X because it's the best fit, or because it's my default?"
- If my answer structure is identical to the last 3 answers, vary it
- If I'm using the same metaphor/analogy I used recently, find a new one
</think>

**Pattern Repetition Detection and Prevention**

**Common repetition traps:**

| Pattern | Detection signal | Fix |
|---------|-----------------|-----|
| Same library always | "I always suggest requests/FastAPI" | Consider httpx, aiohttp, Flask |
| Same structure | Problem → Code → Explanation (always) | Sometimes: Example first, then explain |
| Same caveats | "It depends on your use case" | Be specific about WHAT it depends on |
| Same phrases | "Here's the thing..." (every answer) | Vary openings |
| Same architecture | "Use PostgreSQL + Redis" (always) | Consider SQLite, DynamoDB, etc. |

**Self-monitoring protocol:**

**Before recommending a library:**
"Am I recommending [X] because it's best for this, or because it's my default? What are 2 alternatives?"

**Before writing the answer:**
"Am I structuring this the same way as my last answer? Can I try a different format?"
- Sometimes lead with code, then explain
- Sometimes lead with the common mistake, then show the fix
- Sometimes use a comparison table
- Sometimes use a decision tree

**Before adding caveats:**
"Am I saying 'it depends' because it genuinely depends, or because I'm hedging? If it depends, on WHAT specifically?"

```
# Bad (vague caveat):
"The best database depends on your use case."

# Good (specific decision criteria):
"Use PostgreSQL if you need transactions and complex queries.
 Use MongoDB if your schema varies significantly between records.
 Use Redis if you need sub-millisecond key-value lookups."
```

**The meta-principle:** Repetition indicates autopilot. Each answer should be freshly reasoned from the specific context, not pattern-matched from a template.'''
    ),
    (
        "thinking/auto-autonomous-post-response-review",
        r'''Describe a post-response review process I can run after every significant answer to continuously improve.''',
        r'''<think>
A post-response review is a lightweight retrospective on each answer. It should be quick (30 seconds of thought) but structured enough to catch systematic issues.

The key dimensions to evaluate:
1. Was the answer CORRECT?
2. Was it COMPLETE?
3. Was it CLEAR?
4. Was it CONCISE?
5. Was it CALIBRATED (appropriate confidence)?

I should also track patterns across reviews to identify systematic issues.
</think>

**Post-Response Review Protocol (the "5C Review")**

Run this mental checklist after every significant answer:

```
[ ] CORRECT  — Would the code compile/run? Are the facts verifiable?
[ ] COMPLETE — Did I address all parts of the question?
[ ] CLEAR    — Would the target audience understand this?
[ ] CONCISE  — Did I include only what's needed?
[ ] CALIBRATED — Did I express appropriate confidence?
```

**Quick scoring (1-5 each, target: 4+ on all):**

| Dimension | Score | If < 4, action |
|-----------|-------|---------------|
| Correct | __ | Re-check facts, trace code |
| Complete | __ | Add missing points |
| Clear | __ | Simplify language, add example |
| Concise | __ | Remove tangents |
| Calibrated | __ | Add/remove confidence qualifiers |

**Pattern tracking (review weekly):**
```
After 20 answers, look for patterns:
- Which dimension scores lowest most often? → Focus improvement there
- Which TOPIC areas have the most corrections? → Study those
- Am I consistently over-confident or under-confident? → Adjust calibration
```

**Example post-response review:**
```
Question: "How do I handle file uploads in Django?"

My answer: Showed FileField model, form, and view.

Review:
[x] Correct — code would work ✓
[ ] Complete — missed: file size limits, allowed types, storage backend
[x] Clear — well-structured with code ✓
[x] Concise — appropriate length ✓
[x] Calibrated — didn't over-promise ✓

Action: Completeness was weak. Security considerations for file uploads
should be a standard part of my response whenever file upload is the topic.

Pattern note: This is the 3rd time I've missed security considerations
in a file-handling answer. Add "security check" to my file-handling template.
```

**The 30-second version:** After each answer, ask: "If an expert reviewed this, what would they flag?" Fix it before moving on.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
