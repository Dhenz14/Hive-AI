"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 11)

Autonomously improving code review feedback — making code review
comments more actionable, educational, and appropriately prioritized.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-code-review-actionability",
        r'''My code review comments often identify problems but don't help the author fix them. How do I make my code review feedback more actionable?''',
        r'''<think>
The most common code review anti-pattern is pointing out what's wrong without explaining how to fix it. This leaves the author frustrated and unsure how to proceed. Actionable feedback means the author can immediately act on the comment without needing a follow-up conversation.

**Actionable feedback includes:**
1. What's wrong (the problem)
2. Why it matters (the impact)
3. How to fix it (specific suggestion)
4. Example code (when possible)

**Common non-actionable patterns:**
- "This could be better" (how?)
- "Consider refactoring this" (into what?)
- "This isn't clean" (what would clean look like?)
- "There might be a performance issue here" (where? how bad? what to do?)
</think>

**Making Code Review Comments Actionable**

**The actionable comment formula:**

```
[WHAT's wrong] + [WHY it matters] + [HOW to fix it]

NON-ACTIONABLE:
  "This function is too long."

ACTIONABLE:
  "This function is 80 lines with 3 distinct responsibilities:
   validation (lines 5-25), transformation (lines 26-55), and
   persistence (lines 56-80). Consider extracting each into a
   separate function:

   def validate_order(order): ...
   def transform_order(order): ...
   def persist_order(order): ...

   This makes each part independently testable."
```

**Non-actionable vs. actionable side-by-side:**

| Non-actionable | Actionable |
|----------------|------------|
| "This SQL is vulnerable" | "This query uses string concatenation, which allows SQL injection. Use parameterized queries: `cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))`" |
| "Add error handling" | "If `requests.get()` fails (network error, timeout), this will crash. Wrap in try/except: `try: resp = requests.get(url, timeout=5) except requests.RequestException as e: logger.error(f'API call failed: {e}'); return None`" |
| "This isn't idiomatic" | "In Python, prefer `items = [x for x in data if x.active]` over the manual loop with append. It's more readable and slightly faster." |
| "Consider caching this" | "This database query runs on every request but the data changes rarely. Consider caching with a 5-minute TTL: `@cache(ttl=300) def get_config(): ...`" |
| "Naming could be better" | "Rename `d` to `user_data` and `fn` to `format_name` — the current names require reading the function body to understand." |

**The three levels of code review comments:**

```
Level 1: MUST FIX (blocking issues)
  Security vulnerabilities, data loss risks, broken functionality.
  "This stores passwords in plaintext. Use bcrypt:
   hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())"
  → Always include the fix. These can't be left to interpretation.

Level 2: SHOULD FIX (quality issues)
  Performance problems, maintainability concerns, missing tests.
  "This N+1 query will be slow with many users. Use a JOIN:
   SELECT users.*, orders.* FROM users JOIN orders ON ..."
  → Include the fix and explain the impact.

Level 3: COULD FIX (suggestions/nitpicks)
  Style preferences, minor improvements, alternative approaches.
  "Nit: Consider using f-strings instead of .format() for readability.
   This is minor — approve either way."
  → Mark these clearly as optional.
```

**The code suggestion technique:**
```
Instead of describing the fix in words, SHOW the fix in code:

WORDS ONLY (less actionable):
  "You should use a context manager for the file handling
   to ensure it gets closed properly."

CODE INCLUDED (more actionable):
  "Use a context manager to ensure the file is always closed:

   # Instead of:
   f = open('data.txt')
   data = f.read()
   f.close()  # won't execute if an exception occurs above

   # Use:
   with open('data.txt') as f:
       data = f.read()
   # File is automatically closed, even on exception"
```

**The self-check before submitting a review:**
```
For each comment, ask:
□ Can the author fix this based solely on my comment?
□ Did I explain WHY, not just WHAT?
□ Did I include example code where helpful?
□ Did I mark the priority (must/should/could)?
□ Is my tone collaborative, not condescending?

If any answer is no, revise the comment before posting.
```

**The meta-principle:** Code review comments are instructions, not observations. "This is wrong" is an observation. "This is wrong because X, fix it by doing Y" is an instruction. Every comment should leave the author with a clear next action, not a puzzle to solve.'''
    ),
    (
        "thinking/auto-autonomous-code-review-educational",
        r'''How do I make my code review comments educational rather than just corrective? I want the author to learn from the review, not just fix the immediate issue.''',
        r'''<think>
Educational code reviews transform a correction into a learning moment. The difference is between "fix this" and "here's why this matters and how to think about it in the future." The goal is that after the review, the author won't make the same class of mistake again.

**What makes feedback educational:**
1. Explain the PRINCIPLE behind the fix (not just the fix)
2. Show the CONSEQUENCES of the current approach (not just "it's wrong")
3. Connect to broader concepts (design patterns, principles)
4. Ask questions that lead to understanding (Socratic method)
5. Share the REASONING, not just the conclusion
</think>

**Making Code Review Comments Educational**

**The educational comment structure:**
```
1. Point out the issue (WHAT)
2. Explain the principle (WHY — the learning part)
3. Show the fix (HOW)
4. Generalize (WHEN — when to apply this principle in the future)
```

**Example — teaching a principle through review:**

```
CORRECTIVE ONLY:
  "Change this to use a set instead of a list for the lookup."

EDUCATIONAL:
  "This searches a list of 10,000 items on every request:

   if user_id in blocked_users:  # blocked_users is a list

   List lookup is O(n) — it checks every element. With 10,000
   items, that's 10,000 comparisons per request.

   Change to a set:
   blocked_users = set(blocked_users_list)
   if user_id in blocked_users:  # O(1) average — one hash lookup

   General principle: Whenever you're checking 'is X in this
   collection?' and the collection has more than ~20 items,
   use a set instead of a list. Sets use hash tables internally,
   giving O(1) lookup instead of O(n)."
```

**The Socratic approach — ask questions that teach:**

```
Instead of telling, sometimes ask:

TELLING:
  "This function has side effects. Pure functions are better."

ASKING:
  "What happens if this function is called twice with the same
   input? Will it give the same result? What if two threads
   call it simultaneously?"

  → This leads the author to discover the problem themselves,
     which creates deeper understanding.

Best for: Senior developers who can reason through the answer.
Not for: Beginners who need direct guidance (they'll just feel stuck).
```

**Teaching common principles through reviews:**

```
PRINCIPLE: Fail fast
  Comment: "This validates the input at line 50, but uses it
   at line 10. Move validation to the top of the function.
   'Fail fast' means checking preconditions immediately
   so you don't waste work on invalid input and you get
   clearer error messages (the error happens close to the cause)."

PRINCIPLE: Single Responsibility
  Comment: "This function fetches data, transforms it, validates
   it, AND saves it. Each of these could change independently.
   Splitting into fetch(), transform(), validate(), save() means
   you can test each one separately and swap implementations.
   This is the Single Responsibility Principle — each function
   should have one reason to change."

PRINCIPLE: Defensive copying
  Comment: "You're returning the internal list directly:
   return self._items
   A caller could accidentally modify your internal state:
   obj.items().append('bad')  # modifies the internal list!
   Return a copy instead: return list(self._items)
   Or return a read-only view. This protects your invariants."
```

**The "escalating depth" technique:**
```
For junior developers:
  "Use a set for O(1) lookups instead of a list."
  (Direct instruction, minimal theory)

For mid-level developers:
  "This is O(n) on every request. Sets give O(1) lookups
   using hash tables. Here's the change: [code]"
  (Include the reasoning and complexity analysis)

For senior developers:
  "Consider the access pattern here — is this always a
   membership check, or do you also need ordering? If
   membership only, a set is O(1). If you need order too,
   consider a sorted set or an OrderedDict."
  (Explore trade-offs, don't prescribe)
```

**The knowledge-transfer checklist:**
```
For each educational comment, verify:

□ Did I explain the underlying principle (not just the fix)?
□ Will the author recognize this pattern in FUTURE code?
□ Did I match the depth to the author's level?
□ Did I connect this to a broader concept they can learn more about?
□ Is the tone "let me share something useful" not "you should know this"?
```

**The meta-principle:** The best code review doesn't just improve the code — it improves the developer. If your comment only fixes today's bug, it has limited value. If your comment teaches a principle that prevents a hundred future bugs, it has enormous value. Invest the extra sentence to explain WHY, not just WHAT.'''
    ),
    (
        "thinking/auto-autonomous-code-review-prioritization",
        r'''I sometimes leave 30+ comments on a PR, overwhelming the author. How do I prioritize code review feedback so the most important issues get attention and minor ones don't drown them out?''',
        r'''<think>
Comment overload is a real problem in code reviews. When an author sees 30+ comments, they feel overwhelmed and defensive. They can't distinguish critical security issues from style nitpicks because everything looks the same. The result: important issues get lost in the noise, and the author develops a negative association with code review.

**The solution:** Categorize and limit comments by priority. Focus on what MUST change, minimize what COULD change.

**Priority framework:**
1. Blocking (must fix before merge): security, correctness, data integrity
2. Important (should fix): performance, maintainability, test gaps
3. Minor (nice to have): style, naming, minor improvements
4. FYI (no action needed): tips, alternative approaches, future considerations
</think>

**Prioritizing Code Review Feedback**

**The priority system:**

```
🔴 BLOCKING (must fix before merge)
  Security vulnerabilities, incorrect behavior, data loss risk,
  breaking changes without migration.
  → Author MUST address these. No merge until fixed.
  → Limit: Usually 0-3 per PR. If more, the PR needs rework.

🟡 IMPORTANT (should fix, not blocking)
  Performance issues, missing error handling, missing tests,
  poor abstractions that will cause problems later.
  → Author should address these but can explain why not.
  → Limit: Usually 3-8 per PR.

🟢 MINOR (nice to have)
  Naming improvements, style suggestions, minor refactoring,
  alternative approaches that are marginally better.
  → Author can ignore these. Mark as "nit:" or "minor:"
  → Limit: Usually 3-5 per PR. Bundle into one comment if many.

💬 FYI (no action expected)
  Interesting observations, things to consider for future PRs,
  links to relevant documentation.
  → Explicitly say "no action needed" or "FYI only."
  → Limit: 1-2 per PR maximum.
```

**How to manage a 30-comment review:**

```
WRONG: Post all 30 comments equally.
  Author sees 30 comments and thinks "this PR is terrible."
  They can't tell which ones matter.

RIGHT: Post 3 blocking comments and summarize the rest.

  Top-level comment:
  "Overall this looks good! Three things need to change
   before merge:

   1. SQL injection on line 45 (see comment)
   2. Missing auth check on the admin endpoint (see comment)
   3. Race condition in the counter update (see comment)

   I also left a few minor style suggestions (not blocking).
   Nice work on the test coverage!"

  Then: 3 blocking inline comments (detailed)
  Then: 5 minor inline comments (marked "nit:" or "minor:")
  Skip: The other 22 comments that were truly trivial.
```

**The "two-column" technique:**
```
Mentally divide your comments into two columns:

COLUMN A: "If they only fix one thing..."
  → This is the most important issue.
  → Post it first, explain thoroughly.

COLUMN B: "Everything else"
  → Trim this to the top 5-8 items.
  → Group minor items into a single comment.
  → Drop anything truly trivial.
```

**When to drop a comment entirely:**
```
Don't post if:
□ It's purely personal preference with no objective improvement
□ It would take more time to discuss than to fix
□ The current approach works correctly and is readable
□ The comment is "I would have done it differently" (not wrong, just different)
□ It's the same nitpick you've mentioned in the last 3 PRs
  (raise it in a team meeting as a standard instead)
```

**Labeling convention:**
```
Use a consistent prefix system so authors can triage:

  "blocker: SQL injection — must fix before merge [details]"
  "important: Missing error handling — will crash on invalid input [details]"
  "nit: Consider renaming 'x' to 'user_count' for readability"
  "question: Why was this approach chosen over X?"
  "praise: Nice use of the builder pattern here!"

Authors can ctrl+F for "blocker" to find must-fix items.
```

**The comment budget:**
```
Limit yourself to a budget per PR:

  Small PR (<100 lines): 3-5 comments max
  Medium PR (100-500 lines): 5-10 comments max
  Large PR (500+ lines): 10-15 comments max
  (If a large PR needs >15 comments, it should be split)

When you hit the budget, ask:
  "Is this next comment more important than any I've already posted?"
  → No? Don't post it.
  → Yes? Post it and remove a lower-priority one.
```

**The meta-principle:** Code review effectiveness is inversely proportional to comment count. Five clear, prioritized comments get more attention and action than thirty undifferentiated comments. Your job is not to find everything that could be improved — it's to identify the changes that matter most and communicate them clearly. The PR author should finish reading your review feeling focused, not overwhelmed.'''
    ),
    (
        "thinking/auto-autonomous-code-review-tone",
        r'''I've been told my code review comments come across as harsh or condescending even when I don't intend that. How do I maintain a collaborative tone while still being direct about issues?''',
        r'''<think>
Tone in written communication is extremely hard to get right because text lacks the vocal inflection, facial expressions, and context of in-person conversation. What the reviewer intends as neutral often reads as critical. And developers are emotionally attached to their code — they hear "your code is wrong" as "you are wrong."

**The key insight:** You can be completely direct about technical issues while being warm about the person. Separate the code from the coder.

**Tone killers:**
- "Obviously..." (implies they should have known)
- "Why didn't you..." (implies negligence)
- "You should know that..." (patronizing)
- "This is wrong" (judgmental)
- Rhetorical questions ("Don't you think...?")
</think>

**Maintaining Collaborative Tone in Code Reviews**

**The core principle: Be direct about code, kind about people.**

```
HARSH (attacks the person):
  "You clearly didn't think about edge cases."

DIRECT (addresses the code):
  "This doesn't handle the case where the list is empty.
   Adding a guard clause would prevent the IndexError:
   if not items: return []"

Same issue raised, completely different impact.
```

**Tone transformation examples:**

| Harsh | Collaborative |
|-------|---------------|
| "This is wrong" | "This will cause X when Y happens" |
| "Why did you do it this way?" | "What was the reasoning for this approach? I'm wondering if X might work better because..." |
| "You should never do X" | "X can cause issues here because [reason]. Consider Y instead." |
| "Obviously this needs error handling" | "Adding error handling here would prevent crashes when the API returns a non-200 response." |
| "This is a bad name" | "What about `order_total` instead of `x`? It would make line 45 read more clearly." |
| "Fix this" | "Could we change this to X? It would prevent [issue]." |

**Language patterns that help:**

```
USE "WE" INSTEAD OF "YOU":
  Instead of: "You need to add tests"
  Use: "We should add tests for this edge case"
  → "We" makes it collaborative. "You" makes it adversarial.

USE QUESTIONS INSTEAD OF COMMANDS:
  Instead of: "Rename this variable"
  Use: "What do you think about renaming this to `user_count`
        for clarity?"
  → Questions invite discussion. Commands demand compliance.

USE "BECAUSE" TO JUSTIFY:
  Instead of: "Don't use var"
  Use: "Using const here would prevent accidental reassignment
        on line 23, which would cause a subtle bug."
  → "Because" shows you're not being arbitrary.

ACKNOWLEDGE GOOD WORK:
  "This is a clean implementation! One suggestion: [improvement]"
  → Starting with praise makes criticism easier to receive.
```

**The "would I say this to their face?" test:**
```
Before posting a comment, read it aloud and imagine
saying it to the author while they're sitting next to you.

Would you say "obviously this is wrong" to their face?
  → Probably not. Soften it.

Would you say "this approach will cause issues under load
   because of X — what about using Y instead?"
  → Yes. This is both direct and respectful.
```

**Positive reinforcement (often forgotten):**
```
Don't ONLY leave comments on problems. Also comment on good code:

  "Great use of the strategy pattern here — very clean."
  "This error handling is thorough — covers all the edge cases."
  "Nice test coverage for this module."

Ratio target: At least 1 positive comment for every 5 critiques.
This prevents code review from feeling like "finding everything
wrong with your work."
```

**The comment structure for difficult feedback:**
```
When you need to push back significantly:

1. Acknowledge: "I can see why you took this approach —
   it's simpler in the short term."
2. Concern: "My concern is that as we add more X,
   this pattern will become hard to maintain because Y."
3. Suggest: "What if we restructured it like Z? This would
   handle the current case and scale better."
4. Offer: "Happy to pair on this if it would help."

This structure says: "I respect your thinking AND I have
a concern AND here's a solution AND I'll help."
```

**The meta-principle:** Code review is a conversation between colleagues, not a teacher grading homework. Your comments should read as "here's something I noticed that could make this better" not "here's what you did wrong." The goal is that the author finishes reading your review feeling helped, not judged. When in doubt, add "what do you think?" to the end of your comment — it transforms a demand into a dialogue.'''
    ),
    (
        "thinking/auto-autonomous-code-review-self-improvement",
        r'''How do I continuously improve my own code review skills? I want to get better at finding important issues and providing helpful feedback.''',
        r'''<think>
Improving code review skills requires deliberate practice and feedback loops, just like improving coding skills. Most developers do code reviews without ever reflecting on whether their reviews are actually helpful.

**Areas to improve:**
1. Bug detection (finding issues that matter)
2. Communication (making feedback clear and actionable)
3. Prioritization (focusing on what matters most)
4. Knowledge sharing (teaching through reviews)
5. Efficiency (reviewing thoroughly without taking hours)

**How to build a feedback loop:**
- Track which of your review comments led to actual improvements
- Ask authors if your reviews were helpful
- Review your old review comments — do they hold up?
- Study how experienced reviewers comment
</think>

**Continuously Improving Code Review Skills**

**The review-of-reviews feedback loop:**

```
After each code review you do:

1. TRACK OUTCOMES:
   □ Did the author implement my suggestions?
   □ Which suggestions did they push back on? Were they right?
   □ Did any of my blocking comments turn out to be non-issues?
   □ Did I miss anything that caused a bug later?

2. ASSESS QUALITY:
   □ Were my comments actionable? (Author fixed without follow-up?)
   □ Were my comments accurate? (Did I correctly identify the issue?)
   □ Were my comments proportionate? (Right priority level?)
   □ Was my tone collaborative? (Author engaged constructively?)

3. LEARN:
   □ What did I catch that I'm proud of?
   □ What did I miss that I should have caught?
   □ What comment could have been better?
```

**Common growth areas and how to improve:**

**1. Finding more significant bugs:**
```
Practice: Before reviewing code, think about:
  - What could go wrong at scale? (N+1 queries, memory leaks)
  - What could go wrong with bad input? (null, empty, huge values)
  - What could go wrong with concurrency? (race conditions)
  - What could go wrong with failures? (network, disk, timeout)

Checklist per PR:
  □ Input validation present for user-supplied data?
  □ Error handling for external calls (DB, API, filesystem)?
  □ Resource cleanup (connections, file handles, locks)?
  □ Edge cases (empty collections, null values, boundary values)?
  □ Security (auth checks, injection, data exposure)?
```

**2. Improving communication:**
```
Practice: After writing a comment, re-read it and ask:
  - Can the author act on this without asking me anything?
  - Did I explain WHY, not just WHAT?
  - Is my tone collaborative?
  - Would I want to receive this comment?

Monthly exercise: Re-read your review comments from 30 days ago.
  - Do they still make sense out of context?
  - Were they helpful?
  - What would you write differently now?
```

**3. Improving efficiency:**
```
The 3-pass review technique:

Pass 1 (5 minutes): Big picture
  Read the PR description and file list.
  Understand WHAT the PR does and WHY.
  Check: Does the approach make sense?

Pass 2 (10-20 minutes): Detailed review
  Read the diff carefully.
  Focus on logic, not style.
  Leave comments on important issues.

Pass 3 (2 minutes): Final sweep
  Re-read your comments. Are they clear?
  Prioritize: Mark blocking vs. minor.
  Add a summary comment with your overall assessment.

Total: 15-30 minutes per PR (for typical PRs)
```

**4. Learning from others:**
```
Study technique: Read other people's code reviews.
  - What do experienced reviewers catch that you miss?
  - How do they phrase feedback?
  - What do they focus on?

Learning sources:
  - Open source project PRs (React, Django, Go stdlib)
  - Your team's senior engineers' reviews
  - Google's code review guidelines (publicly available)
```

**The monthly retrospective:**
```
Once a month, review your review stats:

  Reviews completed: __
  Comments per review (avg): __
  Blocking issues found: __
  Bugs caught before merge: __
  False positives (comments that were wrong): __

Trends to watch:
  - Decreasing false positives → getting more accurate
  - Increasing blocking issues found → getting better at spotting real problems
  - Decreasing comments per review → getting more focused
  - Positive author feedback → communication improving
```

**The meta-principle:** Code review is a skill that improves with deliberate practice, just like coding. The best reviewers aren't the ones who find the most issues — they're the ones who find the RIGHT issues and communicate them in a way that helps the author grow. Build a feedback loop: review, track outcomes, reflect, adjust. Over time, you'll develop an instinct for what matters and how to say it.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
