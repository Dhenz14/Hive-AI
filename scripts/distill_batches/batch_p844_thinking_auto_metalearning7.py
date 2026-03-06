"""Phase 4D: Self-Improvement — Meta-Learning (Part 7)

Cross-domain knowledge transfer strategies — leveraging concepts learned
in one area to accelerate learning and problem-solving in another.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-cross-domain-patterns",
        r'''I notice that concepts in distributed systems (like eventual consistency) seem similar to concepts in team management (like eventual alignment). How can I systematically use cross-domain pattern recognition to learn faster?''',
        r'''<think>
Cross-domain pattern recognition is one of the most powerful learning accelerators. When you recognize that two seemingly different domains share the same underlying pattern, you can:

1. Transfer solutions from the domain you know to the one you don't
2. Develop deeper understanding by seeing the same principle from multiple angles
3. Generate novel insights at the intersection of domains

**The key patterns that recur across domains:**
- Caching / Memoization (CS) = Memory / Habits (psychology) = Inventory (supply chain)
- Eventual consistency (distributed systems) = Eventual alignment (teams) = Market equilibrium (economics)
- Load balancing (systems) = Work distribution (management) = Diversification (finance)
- Circuit breakers (reliability) = Safety valves (engineering) = Boundaries (relationships)
</think>

**Systematic Cross-Domain Pattern Recognition**

**The universal patterns that appear everywhere:**

| Pattern | In CS | In Management | In Biology |
|---------|-------|---------------|------------|
| Caching | Store frequently used data locally | Build habits and standard procedures | Muscle memory |
| Load balancing | Distribute requests across servers | Distribute work across team members | Homeostasis |
| Circuit breaker | Stop calling a failing service | Stop escalating a failing approach | Pain reflex |
| Eventual consistency | Replicas converge over time | Teams align through communication | Ecosystem equilibrium |
| Backpressure | Slow producer when consumer is overwhelmed | Push back on scope when team is overloaded | Feedback inhibition |
| Garbage collection | Reclaim unused memory | Eliminate unused processes | Apoptosis |

**How to use this for faster learning:**

**Step 1: Identify the abstract pattern**
```
You know: Database connection pooling
  → Reuse expensive-to-create resources
  → Maintain a pool of pre-created resources
  → Check out / check in lifecycle

Abstract pattern: RESOURCE POOLING
```

**Step 2: Apply to new domain**
```
New domain: Thread management
  → Threads are expensive to create
  → Thread pools maintain pre-created threads
  → Tasks are submitted to the pool, threads are reused

You already understand 80% of thread pools because
you understand connection pools. Same pattern.
```

**Step 3: Note the differences (where the analogy breaks)**
```
Connection pools: Resources are fungible (any connection works)
Thread pools: Tasks may have affinity (need specific thread)

The DIFFERENCES are where the real learning happens.
The similarities get you started; the differences make you expert.
```

**Building a personal pattern library:**
```
Pattern: Rate Limiting
  In APIs: Max 100 requests per minute per client
  In UX: Debouncing user input to avoid excessive renders
  In Teams: Limiting work-in-progress to prevent context switching
  In Life: "No more than 3 commitments per week"

Once you see rate limiting as a universal pattern,
you can apply it fluently in any new domain.
```

**The transfer protocol:**
```
1. Learn deeply in Domain A
2. Extract the abstract pattern (remove domain-specific details)
3. Encounter a problem in Domain B
4. Ask: "What pattern from Domain A applies here?"
5. Apply the pattern, then look for where the analogy breaks
6. The breakpoints reveal what's UNIQUE about Domain B
```

**The meta-principle:** Domains are different in their specifics but share universal patterns. The more domains you learn, the fewer truly NEW patterns you encounter. Most "new" things are familiar patterns in unfamiliar clothing.'''
    ),
    (
        "thinking/auto-metalearning-analogy-limits",
        r'''I often use analogies from familiar domains to understand new ones, but sometimes the analogy breaks down and leads me astray. How do I know when to trust an analogy and when to abandon it?''',
        r'''<think>
Analogies are powerful learning tools but dangerous when over-extended. They work by mapping structure from a known domain to an unknown one. They fail when the two domains diverge in critical ways.

**When analogies work:**
- The structural mapping is valid (same relationships between components)
- The purpose is understanding, not precise prediction
- You're aware of which aspects map and which don't

**When analogies fail:**
- You extend the mapping beyond where it's valid
- You confuse the analogy for the reality
- The critical difference IS the thing you need to understand
- The analogy obscures rather than reveals
</think>

**Knowing When to Trust vs. Abandon an Analogy**

**The analogy lifecycle:**
```
Phase 1: HELPFUL — Analogy gives you a starting mental model
Phase 2: USEFUL — Analogy guides your reasoning correctly
Phase 3: LIMITING — Analogy can't explain new observations
Phase 4: HARMFUL — Analogy actively misleads you
```

**Example: "Electricity is like water flowing through pipes"**
```
Phase 1 (HELPFUL):
  Voltage = water pressure, Current = flow rate
  → Great for understanding basic circuits

Phase 2 (USEFUL):
  Resistance = narrow pipe → makes sense
  → Can reason about Ohm's law

Phase 3 (LIMITING):
  How do capacitors work? Water analogy gets awkward.
  → "It's like a rubber membrane in the pipe" — stretching it

Phase 4 (HARMFUL):
  Electromagnetic induction, transistors → water analogy
  actively gives wrong predictions
  → Must abandon the analogy
```

**Red flags that an analogy is breaking down:**

| Signal | Example | Action |
|--------|---------|--------|
| You need to add exceptions | "It's like X, except..." (3+ exceptions) | Analogy is limiting |
| Predictions are wrong | Analogy predicts A, reality shows B | Analogy is harmful |
| You're defending the analogy | "Well, if you think of it THIS way..." | You're attached, not learning |
| Experts don't use the analogy | Textbooks use different models | Analogy is for beginners only |
| The interesting part doesn't map | The key concept has no analog | Wrong analogy for this topic |

**The analogy testing protocol:**
```
1. State the analogy explicitly: "X is like Y because..."
2. List what maps: "Both have [A, B, C] in common"
3. List what doesn't map: "X has [D, E] that Y doesn't"
4. Check: Is the thing I'm trying to understand in the
   "maps" list or the "doesn't map" list?
5. If it doesn't map → abandon the analogy for this aspect
```

**When to use analogies:**
```
Good: Learning the basics of a new domain
Good: Communicating with non-experts
Good: Generating hypotheses ("if it's like X, then maybe...")
Bad:  Making precise predictions
Bad:  Understanding edge cases
Bad:  Expert-level reasoning
```

**The meta-principle:** Analogies are scaffolding, not structure. They help you build understanding, but once the understanding is built, the scaffolding should come down. If you're still relying on the analogy after weeks of learning, you haven't developed genuine understanding of the new domain.'''
    ),
    (
        "thinking/auto-metalearning-transfer-programming-paradigms",
        r'''I'm proficient in object-oriented programming and need to learn functional programming. What specific OOP concepts transfer to FP, and which ones do I need to unlearn?''',
        r'''<think>
OOP to FP is one of the most common paradigm transfers, and it's tricky because some concepts transfer well, some partially, and some need to be completely unlearned.

**Transfers well:**
- Abstraction (both paradigms use it, just differently)
- Composition (OOP composes objects, FP composes functions)
- Encapsulation (OOP uses classes, FP uses closures)
- Polymorphism (OOP uses inheritance/interfaces, FP uses higher-order functions)

**Must unlearn:**
- Mutable state as the default
- Identity (objects have identity; values don't)
- Inheritance hierarchies
- Side effects everywhere
- Imperative flow control (loops → recursion/map/filter)
</think>

**OOP to FP: Transfer Guide**

**Concepts that transfer directly:**

| OOP Concept | FP Equivalent | What changes |
|-------------|---------------|--------------|
| Interface | Type class / Protocol | Same idea: define a contract |
| Composition over inheritance | Function composition | Same philosophy, different mechanism |
| Encapsulation (private state) | Closures | Both hide internal state |
| Strategy pattern | Higher-order functions | Pass behavior as an argument |
| Decorator pattern | Function wrapping | Wrap a function with additional behavior |
| Iterator pattern | Lazy sequences | Both produce values on demand |

**Example — Strategy pattern becomes a function parameter:**
```python
# OOP: Strategy pattern
class Sorter:
    def __init__(self, strategy):
        self.strategy = strategy
    def sort(self, data):
        return self.strategy.sort(data)

class QuickSort:
    def sort(self, data): ...

sorter = Sorter(QuickSort())

# FP: Just pass a function
def sort_data(data, sort_fn):
    return sort_fn(data)

sort_data(data, quicksort)
```

**Concepts you must UNLEARN:**

**1. Mutable state**
```python
# OOP habit (UNLEARN THIS):
class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1  # mutating state

# FP approach:
def increment(count):
    return count + 1  # return new value, never mutate
```

**2. Inheritance hierarchies**
```python
# OOP habit (UNLEARN THIS):
class Animal: ...
class Dog(Animal): ...
class GoldenRetriever(Dog): ...  # deep hierarchy

# FP approach: Compose behaviors
def make_sound(sound_fn, name):
    return f"{name} says {sound_fn()}"

bark = lambda: "Woof"
make_sound(bark, "Rex")  # compose, don't inherit
```

**3. Loops → map/filter/reduce**
```python
# OOP habit:
results = []
for item in items:
    if item.active:
        results.append(item.name)

# FP approach:
results = [item.name for item in items if item.active]
# Or: list(map(lambda i: i.name, filter(lambda i: i.active, items)))
```

**The mental model shift:**
```
OOP thinks in: Objects that DO things (nouns with verbs)
FP thinks in:  Transformations of data (verbs applied to nouns)

OOP: user.updateEmail(newEmail)  → object changes itself
FP:  updateEmail(user, newEmail) → returns a new user
```

**The meta-principle:** The hardest part of learning FP from OOP isn't the new concepts — it's unlearning the reflexive reach for mutation. Every time you think "change this variable," replace it with "return a new value." That single shift unlocks 80% of FP thinking.'''
    ),
    (
        "thinking/auto-metalearning-cross-domain-debugging",
        r'''Can debugging skills from software engineering transfer to debugging problems in other domains, like business processes or personal productivity? What's the transferable framework?''',
        r'''<think>
Debugging is fundamentally about systematic diagnosis — narrowing down from symptoms to root cause. This process is identical across domains. The tools change, but the methodology transfers completely.

**The universal debugging framework:**
1. Observe the symptom
2. Form hypotheses about the cause
3. Design experiments to test hypotheses
4. Isolate the variable (binary search)
5. Verify the fix resolves the symptom
6. Prevent recurrence

This applies to code, business processes, personal productivity, health, relationships, machines — anything with observable symptoms and hidden causes.
</think>

**The Universal Debugging Framework**

**The process is identical across domains:**

```
SOFTWARE                    BUSINESS PROCESS              PERSONAL PRODUCTIVITY
─────────────────────────   ─────────────────────────     ─────────────────────────
1. Bug report: "App is      1. Symptom: "Sales are        1. Symptom: "I can't focus
   slow"                       declining"                     after 2pm"
2. Reproduce: When? Where?  2. Scope: Which products?     2. Scope: Which days? Which
   Every request or some?      Which regions?                 tasks?
3. Hypotheses:              3. Hypotheses:                3. Hypotheses:
   - DB is slow                - Market changed              - Blood sugar crash
   - Memory leak               - Sales team turnover         - Too many meetings in AM
   - N+1 queries               - Product quality dropped     - Insufficient sleep
4. Isolate:                 4. Isolate:                   4. Isolate:
   - Profile DB → fine         - Market stable → no          - Ate lunch → yes
   - Check memory → growing    - Turnover → yes, 3 reps     - Meetings → no pattern
   - Count queries → 200!      - Quality → unchanged         - Sleep → correlated!
5. Root cause: N+1 queries  5. Root cause: Lost 3 senior  5. Root cause: <7h sleep
                               reps, replacements untrained   → afternoon crash
6. Fix: Add eager loading   6. Fix: Training program +    6. Fix: Sleep by 11pm,
   Prevent: Add query          retention bonuses              set alarm
   monitoring                  Prevent: Quarterly reviews
```

**The transferable techniques:**

**Binary search debugging (works everywhere):**
```
Software: "It worked in version 5, broke in version 10"
  → Test version 7.5. Works? Bug is in 8-10. Doesn't? Bug is in 5-7.5.

Business: "Sales were good in January, bad in June"
  → Check March. Good? Problem started April-June. Bad? Started Feb-March.

Productivity: "I was productive last month, not this month"
  → What changed? New project? New schedule? New environment?
```

**The "what changed?" principle:**
```
If it used to work and now it doesn't, SOMETHING CHANGED.
Find the change and you find the cause.

Software: "What deployment happened before the bug?"
Business: "What changed in the market/team/product?"
Health: "What changed in diet/sleep/exercise/stress?"
```

**Rubber duck debugging (explain it to find the gap):**
```
Software: Explain the code flow to a duck → spot the logical error
Business: Explain the process to a new hire → spot the inefficiency
Personal: Journal about the problem → spot the assumption you're making
```

**The 5 Whys (works identically everywhere):**
```
Software:                          Personal:
Why is the API slow?               Why am I always behind on tasks?
→ DB queries take 2s               → I underestimate task duration
Why are queries slow?              Why do I underestimate?
→ Missing index                    → I don't account for interruptions
Why is the index missing?          Why don't I account for them?
→ Migration wasn't run             → I plan for ideal conditions
Why wasn't it run?                 Why do I plan for ideal?
→ No deployment checklist          → No buffer in my estimates
Root cause: Process gap            Root cause: No buffer habit
```

**The meta-principle:** Debugging is not a programming skill — it's a thinking skill. The ability to systematically move from symptom to root cause transfers to literally any domain where things can go wrong.'''
    ),
    (
        "thinking/auto-metalearning-leverage-multiple-domains",
        r'''I know backend development, some data science, and I used to study cognitive psychology. How can I deliberately leverage this unusual combination to create unique insights or skills?''',
        r'''<think>
Unusual skill combinations create what Scott Adams calls "talent stacks" — you don't need to be the best in any one skill, but the combination creates a unique and valuable profile.

**Backend + Data Science + Cognitive Psychology is a powerful combination:**
- Backend: Building scalable systems
- Data Science: Extracting insights from data
- Cognitive Psychology: Understanding how humans think, decide, and err

**Potential unique capabilities:**
1. Building AI/ML systems that account for human cognitive biases
2. Designing UX backed by both data and psychology
3. Creating developer tools that work WITH human cognition, not against it
4. Building systems for behavior change (apps, nudges, interventions)
</think>

**Leveraging Your Unique Skill Combination**

**Your talent stack:**
```
Backend Dev ∩ Data Science ∩ Cognitive Psychology
     ↓              ↓              ↓
  Build it      Measure it     Understand the humans using it
```

**Unique capabilities this combination unlocks:**

**1. Human-aware ML systems**
```
Most ML engineers: Build a recommendation engine that maximizes clicks
You: Build a recommendation engine that accounts for:
  - Choice overload (too many options → decision paralysis)
  - Anchoring bias (first recommendation has outsized influence)
  - Satisfaction vs. engagement (users may click more but feel worse)

This is RARE. Most teams have the tech skills but not the psych knowledge.
```

**2. Developer experience (DX) engineering**
```
Backend knowledge: How systems work
Psych knowledge: How developers think

Unique insight: Design APIs and tools that match developer mental models
  - Error messages that address the likely misconception
  - Documentation structured by cognitive load theory
  - CLI tools that use recognition over recall

Example: Instead of "Error: ECONNREFUSED"
  → "Cannot connect to database at localhost:5432.
     Is PostgreSQL running? Try: pg_isready"
  (Addresses the likely mental state of the developer)
```

**3. Data-driven behavior change platforms**
```
Data science: A/B test and measure behavior changes
Psychology: Design interventions based on cognitive science
Backend: Build the platform that delivers personalized nudges

Applications: Health apps, education platforms, productivity tools
```

**4. Bias-aware data analysis**
```
Most data scientists: Look at the numbers
You: Look at the numbers AND ask:
  - "Am I seeing a pattern because it's real, or because of
     confirmation bias?"
  - "Is this correlation meaningful, or am I anchoring on it
     because I saw it first?"
  - "Would I interpret this data differently if I saw it in
     a different order?"
```

**How to deliberately create cross-domain innovations:**
```
Method: Forced combination
1. Pick a problem from Domain A (backend)
2. Ask: "What does Domain C (psychology) say about this?"
3. Use Domain B (data science) to validate

Example:
  Problem: API rate limiting (backend)
  Psychology: "Loss aversion — users hate losing access more
              than they value having it"
  Innovation: Instead of hard rate limits (403 Forbidden),
              use progressive degradation (slower responses,
              reduced features) — less psychologically painful
  Data science: A/B test both approaches, measure user retention
```

**The meta-principle:** Your unusual combination IS your competitive advantage. Don't try to be the best backend engineer or the best data scientist. Be the only person who can build psychologically-informed, data-driven backend systems. Scarcity creates value, and unusual combinations are inherently scarce.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
