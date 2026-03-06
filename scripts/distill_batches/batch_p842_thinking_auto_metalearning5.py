"""Phase 4D: Self-Improvement — Meta-Learning (Part 5)

Learning from user feedback patterns — how to detect and incorporate
implicit and explicit signals from user interactions.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-implicit-feedback",
        r'''How can I learn from implicit user feedback — things like when they rephrase their question, ask follow-ups, or seem to ignore parts of my answer?''',
        r'''<think>
Implicit feedback is often more honest than explicit feedback. When a user rephrases their question, they're telling me "you didn't understand what I meant." When they ignore part of my answer, they're saying "that part wasn't useful."

**Types of implicit feedback:**
1. Rephrasing → I misunderstood the question
2. Follow-up asking for basics → My answer was too advanced
3. Follow-up asking for depth → My answer was too shallow
4. Ignoring sections → Those sections weren't relevant
5. Asking the same question again → My answer didn't help at all
6. Moving to a different topic → They gave up on getting help from me

**How to use each signal to improve:**
Each signal tells me something specific about what to change.
</think>

**Learning from Implicit User Feedback**

**The feedback signals users give without saying anything:**

| User behavior | What it means | How to adapt |
|---------------|---------------|--------------|
| Rephrases the question | You misunderstood | Re-read original, focus on THEIR words |
| Asks "but what about X?" | You missed a key concern | Address X and reconsider what else you missed |
| Says "let me be more specific" | Your answer was too general | Ask clarifying questions upfront next time |
| Ignores half your answer | That half was irrelevant | Be more targeted, less comprehensive |
| Asks the same thing again | Your answer didn't help | Try a completely different approach |
| Says "never mind" | They gave up | You failed — analyze what went wrong |

**Building a feedback loop:**

**Step 1: Track the pattern**
```
Interaction 1: User asks about React performance
  My answer: 2000 words covering 8 optimization techniques
  User response: "But specifically for list rendering?"
  Signal: Too broad. They wanted targeted help, not a survey.

Interaction 2: User asks about database indexing
  My answer: 1500 words covering B-trees, hash indexes, etc.
  User response: "Can you just tell me which columns to index?"
  Signal: Too theoretical. They wanted practical guidance.

Pattern: I'm defaulting to comprehensive/theoretical when
         users want targeted/practical.
```

**Step 2: Adjust the default**
```
Old default: Cover all aspects thoroughly
New default: Ask "What specific aspect?" or lead with the
             most practical recommendation, then offer depth
```

**Step 3: Verify the adjustment worked**
```
Next interaction: User asks about caching
New approach: "The most impactful caching to add first is
              [specific recommendation]. Want me to go deeper
              on the theory behind this?"
User response: "Yes, tell me more" or "No, that's enough"
Signal: Now the USER controls the depth.
```

**The meta-principle:** Every follow-up question is feedback. If users consistently ask follow-ups of the same type, that reveals a systematic gap in how you structure answers.'''
    ),
    (
        "thinking/auto-metalearning-explicit-feedback-integration",
        r'''When users explicitly tell me my answer was wrong or unhelpful, how should I process that feedback to improve future answers rather than just fixing the immediate response?''',
        r'''<think>
Explicit negative feedback is the most valuable learning signal, but it's easy to handle poorly. The common mistake: fix the immediate answer without extracting the general lesson.

**Two levels of response to negative feedback:**
1. Tactical: Fix this specific answer (necessary but insufficient)
2. Strategic: Extract the pattern and apply it to all future answers

**Framework for extracting lessons:**
- What category of error was this?
- Is this a one-off or a pattern?
- What systematic change would prevent this class of error?
- How can I verify the change works?
</think>

**Processing Explicit Feedback for Systemic Improvement**

**The wrong way to handle "your answer was wrong":**
```
User: "That's wrong, you should use useEffect, not useMemo"
Bad response: "You're right, here's the corrected code with useEffect"
              (fixes the symptom, learns nothing)
```

**The right way — extract the lesson:**
```
User: "That's wrong, you should use useEffect, not useMemo"

Step 1 - Fix immediately:
  "You're right, useEffect is correct here because this is a
  side effect, not a derived computation."

Step 2 - Categorize the error:
  Error type: Confused side effects with computations
  Root cause: Applied "memoize for performance" heuristic
              without checking if it's a computation or effect

Step 3 - Extract the rule:
  "Before suggesting useMemo, verify the operation is a
  PURE COMPUTATION (input → output, no side effects).
  If it involves API calls, subscriptions, or DOM mutations,
  it's useEffect."

Step 4 - Generalize:
  "Before suggesting ANY React hook, verify the operation
  type matches the hook's purpose."
```

**Error taxonomy for systematic improvement:**

| Error category | Example | Systematic fix |
|---------------|---------|----------------|
| Wrong tool for the job | useMemo for side effects | Verify operation type before recommending |
| Outdated information | Suggesting deprecated API | Check version/date of knowledge |
| Missing context | Generic advice for specific framework | Ask about stack before answering |
| Over-generalization | "Always use X" when X has exceptions | Add caveats and conditions |
| Assumed skill level | Advanced answer for a beginner | Gauge experience level first |

**The feedback journal pattern:**
```
For each piece of negative feedback, record:
1. What I said (the error)
2. What was correct (the fix)
3. WHY I was wrong (root cause)
4. What RULE would have prevented this
5. Where ELSE this rule applies
```

**The meta-principle:** One correction fixes one answer. One extracted rule fixes a hundred future answers. Always ask "what class of error is this?" not just "what's the right answer?"'''
    ),
    (
        "thinking/auto-metalearning-feedback-from-questions",
        r'''How can I learn from the types of questions users ask? If many users ask similar questions, what does that tell me about how I should improve?''',
        r'''<think>
Aggregate question patterns reveal systematic gaps. If many users ask the same question, it means:

1. There's a common knowledge gap in the topic
2. My standard explanations of related topics aren't sufficient
3. There might be a confusing aspect of the technology that I should proactively address

**Types of question pattern analysis:**
- Frequency: What topics get asked most?
- Depth: Where do people get stuck (basic vs. advanced)?
- Sequence: What questions follow what other questions?
- Frustration: Which topics generate the most follow-ups?
</think>

**Learning from Question Patterns**

**What aggregate questions reveal:**

**Pattern 1: Many users ask the same question**
```
Signal: "How do I center a div in CSS?" (asked constantly)
Meaning: This is a genuinely confusing topic
Action: Lead with the modern, simple answer (flexbox/grid)
        Don't explain 5 historical approaches
```

**Pattern 2: Users ask basic questions after receiving advanced answers**
```
Signal: After explaining async/await, users ask "what's a Promise?"
Meaning: I'm skipping prerequisite knowledge
Action: Before explaining async/await, check if they
        understand Promises. Build up, don't assume.
```

**Pattern 3: The same follow-up question appears repeatedly**
```
Signal: After explaining Git branching, users always ask
        "but what happens to my uncommitted changes?"
Meaning: My branching explanation has a gap
Action: Proactively address uncommitted changes in
        every branching explanation
```

**Pattern 4: Questions cluster by mistake type**
```
Signal: Many users ask "why does my state not update immediately?"
Meaning: React's batched state updates are a common confusion
Action: When explaining setState, always mention it's
        asynchronous and show the correct pattern
```

**Building a question taxonomy:**
```
Topic: React State Management
  Frequent questions:
    1. "Why doesn't state update immediately?" (40%)
    2. "When should I use useState vs useReducer?" (25%)
    3. "How do I share state between components?" (20%)
    4. "Why does my component re-render?" (15%)

  Insight: 40% of questions are about the same confusion
  Action: Every React state explanation should open with
          "State updates are batched and asynchronous"
```

**The proactive improvement cycle:**
```
1. Track which questions get asked most
2. Identify the underlying confusion
3. Modify standard explanations to address it proactively
4. Check if the follow-up question rate drops
5. If not, try a different proactive explanation
```

**The meta-principle:** Repeated questions are not failures of the questioner — they're failures of available explanations. If everyone asks the same thing, the standard way of teaching that topic is broken.'''
    ),
    (
        "thinking/auto-metalearning-satisfaction-signals",
        r'''How do I distinguish between a user who is genuinely satisfied with my answer versus one who just accepted it because they don't know enough to challenge it?''',
        r'''<think>
This is a critical distinction. A user who says "thanks!" might mean:
1. "That was exactly what I needed" (genuine satisfaction)
2. "I don't understand enough to know if this is right, but I'll try it" (false satisfaction)
3. "I'm giving up on getting a better answer" (resignation)

**Signals of genuine vs. false satisfaction:**
- Genuine: They ask a NEXT-STEP question ("Great, now how do I deploy this?")
- False: They go quiet or say "ok thanks" with no follow-up
- Resignation: They say "I'll figure it out" or "never mind"

**Why this matters for learning:**
If I can't distinguish these, I might think my explanations are good when they're actually confusing but not being challenged.
</think>

**Distinguishing Genuine Satisfaction from False Acceptance**

**The satisfaction spectrum:**

| Response | Likely meaning | Confidence in understanding |
|----------|---------------|---------------------------|
| "Perfect, now how do I X?" | Genuine — moving to next step | High |
| "That makes sense, so if I wanted to Y..." | Genuine — applying the concept | High |
| "Thanks!" + applies it correctly | Genuine — verified by action | High |
| "Ok, thanks" (no follow-up) | Uncertain — might not understand | Medium |
| "I'll try that" | Possibly false — untested understanding | Low |
| "Ok I think I get it" | Likely false — hedging language | Low |
| "I'll figure it out" | Resignation — gave up | Very low |
| Silence | Unknown — could be any of the above | Unknown |

**Hedging language as a warning sign:**
```
High confidence (genuine):    Low confidence (false):
"Got it!"                     "I think I get it"
"That's exactly what I need"  "I'll try that"
"Makes total sense"           "Ok that sort of makes sense"
"Now let me try X"            "I'll figure out the rest"
```

**Proactive verification techniques:**

**1. The application check:**
```
Instead of ending with the explanation, end with:
"To verify this makes sense — if you wanted to add a
new endpoint, which file would you modify and what
would you add?"

If they can answer → genuine understanding
If they can't → the explanation didn't land
```

**2. The prediction check:**
```
"Before I show you the output, what do you think
this code will print?"

Their prediction reveals their mental model.
If it's wrong, you know where the gap is.
```

**3. The variation check:**
```
"Now suppose instead of a list, you had a dictionary.
How would you modify this approach?"

If they can adapt → they understood the principle
If they can't → they memorized the specific example
```

**When you suspect false satisfaction:**
```
Don't ask: "Did that make sense?" (they'll say yes)
Do ask: "What part is least clear?" (assumes something is unclear)
Or: "If you had to explain this to a colleague, what would you say?"
```

**The meta-principle:** "Do you understand?" is a useless question — it always gets "yes." Instead, ask them to DO something with the knowledge. Action reveals true understanding.'''
    ),
    (
        "thinking/auto-metalearning-feedback-contradictions",
        r'''Sometimes different users give me contradictory feedback — one says my answers are too detailed, another says they're not detailed enough. How do I reconcile conflicting feedback to actually improve?''',
        r'''<think>
Contradictory feedback usually means both are right — for different contexts. The problem isn't that one is wrong, it's that I'm giving the same level of detail to different types of users.

**Why feedback contradicts:**
1. Different users have different expertise levels
2. Different contexts need different depth
3. Different learning styles prefer different approaches
4. One-size-fits-all answers serve no one well

**The solution isn't to pick one side — it's to become adaptive.**
</think>

**Reconciling Contradictory Feedback**

**Why contradictions exist — they're both right:**
```
User A (senior engineer): "Too much detail, just give me the answer"
User B (junior developer): "Not enough detail, I need more explanation"

They're both correct. The problem isn't the detail level —
it's that you're giving the SAME detail level to both.
```

**The resolution framework:**

**Step 1: Categorize feedback by user type**
```
"Too detailed" feedback comes from:
  - Experienced developers
  - People with specific, narrow questions
  - People in a hurry

"Not detailed enough" feedback comes from:
  - Beginners learning a concept
  - People with broad "how does this work" questions
  - People who need to understand WHY, not just WHAT
```

**Step 2: Identify the variable, not the setting**
```
Wrong conclusion: "I should be less detailed" or "more detailed"
Right conclusion: "I should VARY detail based on context"

The feedback isn't telling you the RIGHT level —
it's telling you that a FIXED level is wrong.
```

**Step 3: Build adaptive responses**
```
Structure: Lead with the concise answer, offer depth

"Use useEffect for side effects, not useMemo.

[Concise answer — satisfies the expert]

Here's why: useMemo is for pure computations where you
want to cache the result. useEffect is for operations
that interact with the outside world — API calls, DOM
manipulation, subscriptions...

[Depth — satisfies the learner]
"
```

**The layered answer pattern:**
```
Layer 1: One-line answer (for experts who just need the fact)
Layer 2: Brief explanation (for intermediates)
Layer 3: Detailed walkthrough (for learners)
Layer 4: Deep dive with examples (for deep learners)

Let the user stop at the layer they need.
```

**Handling genuinely contradictory feedback:**

| Feedback A | Feedback B | Resolution |
|------------|------------|------------|
| "Too detailed" | "Not detailed enough" | Adaptive depth (layered answers) |
| "Too much code" | "Need more code" | Lead with code, explain after |
| "Too theoretical" | "Need more theory" | Start practical, link to theory |
| "Too opinionated" | "Just tell me what to do" | State recommendation, then show alternatives |

**When feedback truly conflicts (same user type, same context):**
```
Sometimes feedback is just wrong. If 10 beginners say
"more detail" and 1 beginner says "less detail," go with
the majority. The outlier may have unusual preferences
or may not actually be a beginner.
```

**The meta-principle:** Contradictory feedback reveals a missing variable. Instead of asking "which feedback is right?", ask "what context variable am I failing to detect and adapt to?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
