"""Phase 4B: Self-Improvement — Self-Evaluation (Part 4)

The model evaluates its own outputs for tone, scope, and pedagogical quality.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-check-tone-condescending",
        r'''Let me evaluate the tone of my draft response before sending. User asked: "What's a for loop?"

My draft: "A for loop is one of the most basic programming concepts. It simply iterates over a collection. Here's a trivial example:

```python
for i in range(5):
    print(i)
```

This is elementary — it just prints 0 through 4. Any beginner should be able to understand this."

Is the tone appropriate?''',
        r'''<think>
Let me evaluate the tone:

**Words that are condescending:**
- "one of the most basic" — implies the user should already know this
- "simply iterates" — "simply" dismisses the learner's difficulty
- "trivial example" — calling it trivial makes the learner feel dumb for asking
- "elementary" — same as "basic" — implies it's beneath discussion
- "Any beginner should be able to understand" — if they're asking, they DON'T understand yet. This makes them feel inadequate.

**Tone assessment:** Condescending. The user asked a genuine question and my response implies they should already know the answer. Words like "basic," "simply," "trivial," and "elementary" are red flags in educational content.

**Good teaching tone:**
- Assumes the question is reasonable
- Explains without judgment
- Builds understanding step by step
- Never implies the learner should already know something

**Verdict:** The tone is condescending and would make a beginner feel bad for asking. Rewrite without dismissive language. Rating: 2/10 for tone.
</think>

**Tone check: CONDESCENDING. Rating: 2/10.**

**Problematic words:**
| Word/phrase | Problem |
|-------------|---------|
| "most basic" | Implies they should know this already |
| "simply" | Dismisses the learning difficulty |
| "trivial" | Makes the concept seem beneath discussion |
| "elementary" | Same as "basic" — condescending |
| "Any beginner should" | Makes them feel inadequate |

**Rewritten with respectful tone:**
"A `for` loop lets you repeat an action for each item in a collection:

```python
for i in range(5):
    print(i)
# Output: 0, 1, 2, 3, 4
```

`range(5)` generates numbers 0 through 4. The loop runs `print(i)` once for each number.

You can loop over any collection:
```python
names = ['Alice', 'Bob', 'Carol']
for name in names:
    print(f'Hello, {name}!')
```

The pattern is: `for item in collection:` — do something with each `item`."

**What changed:**
- Removed all judgment words (basic, simple, trivial, elementary)
- Showed the output (learners need to see what code produces)
- Added a second example with real data (not just numbers)
- Explained the pattern, not just the example'''
    ),
    (
        "thinking/auto-selfeval-check-scope-creep",
        r'''The user asked "How do I center a div?" Let me evaluate if my response has scope creep:

My draft: "There are multiple ways to center a div in CSS. You should understand the box model first — every element has margin, border, padding, and content. CSS has evolved through several layout systems: tables (90s), floats (2000s), flexbox (2012), and grid (2017). The cascade determines which styles apply based on specificity, which has three levels...

For centering, here's the historical evolution:
1. margin: 0 auto (old way)
2. position: absolute + transform (hacky)
3. display: flex + justify-content + align-items (modern)
4. display: grid + place-items: center (newest)

Each approach has different browser support considerations. Let me explain the CSS cascade first so you understand why your styles might not apply..."''',
        r'''<think>
Let me evaluate scope:

**What the user asked:** How to center a div.
**What I'm giving them:** A history of CSS layout, the box model, specificity, the cascade, AND four different centering approaches with browser support discussion.

**Scope creep assessment:**
- Box model explanation: NOT NEEDED for centering a div
- CSS history: NOT NEEDED — the user didn't ask for history
- Cascade/specificity: NOT NEEDED — the user asked about centering
- Four historical approaches: EXCESSIVE — give the best modern approach first
- Browser support discussion: NOT NEEDED unless they specified legacy browser requirements

The user asked a simple question. They want to center a div RIGHT NOW. My response is a CSS textbook chapter.

**The "curse of knowledge" problem:** I know a lot about CSS, so I want to share all of it. But the user just wants the answer.

**Verdict:** Massive scope creep. The answer should be 5 lines, not a CSS history lesson. Rating: 2/10 for scope management.
</think>

**Scope check: MASSIVE scope creep. Rating: 2/10.**

**User asked:** How to center a div.
**I wrote:** A CSS history textbook.

| Content | Needed? | Why not |
|---------|---------|---------|
| Box model | No | Not needed for centering |
| CSS history | No | User didn't ask |
| Cascade/specificity | No | Unrelated to centering |
| 4 different approaches | Excessive | Give the best one first |
| Browser support | No | Unless they asked |

**Right-sized answer:**
```css
/* Horizontal + vertical centering (modern): */
.parent {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* Or with grid (even shorter): */
.parent {
  display: grid;
  place-items: center;
}
```

That's it. If they want to know about older approaches or the CSS box model, they'll ask.

**Self-evaluation rule:** If the user asked a specific question, answer that question first. Add context only if it's directly relevant. A focused 5-line answer is more helpful than a comprehensive 50-line essay.'''
    ),
    (
        "thinking/auto-selfeval-check-missing-warning",
        r'''I'm about to show this code for downloading files from URLs. Let me check if I'm missing any important warnings:

```python
import requests

def download_file(url, destination):
    response = requests.get(url)
    with open(destination, 'wb') as f:
        f.write(response.content)
    return destination
```

"Here's how to download a file from a URL in Python."''',
        r'''<think>
Let me check what warnings I should include:

**Security warnings:**
1. If `url` comes from user input, this is a Server-Side Request Forgery (SSRF) risk. The user's code could be used to probe internal network resources (http://169.254.169.254 for cloud metadata, http://localhost:8080/admin, etc.)
2. If `destination` comes from user input, it's a path traversal risk (writing to arbitrary paths).
3. No SSL verification consideration — should probably keep it on but mention it exists.

**Robustness warnings:**
4. `response.content` loads the ENTIRE file into memory. For large files (GB), this causes OOM. Should use `stream=True` and iterate in chunks.
5. No error handling for network failures, 404s, etc.
6. No timeout — could hang forever on slow/dead servers.

**Important missing feature:**
7. No progress indicator for large downloads.

Should I include all of these? Depends on context:
- If this is a tutorial: mention streaming for large files and basic error handling
- If the user is downloading trusted URLs: security is less critical
- If the user is building a service that accepts URLs: SSRF warning is critical

Since I don't know the context, I should at least mention: (1) streaming for large files, (2) timeout, and (3) error handling. SSRF is worth mentioning briefly.

**Verdict:** Missing important warnings about memory usage, timeouts, and error handling. Rating: 4/10 for the response.
</think>

**Self-evaluation: Missing important warnings. Rating: 4/10.**

| Warning | Included? | Severity |
|---------|-----------|----------|
| Large files OOM (no streaming) | ❌ | High |
| No timeout (hangs forever) | ❌ | Medium |
| No error handling | ❌ | Medium |
| SSRF if URL from user input | ❌ | Context-dependent |
| Path traversal if dest from user | ❌ | Context-dependent |

**Improved answer with warnings:**

```python
import requests

def download_file(url, destination, timeout=30):
    """Download a file from a URL to a local path."""
    response = requests.get(url, stream=True, timeout=timeout)
    response.raise_for_status()  # Raise on 4xx/5xx

    with open(destination, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)  # Stream in chunks, don't load all into memory

    return destination
```

**Key improvements:**
- `stream=True` + `iter_content`: handles files of any size without OOM
- `timeout=30`: won't hang forever
- `raise_for_status()`: fails loudly on HTTP errors

**Warning for user-provided URLs:**
If `url` comes from user input, validate it first to prevent SSRF:
```python
from urllib.parse import urlparse
parsed = urlparse(url)
if parsed.hostname in ('localhost', '127.0.0.1') or parsed.hostname.startswith('169.254'):
    raise ValueError("Internal URLs not allowed")
```'''
    ),
    (
        "thinking/auto-selfeval-evaluate-code-suggestion",
        r'''I'm reviewing my own code suggestion before presenting it. The user asked for a function to remove duplicates from a list while preserving order.

My suggestion:
```python
def remove_duplicates(items):
    return list(dict.fromkeys(items))
```

Is this good code to suggest?''',
        r'''<think>
Let me evaluate my suggestion:

**Correctness:**
- `dict.fromkeys(items)` creates a dict with keys from items (values are None). Since dict preserves insertion order (Python 3.7+), converting back to list gives unique items in original order. ✓
- Edge cases: empty list → empty list ✓, single item → single item ✓, all duplicates → one item ✓

**Performance:**
- O(n) time (dict insertion is O(1) average) ✓
- Better than the naive O(n²) nested loop approach

**Readability:**
- Clever but not immediately obvious. Someone reading `dict.fromkeys(items)` might not understand why a dict is being used to deduplicate a list.
- A set-based approach might be clearer:
```python
def remove_duplicates(items):
    seen = set()
    return [x for x in items if x not in seen and not seen.add(x)]
```
Wait, that's even less readable (abusing `set.add` returning None).

**Best version for readability:**
```python
def remove_duplicates(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
```
This is O(n) and immediately clear.

**Requirements check:**
- Items must be hashable (both dict.fromkeys and set require hashable items). If items are dicts or lists, both approaches fail. Should mention this.

**Verdict:** My suggestion works and is concise, but I should present the explicit version as the primary recommendation and mention dict.fromkeys as a shortcut.
</think>

**Self-evaluation: Correct but not the clearest suggestion. Rating: 6/10.**

| Criterion | Score | Notes |
|-----------|-------|-------|
| Correctness | 5/5 | Works for all hashable types |
| Performance | 5/5 | O(n) time |
| Readability | 2/5 | `dict.fromkeys` trick isn't obvious |
| Teachability | 2/5 | Doesn't help user understand the approach |

**Better recommendation — explicit version first, trick second:**

```python
# Clear and explicit (recommended):
def remove_duplicates(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

# Concise alternative (Python 3.7+):
def remove_duplicates(items):
    return list(dict.fromkeys(items))
```

**Note:** Both require items to be hashable (strings, numbers, tuples). For unhashable items (dicts, lists), you'd need a different approach.

**Self-evaluation lesson:** When suggesting code, prioritize readability over cleverness. Show the clear version first, then mention the concise trick as an alternative. A user who understands the explicit version can appreciate the shortcut; a user who only sees the shortcut learns nothing.'''
    ),
    (
        "thinking/auto-selfeval-retrospective-multi-step",
        r'''I just completed a multi-step task: helping a user set up a Flask API with authentication. Let me do a retrospective on my own performance.

Steps I took:
1. Created the Flask app structure
2. Added SQLAlchemy models for User
3. Implemented registration endpoint
4. Implemented login endpoint with JWT
5. Added a protected endpoint with @jwt_required

Now let me evaluate: did I do a good job?''',
        r'''<think>
Let me do a retrospective self-evaluation:

**Step 1 — App structure:**
- Did I create a well-organized structure? (app/, models/, routes/, config.py)
- Or did I dump everything in one file?
- If one file: acceptable for a tutorial, bad for a real project

**Step 2 — User model:**
- Did I use proper password hashing (bcrypt/argon2)?
- Did I include created_at, updated_at fields?
- Did I add unique constraint on email?
- Did I add proper indexes?

**Step 3 — Registration:**
- Did I validate input (email format, password strength)?
- Did I handle duplicate email gracefully?
- Did I hash the password before storing?
- Did I return appropriate status codes (201 Created)?

**Step 4 — Login with JWT:**
- Did I use a strong secret key (from env var, not hardcoded)?
- Did I set reasonable token expiration?
- Did I handle wrong credentials with proper error messages?
- Did I use timing-safe password comparison?

**Step 5 — Protected endpoint:**
- Did I demonstrate how to extract user info from the token?
- Did I handle expired tokens gracefully?
- Did I show proper 401 response for missing/invalid tokens?

**What I probably missed (common gaps):**
- Rate limiting on login (brute force protection)
- Password reset flow
- CORS configuration
- Token refresh mechanism
- Logout (token blacklist)
- Input sanitization
- Tests

**Verdict:** I should check each step against these criteria. Even if the user didn't ask for rate limiting, I should at least mention it as a security consideration.
</think>

**Self-evaluation retrospective:**

| Step | Quality check | Status |
|------|-------------|--------|
| App structure | Organized or single file? | Check |
| User model | bcrypt? unique email? indexes? | Check |
| Registration | Input validation? duplicate handling? 201 status? | Check |
| Login | Strong secret? expiration? timing-safe comparison? | Check |
| Protected route | Token extraction? 401 handling? | Check |

**Common gaps I should verify I addressed:**

**Security (must-have):**
- [ ] Password hashed with bcrypt (not SHA-256, not plain text)
- [ ] JWT secret from environment variable (not hardcoded)
- [ ] Token expiration set (1 hour, not 24 hours)
- [ ] Input validation on registration (email format, password length)
- [ ] Duplicate email returns 409 Conflict (not 500 error)

**Security (should mention):**
- [ ] Rate limiting on login endpoint
- [ ] CORS configuration if frontend is on different domain
- [ ] Token refresh mechanism for long sessions
- [ ] Mention that logout requires a token blacklist

**Code quality:**
- [ ] Proper HTTP status codes (201, 401, 409)
- [ ] Consistent error response format
- [ ] Environment-based configuration
- [ ] At least one test example

**Self-evaluation outcome:** If I missed password hashing or hardcoded the JWT secret, those are critical issues I need to fix before the user deploys this. If I missed rate limiting, I should at least add a comment noting it's needed for production.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
