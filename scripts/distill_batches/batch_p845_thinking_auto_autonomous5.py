"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 5)

Autonomously improving explanation quality — detecting when explanations
are unclear and systematically making them better.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-explanation-clarity",
        r'''How can I autonomously detect when my technical explanations are unclear and systematically improve them without waiting for user feedback?''',
        r'''<think>
Self-evaluating explanation quality requires having internal criteria for what makes an explanation clear. I need to check my own output against these criteria before presenting it.

**Clarity criteria:**
1. Can the target audience understand every sentence?
2. Is jargon defined or avoided?
3. Is there a concrete example for every abstract concept?
4. Is the structure logical (building block by building block)?
5. Is it the right length (not too short to be useful, not too long to lose attention)?

**Self-evaluation process:**
1. Write the explanation
2. Re-read it as if I'm the target audience
3. Flag sentences that require prior knowledge I haven't established
4. Check for "curse of knowledge" — assuming the reader knows what I know
</think>

**Autonomous Explanation Quality Improvement**

**The self-evaluation checklist (run before presenting any explanation):**

```
□ Jargon check: Every technical term is either defined or
  commonly known to the target audience
□ Example check: Every abstract concept has a concrete example
□ Prerequisite check: No sentence requires knowledge I haven't
  introduced yet
□ Structure check: The explanation builds logically — no forward
  references
□ Length check: No section is longer than it needs to be
□ "So what?" check: The reader knows WHY this matters, not just
  WHAT it is
```

**The "curse of knowledge" detector:**
```
Flag any sentence that contains:
  - "Simply..." (it's not simple if you don't know it)
  - "Obviously..." (it's not obvious to the reader)
  - "Just do X" (implies X is easy; it may not be)
  - Acronyms without expansion
  - Concepts introduced without definition

Before: "Simply use a mutex to avoid race conditions."
After:  "Use a mutex (a lock that ensures only one thread
         accesses shared data at a time) to prevent race
         conditions (bugs where two threads modify the same
         data simultaneously)."
```

**The concrete example rule:**
```
ABSTRACT (hard to understand):
  "Dependency injection decouples components by providing
   dependencies from outside rather than creating them internally."

CONCRETE (easy to understand):
  "Instead of this:
     class UserService:
         def __init__(self):
             self.db = Database()  # creates its own dependency

   Do this:
     class UserService:
         def __init__(self, db):  # receives dependency from outside
             self.db = db

   Now UserService doesn't know or care what database it uses.
   You can pass a real DB in production and a fake DB in tests."
```

**The progressive disclosure structure:**
```
Layer 1: One sentence summary (for skimmers)
Layer 2: Key concept with one example (for most readers)
Layer 3: Detailed walkthrough (for learners)
Layer 4: Edge cases and nuances (for experts)

Each layer is self-contained. The reader can stop at any layer
and have a useful understanding.
```

**Self-improvement loop:**
```
1. Write explanation
2. Run the checklist
3. Find a violation (e.g., jargon without definition)
4. Fix it
5. Record the pattern: "I tend to use [term] without defining it"
6. In future explanations, proactively define that term
7. Eventually, the checklist item becomes automatic
```

**The meta-principle:** Clear explanations aren't written — they're edited. First write what you know, then edit for what the READER knows. The gap between those two is where clarity lives.'''
    ),
    (
        "thinking/auto-autonomous-simplify-complex-topics",
        r'''I tend to give overly complex explanations of simple concepts. How do I autonomously detect over-complexity and simplify without losing accuracy?''',
        r'''<think>
Over-complexity in explanations usually comes from:
1. Trying to be comprehensive when the user needs targeted help
2. Including caveats and edge cases upfront instead of progressively
3. Using precise technical language when plain language would work
4. Structuring by how YOU learned it, not how the reader needs it

**The simplification challenge:** Remove complexity without sacrificing correctness.

**The key insight:** You can be both simple AND accurate. Simple doesn't mean incomplete — it means focused on what matters most.
</think>

**Detecting and Fixing Over-Complex Explanations**

**Complexity red flags to detect in your own writing:**

| Red flag | Example | Fix |
|----------|---------|-----|
| Wall of text | 500 words for "what is a variable?" | Cut to 50 words + 1 example |
| Excessive caveats upfront | "Well, it depends on..." (before explaining the base case) | State the common case first, caveats later |
| Multiple abstractions at once | "A monad is a monoid in the category of endofunctors" | One concept at a time |
| History lesson | "In 1972, Dennis Ritchie..." | Start with what it IS, not where it came from |
| Defensive completeness | Covering every edge case | Cover the 90% case, mention edges briefly |

**The simplification protocol:**

**Step 1: Write your explanation**

**Step 2: Apply the "5-year-old" filter**
```
Not literally — but ask: "What's the SIMPLEST true statement
I can make about this?"

Before: "An API (Application Programming Interface) is a set
of protocols and tools for building software applications that
specifies how software components should interact."

After: "An API is a way for two programs to talk to each other.
Program A sends a request, Program B sends a response."
```

**Step 3: Cut the bottom 50%**
```
If your explanation is 10 paragraphs:
  - Which 5 are essential for basic understanding?
  - Move the other 5 to "Further reading" or "For advanced users"

Most explanations can be cut in half without losing anything
the reader actually needs.
```

**Step 4: Replace jargon with plain language**
```
"Polymorphism" → "using the same interface for different types"
"Abstraction" → "hiding the details behind a simpler interface"
"Encapsulation" → "keeping related data and functions together"
"Idempotent" → "safe to retry — running it twice gives the same result"
```

**Step 5: The sentence-level test**
```
For each sentence, ask:
  "If I removed this sentence, would the reader still understand?"
  If yes → remove it
  If no → keep it (it's load-bearing)
```

**The complexity budget:**
```
Simple question → Simple answer (1-3 sentences + 1 example)
Medium question → Medium answer (1-2 paragraphs + code example)
Complex question → Layered answer (summary → details → deep dive)

NEVER give a complex answer to a simple question.
```

**The meta-principle:** Complexity should be proportional to the question, not to your knowledge. Knowing a lot about a topic means you can explain it simply, not that you should explain all of it.'''
    ),
    (
        "thinking/auto-autonomous-improve-code-examples",
        r'''My code examples in explanations sometimes confuse more than they help. How do I self-evaluate whether a code example is actually clarifying the concept?''',
        r'''<think>
Code examples can hurt more than help when they:
1. Include irrelevant details (imports, boilerplate, error handling)
2. Use unfamiliar syntax or patterns
3. Are too long to hold in working memory
4. Mix the concept being taught with other concepts
5. Don't match what the reader would write themselves

**Good code examples:**
- Show ONLY the concept being explained
- Are short enough to read in one glance (5-15 lines)
- Use familiar variable names and patterns
- Can be copy-pasted and run
- Build incrementally (simple → complex)
</think>

**Self-Evaluating Code Example Quality**

**The code example checklist:**
```
□ FOCUSED: Shows only the concept, nothing else
□ SHORT: 5-15 lines (fits in one mental "chunk")
□ RUNNABLE: Reader can paste it and see the output
□ FAMILIAR: Uses standard patterns the reader already knows
□ ANNOTATED: Key lines have comments explaining why
□ PROGRESSIVE: If multiple examples, each builds on the last
```

**Bad example (too much noise):**
```python
import os
import sys
from typing import List, Optional
from dataclasses import dataclass, field

@dataclass
class Config:
    debug: bool = False
    verbose: bool = False
    log_level: str = "INFO"

class UserService:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.users: List[dict] = []

    def add_user(self, name: str, email: str) -> dict:
        user = {"name": name, "email": email, "id": len(self.users)}
        self.users.append(user)
        if self.config.verbose:
            print(f"Added user: {user}")
        return user

# THE CONCEPT (list comprehension) IS BURIED:
active = [u for u in service.users if u.get("active")]
```

**Good example (focused on the concept):**
```python
# List comprehension: filter and transform in one line
numbers = [1, 2, 3, 4, 5, 6]

# Get only even numbers
evens = [n for n in numbers if n % 2 == 0]
# Result: [2, 4, 6]

# Square each number
squares = [n ** 2 for n in numbers]
# Result: [1, 4, 9, 16, 25, 36]
```

**The "10-second test":**
```
Can the reader understand the example in 10 seconds?
  Yes → Good example
  No  → Too complex, simplify

If you need a paragraph of prose to explain your code example,
the code example isn't doing its job.
```

**Progressive example building:**
```
Step 1: Simplest possible case
  names = [user.name for user in users]

Step 2: Add a filter
  active_names = [user.name for user in users if user.active]

Step 3: Add transformation
  upper_names = [user.name.upper() for user in users if user.active]

Each step adds ONE thing. The reader always knows what changed.
```

**Self-evaluation questions:**
```
1. "If I cover the prose, does the code speak for itself?"
   If no → code needs better variable names or comments

2. "If I cover the code, does the prose explain the same thing?"
   If yes → one of them is redundant; remove it

3. "Could a junior dev read this code without getting lost?"
   If no → too much happening; split into smaller examples
```

**The meta-principle:** A good code example is a teaching tool, not a production artifact. Optimize for clarity, not for completeness. Remove everything that doesn't serve the concept being taught.'''
    ),
    (
        "thinking/auto-autonomous-detect-explanation-gaps",
        r'''How do I detect gaps in my explanations — things I assume the reader knows but might not — before presenting them?''',
        r'''<think>
Explanation gaps come from the "curse of knowledge" — once you know something, it's hard to remember not knowing it. You skip steps that feel obvious to you but aren't obvious to the reader.

**Common gap patterns:**
1. Missing prerequisites ("To use Docker, first install Docker" — but what IS Docker?)
2. Implicit steps ("Deploy your app" — but HOW? What commands?)
3. Assumed terminology ("Set up your CI/CD pipeline" — reader may not know CI/CD)
4. Missing "why" ("Use a hashmap" — but WHY is it better than a list?)
5. Skipped failure modes ("Run the migration" — what if it fails?)

**Detection strategy:** Trace the reader's likely path through the explanation and flag every assumption.
</think>

**Detecting and Filling Explanation Gaps**

**The assumption audit:**
```
For each sentence in your explanation, ask:
  "What does the reader need to ALREADY KNOW for this to make sense?"

If the answer isn't "nothing" or "something I explained earlier,"
you have a gap.
```

**Common gap patterns and how to detect them:**

**Gap 1: Missing prerequisites**
```
GAPPED: "Add a webhook to your Stripe account to handle events."
ASSUMPTION: Reader knows what a webhook is.

FIX: "Add a webhook (a URL that Stripe will call whenever
something happens, like a payment succeeding) to your
Stripe account."

DETECTION: Circle every technical noun. Is each one defined
or universally known to your audience?
```

**Gap 2: Implicit steps**
```
GAPPED: "Deploy your React app to production."
ASSUMPTION: Reader knows how to deploy.

FIX: "Deploy your React app to production:
  1. Build the production bundle: npm run build
  2. Upload the 'build/' folder to your hosting provider
  3. Configure your domain to point to the hosting provider"

DETECTION: For any instruction, ask "Could the reader
execute this RIGHT NOW with no additional research?"
```

**Gap 3: Assumed causation**
```
GAPPED: "Use an index on the email column."
ASSUMPTION: Reader knows WHY indexes help.

FIX: "Add an index on the email column. Without an index,
the database scans every row to find a match (slow).
With an index, it jumps directly to matching rows (fast),
like an index in a book."

DETECTION: For any recommendation, ask "Does the reader
know WHY this is better than not doing it?"
```

**The gap detection protocol:**
```
1. Write the explanation
2. Read it as a person with ZERO context
3. Highlight every term, concept, or step that requires
   prior knowledge
4. For each highlight:
   a. Was it defined earlier in this explanation? → OK
   b. Is it genuinely common knowledge for the audience? → OK
   c. Neither? → GAP. Add a definition or link.
5. Read again. Repeat until clean.
```

**The "fresh eyes" simulation:**
```
Imagine reading your explanation as three different people:
  - Complete beginner: Do they know all the terms?
  - Intermediate: Do they understand the logic flow?
  - Senior coming from a different domain: Are domain-specific
    assumptions explained?

If any of these personas would get stuck, add clarification
targeted to their level.
```

**The meta-principle:** Every explanation has invisible dependencies — things you assume the reader knows. The skill isn't in writing good explanations; it's in making those invisible dependencies visible. Audit every assumption.'''
    ),
    (
        "thinking/auto-autonomous-explanation-structure",
        r'''How should I autonomously evaluate and improve the STRUCTURE of my explanations, not just the content? What makes one ordering of information better than another?''',
        r'''<think>
Structure is often more important than content for understanding. The same information presented in different orders can go from confusing to crystal clear.

**Principles of good explanation structure:**
1. Start with WHY (motivation before mechanism)
2. Build from known to unknown
3. One concept at a time (no parallel introductions)
4. Concrete before abstract
5. Simple case first, edge cases later
6. Answer the question before elaborating

**Common structural problems:**
- Bottom-up when top-down would be better
- Starting with theory when a example would ground the reader
- Answering a different question than what was asked
- Burying the key insight in the middle
</think>

**Evaluating and Improving Explanation Structure**

**The structural evaluation framework:**

**Rule 1: Answer first, explain second**
```
BAD STRUCTURE:
  "HTTP is a protocol that runs on TCP. TCP establishes
   connections using a three-way handshake. HTTP sends
   requests over this connection. A GET request retrieves
   data from the server..."
  (Still hasn't answered: "How do I make an API call?")

GOOD STRUCTURE:
  "To make an API call:
   curl https://api.example.com/users
   This sends a GET request and returns user data.

   Here's how it works under the hood:
   1. Your computer connects to the server (TCP handshake)
   2. It sends an HTTP GET request
   3. The server processes it and sends a response
   ..."
```

**Rule 2: Known → Unknown (anchor new concepts to familiar ones)**
```
BAD: "A monad is a type class with bind and return operations."
     (Nothing to anchor to — entirely unknown concepts)

GOOD: "You know how you chain array operations?
       [1,2,3].filter(isEven).map(double)
       A monad generalizes this chaining pattern. Any type
       that supports chaining operations is a monad."
       (Anchored to familiar: array chaining)
```

**Rule 3: One concept per section**
```
BAD: Introducing async, Promises, AND error handling simultaneously

GOOD:
  Section 1: Synchronous code (what you know)
  Section 2: Why async exists (motivation)
  Section 3: Callbacks (simplest async)
  Section 4: Promises (better callbacks)
  Section 5: async/await (better Promises)
  Each builds on the last. One new concept per section.
```

**Rule 4: Concrete → Abstract**
```
BAD (abstract first):
  "The Observer pattern defines a one-to-many dependency
   between objects so that when one object changes state,
   all dependents are notified."

GOOD (concrete first):
  "Imagine a spreadsheet. Cell A1 contains a number.
   Cells B1 and C1 contain formulas that use A1.
   When you change A1, B1 and C1 update automatically.
   That's the Observer pattern."
```

**The structural self-test:**
```
1. Does the first sentence answer or address the question? (not wander)
2. Could the reader stop after the first paragraph and have a useful answer?
3. Does each section need only the sections BEFORE it (not after)?
4. Is there a clear progression (simple → complex, known → unknown)?
5. Are examples placed BEFORE or WITH the concept, not after?
```

**The "inverted pyramid" principle (from journalism):**
```
Paragraph 1: The complete answer (compressed)
Paragraph 2: Key details and examples
Paragraph 3: Important nuances
Paragraph 4+: Deep dives, edge cases, history

The reader can stop at ANY paragraph and have gotten
value proportional to the time spent.
```

**The meta-principle:** Good structure means the reader never has to read ahead to understand what they're reading now. Every sentence should be fully understandable with only what came before it. If you reference something you haven't introduced yet, restructure.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
