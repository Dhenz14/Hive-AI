"""Phase 4D: Self-Improvement — Meta-Learning (Part 2)

The model learns to analyze its own reasoning patterns and improve its problem-solving strategies.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-recognize-reasoning-patterns",
        r'''I notice I keep making the same type of error: I suggest complex solutions when simple ones exist. How do I build a habit of checking for simpler alternatives?''',
        r'''<think>
This is a bias toward complexity — a common failure mode. Let me analyze why it happens and create a systematic check.

**Why I default to complex solutions:**
1. Complex solutions demonstrate more knowledge (showing off)
2. I pattern-match against enterprise architectures I've seen in training data
3. I don't pause to ask "what's the simplest thing that could work?"
4. Complex solutions feel more "complete" even when completeness isn't needed

**The fix is a pre-response checklist that forces me to consider simplicity:**
1. Before suggesting architecture: "Can this be done with a single file/function?"
2. Before suggesting a library: "Can this be done with the standard library?"
3. Before suggesting a pattern: "Can this be done with a simple if/else?"
4. Before suggesting infrastructure: "Can this run on a single server?"

**The "do I need this?" test:** For each component in my solution, ask: "If I remove this, does the solution still work for the user's stated requirements?" If yes, remove it.
</think>

**Complexity Bias: Detection and Prevention**

**Self-diagnosis questions (ask before presenting any solution):**

| Question | If yes → |
|----------|----------|
| "Can this be a single function?" | Don't suggest a class hierarchy |
| "Can this use the standard library?" | Don't suggest pip install |
| "Can this run without a database?" | Don't suggest PostgreSQL |
| "Can this be a script?" | Don't suggest a microservice |
| "Has the user mentioned scale?" | Don't add caching/queues |

**The "Remove Components" test:**
```
My solution: React + Redux + TypeScript + Tailwind + PostgreSQL + Redis + Docker

Remove Redis: Does it still work? → Yes → Remove it
Remove Docker: Does it still work? → Yes → Remove it
Remove Redux: Does it still work? → Yes → Remove it
Remove TypeScript: Does it still work? → Yes → Remove it

Actual needed solution: React + Tailwind + PostgreSQL
```

**Build the habit:**
1. **Write the complex solution first** (it's natural)
2. **Then simplify**: For each component, ask "does removing this break the solution?"
3. **Present the simple version** with a note: "If you need X later, you can add Y"

**The principle:** The best solution is the simplest one that meets the stated requirements. Not the stated requirements plus imagined future requirements.

**Practice exercise:** Before every answer, force yourself to think of the simplest possible solution (even if it seems too simple). Then evaluate: does it actually meet the requirements? Often, it does.'''
    ),
    (
        "thinking/auto-metalearning-analyze-error-patterns",
        r'''I've been tracking my errors. Here's my log:

1. Suggested Python 2 syntax (print without parentheses) - 3 times
2. Forgot to handle None/null inputs - 5 times
3. Used deprecated library features - 2 times
4. Recommended over-engineered architecture - 4 times
5. Missed edge case in algorithm - 6 times

What patterns do I see and how do I address them?''',
        r'''<think>
Let me categorize these errors:

**Category 1: Version/deprecation errors (items 1, 3)**
Count: 5 occurrences
Pattern: My knowledge has stale information that I present as current
Root cause: Not tagging facts with version information
Fix: Always specify Python version. Check if features are deprecated.

**Category 2: Missing input validation (items 2, 5)**
Count: 11 occurrences — this is the BIGGEST category
Pattern: I assume inputs are well-formed and don't consider boundary/null cases
Root cause: I think about the "happy path" first and don't systematically check edges
Fix: Before presenting code, run a mental checklist: What if input is None? Empty? Wrong type? At boundaries?

**Category 3: Over-engineering (item 4)**
Count: 4 occurrences
Pattern: I default to complex solutions
Root cause: Matching against enterprise patterns when simple patterns would suffice
Fix: Ask "what's the simplest thing that works?" before presenting

**Priority ranking by frequency:**
1. Edge cases/null handling: 11 errors — highest priority
2. Version staleness: 5 errors — medium priority
3. Over-engineering: 4 errors — lower priority

**The meta-insight:** The most frequent error (missing edge cases) is NOT about knowledge — it's about process. I KNOW about null handling. I just don't consistently CHECK for it. This requires a process fix, not a knowledge fix.
</think>

**Error Pattern Analysis**

**Categorized errors:**
| Category | Errors | Count | Root cause |
|----------|--------|-------|------------|
| Missing input validation | #2, #5 | 11 | Process gap (don't check edges) |
| Version staleness | #1, #3 | 5 | Knowledge gap (outdated info) |
| Over-engineering | #4 | 4 | Bias toward complexity |

**Key insight: My biggest error category is a PROCESS problem, not a knowledge problem.**

I know about null handling. I know about edge cases. But I don't consistently check for them. This means:
- More studying won't fix it (I already know the concept)
- A checklist WILL fix it (force the check every time)

**Fix for each category:**

**1. Edge cases/null handling (PROCESS fix):**
```
Pre-response checklist:
[ ] What if input is None/null?
[ ] What if input is empty ([], "", {}, 0)?
[ ] What if input is at boundary (min, max)?
[ ] What if input is wrong type?
```

**2. Version staleness (KNOWLEDGE fix):**
```
Rule: When mentioning language features, specify minimum version.
"Python dicts are ordered (since 3.7)"
"Use list[str] (Python 3.9+) or List[str] (older)"
```

**3. Over-engineering (BIAS fix):**
```
Rule: Present the simplest solution first.
Then: "If you need X at scale, consider adding Y."
```

**Process for ongoing improvement:**
1. Continue tracking errors by category
2. After implementing fixes, track if error rates decrease
3. If a category persists, the fix isn't working — try a different approach
4. New error categories will emerge — add them to the tracking system'''
    ),
    (
        "thinking/auto-metalearning-deliberate-practice",
        r'''What's the difference between just answering questions and deliberately practicing to get better at answering questions?''',
        r'''<think>
This is about the difference between experience and deliberate practice — a concept from expertise research (Anders Ericsson).

**Just answering questions (experience):**
- Answer the question
- Move to the next question
- Repeat for years
- Improvement plateaus quickly

**Deliberate practice:**
- Answer the question
- Evaluate the quality of the answer
- Identify what could be better
- Practice the specific weakness
- Track improvement over time

The key difference: deliberate practice includes a FEEDBACK LOOP. Without feedback, you just reinforce existing patterns (including bad ones).

**Applied to AI coding assistance:**
1. After each answer → self-evaluate (was it correct? complete? clear?)
2. Track patterns in errors → identify systematic weaknesses
3. Focus practice on weak areas → study the specific topics where I make errors
4. Measure improvement → are the same errors happening less?
</think>

**Experience vs Deliberate Practice**

**Experience (10,000 hours of mediocrity):**
```
Answer question → Next question → Next question → ...
No feedback loop. Same mistakes repeated. Plateau.
```

**Deliberate practice (actual improvement):**
```
Answer question → Self-evaluate → Identify weakness →
Practice weakness → Re-evaluate → Next question
Feedback loop. Errors decrease. Continuous improvement.
```

**The 4 components of deliberate practice for coding assistance:**

**1. Focused attention on weak spots**
```
Don't just answer more questions.
Specifically practice the types of questions you get wrong.

If edge cases are your weakness:
→ Practice by ONLY doing edge case analysis for a week
→ For every function, enumerate all boundary inputs before writing code
```

**2. Immediate feedback**
```
After every answer, ask:
- Was the code correct? (Run it mentally or actually)
- Did I miss any edge cases?
- Was it the simplest solution?
- Was my confidence calibrated?
```

**3. Practice at the edge of ability**
```
Easy questions don't improve you.
Impossible questions don't either.
The sweet spot: questions where you're 60-80% likely to get it right.
That's where learning happens.
```

**4. Track and measure**
```
Week 1: Edge case errors in 6/20 answers (30%)
Week 2: Added pre-response checklist → 3/20 (15%)
Week 3: Checklist becoming automatic → 2/20 (10%)
Week 4: New error pattern emerging → adjust practice
```

**The meta-lesson:** Answering 10,000 questions doesn't make you an expert. Answering 100 questions with deliberate self-evaluation, tracking, and targeted improvement does. Quality of practice > quantity of practice.'''
    ),
    (
        "thinking/auto-metalearning-cognitive-biases",
        r'''What cognitive biases affect my code suggestions, and how do I counteract them?''',
        r'''<think>
Let me identify biases that specifically affect code suggestions:

1. **Anchoring bias** — I anchor to the first solution I think of and don't explore alternatives
2. **Availability bias** — I suggest tools I've seen most frequently in training, not necessarily the best ones
3. **Complexity bias** — I prefer elaborate solutions over simple ones (feels more thorough)
4. **Recency bias** — I favor newer/trendier technologies over proven ones
5. **Confirmation bias** — Once I decide on an approach, I look for evidence it's right rather than looking for reasons it's wrong
6. **Sunk cost fallacy** — If I've started explaining a complex solution, I continue rather than restarting with a simpler one
7. **Bandwagon effect** — I recommend what's popular (React, TypeScript, Docker) regardless of fit
</think>

**Cognitive Biases in Code Suggestions**

| Bias | How it manifests | Counteraction |
|------|-----------------|---------------|
| **Anchoring** | First solution dominates thinking | Force 3 alternatives before choosing |
| **Availability** | Suggest most-seen tools, not best-fit | Ask "what's the simplest tool for this specific problem?" |
| **Complexity** | Over-engineer solutions | "Can I remove a component and still solve it?" |
| **Recency** | Favor trendy tech | "Has a proven tool done this for 10 years?" |
| **Confirmation** | Defend chosen approach | "What's the strongest argument AGAINST my suggestion?" |
| **Sunk cost** | Continue with bad approach | "If I started over, would I choose this same approach?" |
| **Bandwagon** | Recommend popular tech | "Is this popular because it's good, or good because it's popular?" |

**Practical counteraction protocol:**

**Before suggesting a technology:**
```
1. Generate 3 alternatives (fights anchoring)
2. For each, list one strength and one weakness (fights confirmation)
3. Include at least one "boring" option (fights recency/bandwagon)
4. Ask: "Which is simplest for THIS specific problem?" (fights complexity)
```

**Before suggesting architecture:**
```
1. Start with the simplest possible architecture
2. Add complexity ONLY when you can name the specific problem it solves
3. Ask: "If this were my personal project with my time, would I do this?"
   (Removes the bias toward impressing vs. solving)
```

**Self-check question:**
"Am I suggesting this because it's the best solution, or because it's the solution I know best?"

If the honest answer is "it's what I know best" — pause and research alternatives.'''
    ),
    (
        "thinking/auto-metalearning-generalize-from-specific",
        r'''I just learned that Python's `os.path.join('uploads', user_input)` is vulnerable to path traversal. How do I generalize this into a broader security principle?''',
        r'''<think>
The specific vulnerability: if `user_input` is `../../etc/passwd`, `os.path.join` doesn't sanitize it, so the resulting path escapes the intended directory.

Let me generalize at multiple levels:

**Level 1 (specific):** Don't use user input in file paths without sanitization.

**Level 2 (broader):** Don't use user input in any system resource identifier (file paths, URLs, SQL queries, command arguments) without sanitization.

**Level 3 (principle):** User input is always untrusted. Any place user input flows into a system operation is a potential injection point.

**Level 4 (meta-principle):** Whenever data crosses a trust boundary (user → server, server → database, service → service), validate and sanitize it.

**Analogous vulnerabilities (same principle, different context):**
- File path: path traversal → use secure_filename()
- SQL query: SQL injection → use parameterized queries
- Shell command: command injection → use subprocess with list args, not shell=True
- URL: SSRF → validate URL scheme and hostname
- HTML: XSS → escape user input in templates
- HTTP header: header injection → validate/encode header values

All of these are the SAME bug: untrusted input flowing into a system operation without sanitization.
</think>

**Generalizing: File Path Traversal → Trust Boundary Principle**

**Level 1: The specific bug**
```python
# Vulnerable:
path = os.path.join('uploads', user_input)  # user_input = "../../etc/passwd"

# Fixed:
from werkzeug.utils import secure_filename
path = os.path.join('uploads', secure_filename(user_input))
```

**Level 2: The pattern (injection via system identifiers)**
| System resource | Attack | Defense |
|----------------|--------|---------|
| File path | Path traversal | `secure_filename()` or UUID |
| SQL query | SQL injection | Parameterized queries |
| Shell command | Command injection | `subprocess` with list args |
| URL | SSRF | Allowlist schemes/hosts |
| HTML | XSS | Template auto-escaping |
| HTTP headers | Header injection | Validate/encode |

**Level 3: The principle**
> **Any place user input flows into a system operation is an injection point.** Sanitize at the boundary between untrusted data and system operations.

**Level 4: The meta-principle**
> **Data crossing trust boundaries must be validated.** Trust boundaries exist between: user → server, server → database, service → service, frontend → backend.

**How to apply this generalization:**

When writing ANY code that takes user input, ask:
1. Where does this input end up? (file system, database, shell, HTTP, HTML)
2. What could a malicious input do? (escape the intended context)
3. What sanitization exists at that boundary? (secure_filename, parameterized queries, escaping)

**The meta-learning process:**
```
Specific bug (path traversal)
    → Pattern (injection via identifiers)
    → Principle (sanitize at trust boundaries)
    → Mental model (data flow + trust boundaries)
```

One specific vulnerability, once generalized, protects against an entire CLASS of vulnerabilities. This is the value of extracting principles from specific experiences.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
