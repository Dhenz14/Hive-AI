"""Phase 4B: Self-Improvement — Self-Evaluation (Part 2)

The model evaluates its own outputs for quality, rating and improving them.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-rate-own-response-quality",
        r'''I need to evaluate the quality of my own response before sending it. Here's my draft answer to "What's the difference between == and === in JavaScript?":

"== compares values with type coercion, === compares without type coercion. Always use ===."

Rate this response 1-10 and improve it if needed.''',
        r'''<think>
Let me self-evaluate this response:

**Accuracy:** Technically correct but oversimplified. == does perform type coercion, === does not. But just saying "type coercion" doesn't help someone who doesn't know what that means.

**Completeness:** Low. Missing:
- What IS type coercion? (examples showing surprising behaviors)
- WHY === is preferred (predictability, fewer bugs)
- When == might be intentionally used (checking for null/undefined)
- Common gotchas with == ('' == 0, null == undefined, etc.)

**Actionability:** "Always use ===" is good advice but too absolute. `value == null` is a common and acceptable pattern to check for both null and undefined.

**Depth:** Very shallow. A one-liner doesn't teach understanding.

Rating: 3/10. Technically correct but doesn't teach the user anything.
</think>

**Self-evaluation: 3/10 — Correct but too shallow to be useful.**

| Criterion | Score | Issue |
|-----------|-------|-------|
| Accuracy | 4/5 | Correct core concept |
| Completeness | 1/5 | Missing examples, gotchas, exceptions |
| Depth | 1/5 | One-liner doesn't teach understanding |
| Actionability | 3/5 | "Always use ===" is too absolute |

**Improved response:**

`==` (loose equality) converts types before comparing. `===` (strict equality) compares type AND value.

```javascript
// == surprises (type coercion):
'' == 0          // true  (empty string → 0)
'0' == 0         // true  (string → number)
false == 0       // true  (boolean → number)
null == undefined // true  (special case in spec)
[] == false      // true  (array → string → number)

// === is predictable (no coercion):
'' === 0          // false (string ≠ number)
'0' === 0         // false
false === 0       // false
null === undefined // false
```

**Rule: Use `===` by default.** One exception: `value == null` is a clean way to check for both `null` and `undefined`:
```javascript
if (value == null) { ... }  // Catches null AND undefined
// Equivalent to: if (value === null || value === undefined)
```

**Self-evaluation improvement:** +7 points by adding examples showing WHY the distinction matters, not just WHAT it is.'''
    ),
    (
        "thinking/auto-selfeval-detect-own-hallucination",
        r'''I'm about to answer a question about Python's match statement. Let me evaluate my knowledge confidence:

User asked: "Can I use match/case with custom classes in Python?"

My draft: "Yes, you can use structural pattern matching with custom classes. Python 3.10+ supports match/case with __match_args__ to define positional patterns:

```python
class Point:
    __match_args__ = ('x', 'y')
    def __init__(self, x, y):
        self.x = x
        self.y = y

match point:
    case Point(0, 0):
        print('origin')
    case Point(x, 0):
        print(f'on x-axis at {x}')
    case Point(0, y):
        print(f'on y-axis at {y}')
    case Point(x, y):
        print(f'at ({x}, {y})')
```"

Is this accurate?''',
        r'''<think>
Let me self-evaluate my confidence in this answer:

**What I'm confident about:**
- Python 3.10 introduced structural pattern matching (match/case) ✓
- Custom classes can be used with match/case ✓
- `__match_args__` defines positional pattern matching for classes ✓
- The Point example is the canonical example from PEP 634 ✓
- The syntax `case Point(0, 0)` matches by position ✓

**What I should double-check:**
- Does the class need `__match_args__` to work with match/case?
  → For positional matching: yes. For keyword matching: no, you can do `case Point(x=0, y=0)` without `__match_args__`.
- Does this work with dataclasses?
  → Yes, dataclasses automatically set `__match_args__` based on field order.
- Am I missing any important caveats?
  → The matched variables (`x`, `y`) are bindings, not comparisons. `case Point(x, 0)` binds x, doesn't compare to an existing variable named x.

**Hallucination risk assessment:**
- Low risk on the core example — it's from PEP 634 documentation
- Medium risk on edge cases I haven't mentioned
- I should mention dataclasses and keyword patterns as additional context

**Verdict:** The answer is accurate. I should add a note about dataclasses and keyword patterns for completeness.
</think>

**Self-evaluation: Accurate. Confidence: 9/10.**

The core example is correct — it's directly from PEP 634. Two additions for completeness:

**Addition 1: Dataclasses work automatically:**
```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float
    # __match_args__ is set automatically: ('x', 'y')

match point:
    case Point(0, 0):
        print('origin')
```

**Addition 2: Keyword patterns don't need __match_args__:**
```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    # No __match_args__ needed for keyword matching:

match point:
    case Point(x=0, y=0):   # Keyword pattern
        print('origin')
```

**Hallucination check applied:**
1. ✅ Core syntax verified against PEP 634
2. ✅ `__match_args__` behavior confirmed
3. ✅ Edge cases (dataclasses, keyword patterns) validated
4. ⚠️ Note: matched variables are bindings, not comparisons — should mention this if relevant

**My confidence calibration was correct here — high confidence on a well-documented feature. When I'm less confident (newer features, obscure edge cases), I should flag uncertainty explicitly.**'''
    ),
    (
        "thinking/auto-selfeval-check-own-debugging-advice",
        r'''I just generated debugging advice for a user whose Python script is slow. Let me evaluate it:

"Your script is slow because Python is an interpreted language. To make it faster:
1. Rewrite the hot path in C using ctypes
2. Use Cython to compile Python to C
3. Switch to PyPy for JIT compilation"

Is this good debugging advice?''',
        r'''<think>
Let me self-evaluate this debugging advice:

**Problem #1: Jumped to solutions without diagnosing.**
I have no idea WHY the script is slow. It could be:
- An O(n²) algorithm that should be O(n)
- A database query missing an index
- Reading a large file into memory instead of streaming
- Network I/O without concurrency
- A tight loop creating unnecessary objects

"Python is interpreted" is rarely the bottleneck for real applications. The bottleneck is almost always algorithmic or I/O-related.

**Problem #2: Solutions are nuclear options.**
Rewriting in C, using Cython, or switching runtimes are last resorts. They add massive complexity. 95% of performance issues are fixed by:
- Better algorithms
- Adding database indexes
- Using built-in functions (written in C) instead of Python loops
- Caching expensive computations
- Using appropriate data structures

**Problem #3: No profiling step.**
I didn't suggest measuring where the time is spent. Without profiling, any optimization is guessing.

**Verdict:** This is terrible debugging advice. It skips diagnosis, jumps to extreme solutions, and doesn't address the actual likely causes of slowness. Rating: 1/10.
</think>

**Self-evaluation: TERRIBLE advice. Rating: 1/10.**

| Issue | Severity |
|-------|----------|
| No profiling/diagnosis step | Critical |
| "Python is interpreted" as root cause | Wrong premise |
| Solutions are nuclear options | Overkill for 95% of cases |
| No mention of algorithmic optimization | Major omission |

**Corrected advice I should present:**

"Let's find out WHY it's slow before optimizing:

**Step 1: Profile it**
```python
# Quick timing
import time
start = time.perf_counter()
# ... your code ...
print(f'Took {time.perf_counter() - start:.3f}s')

# Detailed profiling
python -m cProfile -s cumulative your_script.py
```

**Step 2: Fix the actual bottleneck (most common causes):**
1. **O(n²) algorithm** → find and fix the nested loop
2. **Missing database index** → add index, check with EXPLAIN
3. **Loading large files into memory** → use streaming/generators
4. **No caching** → cache expensive computations
5. **Python loops over data** → use NumPy/pandas vectorized operations
6. **Serial I/O** → use asyncio or threading for concurrent operations

**Step 3: Only if Python itself is the bottleneck** (rare):
- Use built-in functions (map, filter, list comprehensions)
- Use NumPy for numerical work
- Last resort: Cython, C extensions, or PyPy"

**Self-evaluation lesson:** Always profile before optimizing. Never suggest rewriting in C as a first step.'''
    ),
    (
        "thinking/auto-selfeval-check-own-test-coverage",
        r'''I just wrote tests for a password validation function. Let me evaluate whether my tests are sufficient:

```python
def test_valid_password():
    assert validate_password("SecurePass123!") == True

def test_too_short():
    assert validate_password("Ab1!") == False

def test_no_uppercase():
    assert validate_password("securepass123!") == False
```

The function validates passwords require: 8+ chars, uppercase, lowercase, number, special char. Are these tests complete?''',
        r'''<think>
Let me self-evaluate my test coverage:

**Requirements:**
1. At least 8 characters
2. At least one uppercase letter
3. At least one lowercase letter
4. At least one number
5. At least one special character

**What I'm testing:**
- ✅ Valid password (all requirements met)
- ✅ Too short (requirement 1)
- ✅ No uppercase (requirement 2)

**What I'm NOT testing:**
- ❌ No lowercase (requirement 3)
- ❌ No number (requirement 4)
- ❌ No special character (requirement 5)
- ❌ Empty string
- ❌ Just spaces
- ❌ Exactly 8 characters (boundary)
- ❌ Exactly 7 characters (boundary)
- ❌ Very long password (100+ chars)
- ❌ Unicode characters (é, ñ, 中文)
- ❌ Password that's all special chars
- ❌ None input

**Coverage assessment:**
- Requirement coverage: 2/5 (40%)
- Boundary testing: 0/3 (0%)
- Edge case testing: 0/4 (0%)

**Verdict:** Tests cover only 2 of 5 requirements. No boundary or edge case tests. This is insufficient — I could ship a bug where passwords without numbers or special characters are accepted.
</think>

**Self-evaluation: Tests are INCOMPLETE. Coverage: 2/5 requirements tested.**

| Requirement | Tested? | Missing test |
|-------------|---------|-------------|
| 8+ characters | ✅ | — |
| Uppercase | ✅ | — |
| Lowercase | ❌ | Need test with no lowercase |
| Number | ❌ | Need test with no digits |
| Special char | ❌ | Need test with no special chars |
| Boundary (exactly 8) | ❌ | Need test at exact boundary |
| Edge cases | ❌ | Empty, None, Unicode, spaces |

**Complete test suite:**
```python
# Happy path
def test_valid_password():
    assert validate_password("SecurePass123!") == True

# Each requirement individually
def test_too_short():
    assert validate_password("Ab1!aaa") == False  # 7 chars

def test_exactly_eight():
    assert validate_password("Abcde1!a") == True  # Boundary

def test_no_uppercase():
    assert validate_password("securepass123!") == False

def test_no_lowercase():
    assert validate_password("SECUREPASS123!") == False

def test_no_number():
    assert validate_password("SecurePass!!!") == False

def test_no_special_char():
    assert validate_password("SecurePass123") == False

# Edge cases
def test_empty_string():
    assert validate_password("") == False

def test_none_input():
    with pytest.raises((TypeError, ValueError)):
        validate_password(None)

def test_only_spaces():
    assert validate_password("        ") == False

def test_very_long():
    assert validate_password("A" * 100 + "a1!") == True
```

**Self-evaluation lesson:** For validation functions, test each rule independently AND test boundary values. Missing a single requirement test means that requirement could be silently broken.'''
    ),
    (
        "thinking/auto-selfeval-detect-bias-in-recommendation",
        r'''I'm about to recommend a tech stack. Let me check for bias first:

User asked: "I'm building a blog. What tech should I use?"

My draft: "Use Next.js with TypeScript, Tailwind CSS, Prisma ORM, PostgreSQL, and deploy on Vercel. This is the best modern stack for blogs."

Am I being biased?''',
        r'''<think>
Let me check for bias in my recommendation:

**Bias check 1: Recency bias**
Am I recommending this because it's trendy, or because it's actually the best fit? Next.js is extremely popular right now. But for a BLOG, there are simpler options that have existed for years and work perfectly.

**Bias check 2: Complexity bias**
A blog is content-focused. My recommendation involves: a React framework, a typed language, a utility CSS framework, an ORM, a database, and a cloud platform. That's 6 technologies for... displaying text and images.

**Bias check 3: Developer-centric vs user-centric**
This stack is great for DEVELOPERS who want to learn modern tools. But for a user who just wants a blog, it's massive overkill. A WordPress site, a static site generator (Hugo, Jekyll, Astro), or even Medium/Substack would be up and running in hours, not days.

**Bias check 4: "Best" claim**
"This is the best modern stack" is an absolute claim I can't justify. Best for whom? A developer learning Next.js? A non-technical person? A writer who needs SEO?

**What I should ask first:**
- Are you a developer or non-technical?
- Do you want to learn coding, or just write?
- How important is customization vs speed to launch?
- What's your budget?

**Verdict:** I'm heavily biased toward a developer-friendly stack. For most people building a blog, simpler options are dramatically better.
</think>

**Bias check: YES, I'm biased toward a developer-friendly stack.**

| Bias type | Present? | Evidence |
|-----------|----------|---------|
| Recency bias | ✅ | Next.js is trendy, not necessarily optimal |
| Complexity bias | ✅ | 6 technologies for displaying text |
| Developer-centrism | ✅ | Optimized for developer experience, not user needs |
| Absolute claim | ✅ | "This is the best" without knowing the user |

**A blog needs:** text, images, SEO, maybe comments. That's it.

**Corrected recommendation — ask first, then suggest:**

"What kind of blog and who are you?

**Non-technical writer:** Use WordPress.com, Ghost, or Substack. Up in 10 minutes, focus on writing.

**Developer who wants simplicity:** Use a static site generator:
- **Astro** or **Hugo** — fast, simple, deploy to Netlify for free
- Write posts in Markdown, zero database needed

**Developer who wants to learn:** Use Next.js + MDX (my original suggestion). More complex but teaches modern web dev.

**Developer who needs dynamic features** (user accounts, comments, payments): Then yes, Next.js + PostgreSQL makes sense."

**Self-evaluation lesson:** Before recommending a tech stack, ask about the user's skills, goals, and constraints. Don't assume everyone wants to write code. The best technology is the one that solves the problem with the least complexity.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
