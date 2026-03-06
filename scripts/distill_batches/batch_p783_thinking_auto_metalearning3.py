"""Phase 4D: Self-Improvement — Meta-Learning (Part 3)

Model learns to evaluate learning strategies and adapt its approach.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-evaluate-learning-strategy",
        r'''I've been learning about distributed systems by reading blog posts. I can talk about CAP theorem and eventual consistency, but when asked to design a system, I freeze. What's wrong with my learning strategy?''',
        r'''<think>
This is a classic case of passive learning vs. active application. The symptom: can recite concepts but can't apply them.

**Diagnosis:** Blog posts are passive consumption. They give you vocabulary ("CAP theorem", "eventual consistency") but not the ability to use those concepts in design decisions.

**The learning taxonomy (Bloom's):**
1. Remember — can define CAP theorem (where this learner is)
2. Understand — can explain WHY certain tradeoffs exist
3. Apply — can USE the concepts in a design
4. Analyze — can EVALUATE which tradeoff is right for a given situation
5. Create — can DESIGN novel systems using these principles

Blog posts get you to level 1-2. System design requires level 3-5.

**The fix:** Replace passive reading with active design practice.
</think>

**Diagnosis: Passive learning → vocabulary without skill.**

Reading blog posts builds RECOGNITION ("I've heard of CAP theorem") but not APPLICATION ("I can design a system that makes the right CAP tradeoff").

**Learning pyramid for system design:**
| Level | Activity | Retention |
|-------|----------|-----------|
| Reading blog posts | Passive | ~10% |
| Watching talks | Passive | ~20% |
| Discussing with peers | Active | ~50% |
| Designing systems | Active | ~75% |
| Teaching/explaining designs | Active | ~90% |

**Fixed learning strategy:**

**1. Replace reading with designing (weekly practice):**
```
Pick a system: "Design a URL shortener"
Set a timer: 45 minutes
Draw the architecture on paper
Make explicit tradeoff decisions:
  - "I choose AP over CP because [reason]"
  - "I use a cache here because [reason]"
Then: Read how others designed it and compare
```

**2. Analyze real systems (reverse engineering):**
```
Pick a product you use (Twitter, Uber, Netflix)
Ask: How would I build this?
Then: Read their engineering blog to compare
Focus on: Where did my design differ? Why?
```

**3. Discuss and defend designs:**
```
Present your design to someone and defend your choices.
"Why did you choose PostgreSQL over DynamoDB?"
If you can't defend a choice, you don't understand it.
```

**The key insight:** You can't learn system design by reading about it, just as you can't learn to swim by reading about swimming. You have to practice designing systems, making tradeoff decisions, and defending those decisions.'''
    ),
    (
        "thinking/auto-metalearning-adapt-explanation-style",
        r'''I explained recursion to a beginner using the factorial example, but they still don't understand. How should I adapt my explanation strategy?''',
        r'''<think>
If the factorial example didn't work, it's probably because:
1. Factorial is mathematical — the learner might not relate to it
2. The concept of "a function calling itself" is deeply abstract
3. They might need a PHYSICAL or VISUAL metaphor first
4. They might need to see the EXECUTION, not just the code

**Adapting teaching strategy means:**
1. Try a different metaphor (not math)
2. Try a different modality (visual, not code)
3. Try a more relatable example (real-world, not mathematical)
4. Build from something they already understand
</think>

**Adaptation strategy: Try different angles until one clicks.**

**Attempt 1 failed:** Factorial (mathematical, abstract)
```python
def factorial(n):
    if n == 0: return 1
    return n * factorial(n-1)
```
*Why it might not work: If they don't intuitively grasp factorial, the code adds confusion on top of confusion.*

**Attempt 2: Physical metaphor (Russian dolls)**
"Imagine Russian nesting dolls. To open all of them:
1. Open the outer doll → find another doll inside
2. Open that one → find another inside
3. Keep opening until you find the tiny solid doll (the base case)
4. Then you're done

Recursion is: to solve the problem, solve a smaller version of the same problem. Keep going until the problem is so small it's trivial."

**Attempt 3: Visual trace (show the execution)**
```
countdown(3):
  print 3, then call countdown(2)
    print 2, then call countdown(1)
      print 1, then call countdown(0)
        base case! stop.
      returns
    returns
  returns
```
Draw the INDENTATION as nesting. Each indent is one function call deeper.

**Attempt 4: Relatable example (filesystem)**
"You have a folder. Inside it are files and more folders. To find all files:
1. Look at each item in the folder
2. If it's a file → add to list
3. If it's a folder → do the SAME THING for that folder (recursion!)
4. Stop when you run out of items (base case)"

**Teaching adaptation checklist:**
| If they don't understand... | Try... |
|---------------------------|--------|
| The abstract concept | A physical metaphor |
| The code | A visual execution trace |
| The mathematical example | A real-world example |
| Why it terminates | Emphasize the base case with countdown |
| Why it's useful | Show a tree/filesystem example where loops don't work |

**The meta-principle:** If explanation X doesn't work, don't repeat X louder. Try a completely different angle. Multiple representations of the same concept increase the chance that one connects with the learner's existing mental models.'''
    ),
    (
        "thinking/auto-metalearning-measure-explanation-quality",
        r'''How can I measure whether my code explanations are actually helping people learn, not just making them feel like they understand?''',
        r'''<think>
This is about the difference between "feeling of understanding" (illusion of competence) and actual understanding.

**The problem with most explanations:** The reader nods along, feels like they understand, but can't reproduce or apply the concept. This is the "illusion of competence" — passive reading creates a feeling of familiarity that people mistake for understanding.

**Measuring actual understanding requires:**
1. The learner must DO something, not just read
2. The task must require TRANSFER, not just repetition
3. There must be a way to verify the output is correct
</think>

**Measuring Understanding vs. Feeling of Understanding**

**The problem:** Reading a good explanation feels like learning, but it's often just recognition.

```
"I understand recursion!"
    → Can you write a recursive function from scratch?
    → "...no."
```

**3 levels of verification:**

**Level 1: Can they reproduce it?**
After your explanation, remove the code and ask: "Write this from scratch."
If they can → they at least memorized the pattern.
If they can't → they didn't actually understand.

**Level 2: Can they modify it?**
"Now change the factorial function to compute the sum of 1 to n."
This requires understanding the STRUCTURE, not just the specific example.

**Level 3: Can they transfer it?**
"Write a recursive function to flatten a nested list."
This requires applying the PRINCIPLE to a new problem. If they can do this, they genuinely understand recursion.

**Explanation quality indicators:**

| Indicator | Good sign | Bad sign |
|-----------|-----------|----------|
| Follow-up questions | "What happens if..." (exploring) | "Can you repeat that?" (lost) |
| Modifications | They adapt the code successfully | They can't change anything |
| New problems | They apply the concept to a new case | They're stuck without an example |
| Teaching others | They can explain it in their own words | They can only repeat your words |

**How to build testable explanations:**
```
1. Explain the concept
2. Show one example
3. Give a PRACTICE PROBLEM (slightly different from the example)
4. Let them try BEFORE showing the solution
5. If they succeed → understanding is real
6. If they fail → the explanation needs a different angle
```

**The meta-principle:** An explanation that doesn't include a practice problem is untestable. You can't know if it worked. Always pair explanations with "now you try" prompts.'''
    ),
    (
        "thinking/auto-metalearning-diminishing-returns",
        r'''I've been studying Python for 5 years and I feel like I'm not getting better. Am I at diminishing returns, or am I studying wrong?''',
        r'''<think>
After 5 years, there are two possibilities:
1. They've genuinely hit the ceiling of Python language knowledge (unlikely — there's always more)
2. They're repeating the same type of practice without challenging themselves (likely)

This is the "expertise plateau" — when further practice doesn't improve performance because you're practicing within your comfort zone.

**Key question:** Are they doing the same kind of Python work they did 3 years ago? If yes, they're not practicing — they're just working.

**What grows expertise after the basics:**
- Reading CPython source code (understand HOW Python works)
- Contributing to open source (different codebases, different patterns)
- Learning a very different language (Rust, Haskell → changes how you think about Python)
- Teaching Python (reveals gaps in understanding)
- Building novel things (not CRUD apps — compilers, frameworks, tools)
</think>

**Diagnosis: Probably studying wrong, not at diminishing returns.**

**After 5 years, the activities that got you to intermediate stop working:**

| Activity | Gets you to | Stops working at |
|----------|------------|-----------------|
| Tutorials | Beginner → Intermediate | Year 1-2 |
| Building CRUD apps | Intermediate | Year 2-3 |
| Reading documentation | Intermediate+ | Year 3-4 |
| Online courses | Intermediate | Year 1-2 |

**Activities that continue to grow expertise:**

**1. Read CPython source code (understand the interpreter)**
```python
# You use dicts every day. But can you explain:
# - How Python dicts achieve O(1) lookup?
# - What happens during hash collision?
# - Why dict ordering works since 3.7?
# Read: cpython/Objects/dictobject.c
```

**2. Learn a VERY different language**
```
Rust → teaches you about memory, ownership, lifetimes
  → Changes how you think about Python's memory model
Haskell → teaches you about types, immutability, composition
  → Changes how you structure Python code
```

**3. Build something you've never built before**
```
Not another web app. Try:
- A package manager (like pip)
- A static site generator (like Hugo)
- A linter or formatter (like Black)
- A simple database
- A compiler for a tiny language
```

**4. Contribute to open-source Python projects**
```
Read code written by experts. Understand their design decisions.
Start with: CPython, Flask, FastAPI, pytest, httpx
```

**5. Teach Python**
```
Write a blog post explaining decorators.
If you can't explain it clearly, you don't fully understand it.
Teaching is the best test of understanding.
```

**The principle:** After the basics, improvement comes from DISCOMFORT, not repetition. If your Python practice is comfortable, it's not making you better.'''
    ),
    (
        "thinking/auto-metalearning-self-correct-in-realtime",
        r'''How should I handle it when I realize mid-answer that I'm going down the wrong path? Should I restart or correct course?''',
        r'''<think>
This is about real-time self-correction — a critical meta-cognitive skill.

**Options when I realize I'm wrong mid-answer:**
1. Silently restart (delete what I've written, start over)
2. Correct course transparently ("Actually, let me reconsider...")
3. Continue and correct at the end
4. Continue with the wrong approach (worst option)

**The best approach depends on context:**
- If I haven't presented anything yet → silently restart (no need to show the false start)
- If I've already presented partial work → correct transparently
- If the wrong path has educational value → show the mistake and the correction

**The transparent correction is often MOST valuable for the user:**
"I started suggesting X, but I realize Y is better because..."
This teaches the user HOW to evaluate approaches, not just WHICH approach to use.
</think>

**Real-Time Self-Correction Strategy**

**The decision matrix:**
| Situation | Best action |
|-----------|------------|
| Haven't presented yet | Silently restart with better approach |
| Partially presented | Correct transparently: "Actually, let me reconsider..." |
| The mistake is educational | Show the mistake → explain why it's wrong → show the fix |
| Small error in detail | Note the correction inline and continue |

**The transparent correction (often most valuable):**
```
"I was about to suggest using a global variable for this, but
that would cause thread-safety issues. Instead, let's use a
thread-local or pass it as a parameter..."
```

**Why showing the correction helps the user:**
1. They see HOW to evaluate approaches (not just the final answer)
2. They learn the failure mode (what went wrong and why)
3. They develop judgment (knowing what to avoid)

**Self-correction triggers (when to re-evaluate):**
- "This is getting complicated" → Probably over-engineering
- "I'm making a lot of assumptions" → Should ask for clarification
- "I've seen this go wrong before" → Red flag, reconsider
- "The user asked for X but I'm building Y" → Scope creep, refocus

**The meta-skill: Notice WHEN you're going wrong.**
Most errors aren't sudden — there are warning signs:
- The code is getting longer than expected
- You're adding more edge cases than the core logic
- You feel uncertain but keep going
- The solution requires explaining "but first you need to understand..."

When you notice these signs, STOP and re-evaluate before continuing.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
