"""Phase 4D: Self-Improvement — Meta-Learning (Part 4)

Recognizing and breaking out of reasoning ruts — patterns where the model
falls into familiar but suboptimal reasoning paths.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-recognize-reasoning-rut",
        r'''I keep defaulting to suggesting microservices for every architecture question, even when it might not be appropriate. How do I recognize when I'm in a reasoning rut?''',
        r'''<think>
This is about pattern recognition in my own reasoning. A "reasoning rut" is when I apply the same solution template regardless of context.

**Signs of a reasoning rut:**
1. I reach for the same answer before fully understanding the question
2. I feel "comfortable" with my answer immediately (no tension, no deliberation)
3. My answer would be the same regardless of the specifics given
4. I skip the analysis phase and jump to the solution

**Why microservices become a rut:**
- It's a popular, well-known pattern
- It sounds sophisticated and modern
- It's easy to justify ("scalability", "separation of concerns")
- But it's genuinely wrong for many cases (small teams, simple domains, early-stage products)

**Breaking out requires:** Forcing myself to argue the opposite before committing.
</think>

**Recognizing a Reasoning Rut**

**Warning signs that you're in a rut:**

| Signal | What it looks like | What it means |
|--------|-------------------|---------------|
| Instant answer | "Obviously microservices" before reading details | Pattern matching, not reasoning |
| No tension | You feel zero uncertainty | You skipped analysis |
| Context-blindness | Same answer for 2-person startup and 500-person enterprise | Not adapting to constraints |
| Defensive reaction | Annoyed when challenged on the recommendation | Ego-attachment to a pattern |

**The "opposite argument" technique:**

Before committing to an answer, force yourself to argue the opposite:

```
Default instinct: "Use microservices"
Force opposite: "Why would a monolith be BETTER here?"

- Team size: 3 developers → microservices create overhead
- Domain complexity: Simple CRUD → no need for service boundaries
- Timeline: MVP in 6 weeks → monolith ships faster
- Ops capability: No DevOps team → who manages 12 services?

Verdict: Monolith is actually better here.
```

**Rut-breaking checklist:**
1. Notice the instant answer (the rut)
2. Ask "Would my answer change if [constraint] were different?"
3. Argue the opposite for 60 seconds
4. Only then commit to a recommendation
5. If your answer never changes regardless of context, you are in a rut

**The meta-principle:** Comfort in reasoning is a warning sign. Good analysis should involve tension between alternatives. If there's no tension, you're not analyzing — you're pattern-matching.'''
    ),
    (
        "thinking/auto-metalearning-break-confirmation-bias",
        r'''I notice that when debugging, I often form a hypothesis early and then only look for evidence that confirms it, ignoring contradicting clues. How do I break this confirmation bias in my reasoning?''',
        r'''<think>
Confirmation bias in debugging is one of the most common reasoning ruts. You form a theory ("it must be a race condition") and then interpret everything through that lens, ignoring evidence that points elsewhere.

**Why this happens:**
- Early hypotheses create a mental frame
- Contradicting evidence requires cognitive effort to process
- We feel productive when "confirming" our theory
- Admitting the hypothesis is wrong feels like wasted time

**How to break it:**
1. Actively seek DISconfirming evidence
2. Maintain multiple hypotheses simultaneously
3. Use structured elimination (not confirmation)
4. Set time limits on each hypothesis
</think>

**Breaking Confirmation Bias in Debugging**

**The pattern you're stuck in:**
```
1. See a bug
2. Form hypothesis: "It's probably X"
3. Look for evidence of X
4. Find something that could be X → "Confirmed!"
5. Spend 3 hours on X
6. Eventually discover it was Y all along
```

**The fix — Hypothesis Elimination Method:**

**Step 1: Generate multiple hypotheses BEFORE investigating**
```
Bug: API returns 500 intermittently

Hypotheses (force yourself to list at least 3):
  H1: Database connection pool exhaustion
  H2: Memory leak causing OOM
  H3: Race condition in request handler
  H4: Upstream service timeout
```

**Step 2: For each hypothesis, define what DISPROVES it**
```
H1 disproved if: Connection pool metrics show no exhaustion
H2 disproved if: Memory usage is stable during failures
H3 disproved if: Failures occur even under single-threaded load
H4 disproved if: No upstream calls during the failing requests
```

**Step 3: Check disproving evidence FIRST**
```
Instead of: "Let me look for signs of H1"
Do: "Let me check if H1 is IMPOSSIBLE"

Check connection pool → pool is fine → H1 eliminated
Check memory → memory is stable → H2 eliminated
Check upstream → upstream timed out during failures → H4 likely!
```

**Why elimination beats confirmation:**
| Approach | Effort | Accuracy |
|----------|--------|----------|
| Confirm first hypothesis | Hours on wrong path | Low |
| Eliminate impossible ones | Minutes per hypothesis | High |

**The rule:** Spend your first 10 minutes trying to DISPROVE your favorite hypothesis. If you can't disprove it, then it gains credibility. If you can disprove it, you just saved hours.'''
    ),
    (
        "thinking/auto-metalearning-escape-complexity-trap",
        r'''I have a tendency to over-engineer solutions. Even when a simple approach would work, I gravitate toward complex abstractions. How do I catch myself doing this and course-correct?''',
        r'''<think>
Over-engineering is a reasoning rut where complexity feels like thoroughness. The engineer thinks "I'm being careful and future-proof" when they're actually making the solution harder to understand, maintain, and debug.

**Root causes of the complexity rut:**
1. Confusing complexity with quality
2. Solving imagined future problems instead of current ones
3. Showing off technical knowledge
4. Fear of refactoring later ("let me get it right the first time")

**The antidote:** Concrete heuristics that force simplicity.
</think>

**Breaking the Over-Engineering Rut**

**Self-diagnostic — you're over-engineering when:**
- You're writing abstractions before you have 2+ concrete use cases
- You're adding "flexibility" nobody asked for
- The solution has more infrastructure than business logic
- You need to explain why it's "not actually that complex"
- You're enjoying the architecture more than solving the problem

**The "Will I Need This?" test:**
```
For every abstraction, ask:
1. Do I need this TODAY? (not "might I someday")
2. How hard would it be to add this LATER if I need it?
3. What's the cost of having it NOW even if I don't need it?

If answers are: No, Easy, High → remove it.
```

**Concrete example:**
```python
# OVER-ENGINEERED: Abstract factory with strategy pattern
class NotificationFactory:
    _strategies = {}
    @classmethod
    def register(cls, channel, strategy):
        cls._strategies[channel] = strategy
    @classmethod
    def create(cls, channel, **kwargs):
        return cls._strategies[channel](**kwargs)

# JUST RIGHT: Simple function
def send_email(to, subject, body):
    smtp.send(to, subject, body)

# When you actually need SMS too, THEN refactor.
```

**The "3 Uses" rule:**
```
1st use: Write the simplest code that works
2nd use: Notice the duplication but tolerate it
3rd use: NOW extract the abstraction (you have 3 examples to guide it)
```

**Rut-breaking triggers:**
| You're thinking... | Replace with... |
|--------------------|--------------------|
| "What if we need to support X later?" | "How hard is it to add X later?" |
| "Let me make this generic" | "Let me make this work for the specific case" |
| "This needs a proper architecture" | "This needs to work correctly" |
| "I should use a design pattern here" | "I should use the simplest thing that works" |

**The meta-principle:** Simple code that works is always better than complex code that works. Complexity should be earned by real requirements, not imagined ones.'''
    ),
    (
        "thinking/auto-metalearning-detect-anchoring-bias",
        r'''When I see a performance problem, I tend to anchor on the first metric I check and optimize for that, even if it's not the real bottleneck. How do I avoid this anchoring in my reasoning?''',
        r'''<think>
Anchoring bias in performance optimization: you check one metric first (e.g., CPU usage), see it's high, and spend days optimizing CPU when the real bottleneck is I/O or network latency.

**Why anchoring happens in performance work:**
- The first metric gives you a "story" to tell
- It feels productive to optimize something measurable
- Investigating further feels like procrastination
- We confuse correlation (CPU is high during slowness) with causation (CPU is CAUSING the slowness)

**Breaking anchoring requires systematic profiling, not selective measurement.**
</think>

**Avoiding Anchoring Bias in Performance Reasoning**

**The anchoring trap:**
```
1. System is slow
2. Check CPU → it's at 80%
3. Anchor: "CPU is the problem"
4. Spend a week optimizing CPU-bound code
5. System is still slow
6. Eventually discover: database queries were the bottleneck
   (CPU was high BECAUSE of busy-waiting on DB responses)
```

**The anti-anchoring protocol:**

**Step 1: Profile EVERYTHING before optimizing ANYTHING**
```
Before touching code, collect ALL metrics:
- CPU usage (user vs. system vs. iowait)
- Memory usage and allocation rate
- Disk I/O (reads, writes, latency)
- Network I/O (bandwidth, latency, connections)
- Database (query count, query time, lock contention)
- Application (request latency P50/P95/P99, error rate)
```

**Step 2: Rank by impact, not by first-seen**
```
Metric           | Value    | Normal | Impact
CPU user         | 80%      | <70%   | Medium
CPU iowait       | 45%      | <5%    | HIGH ← actual bottleneck
Memory           | 60%      | <80%   | Low
DB query time    | 2.3s avg | <100ms | HIGH ← root cause
Network latency  | 2ms      | <5ms   | Low
```

**Step 3: Follow the dependency chain**
```
Why is CPU high? → busy-waiting on I/O
Why is I/O high? → waiting on database
Why are DB queries slow? → missing index on users.email
Fix: Add index → DB queries drop to 5ms → I/O drops → CPU drops to 30%
```

**The "five metrics" rule:**
Never optimize based on fewer than 5 different metrics. The first metric you check has an outsized influence on your reasoning. Force yourself to check at least 5 before forming a hypothesis.

**Anchoring red flags:**
| You're thinking... | Risk |
|--------------------|------|
| "CPU is high, that must be it" | Anchoring on first metric |
| "I know from experience it's usually X" | Anchoring on past patterns |
| "The user said it's slow, so it must be latency" | Anchoring on the complaint |
| "Let me optimize this hot loop" | Anchoring on code you can see |

**The meta-principle:** The first number you see becomes your anchor. Deliberately collect many numbers before interpreting any of them.'''
    ),
    (
        "thinking/auto-metalearning-break-solution-fixation",
        r'''I often get fixated on making my initial approach work even when it's clearly struggling. I'll spend hours patching a bad solution instead of stepping back and trying something different. How do I break this fixation?''',
        r'''<think>
This is the "sunk cost fallacy" applied to solutions. You've invested time in approach A, so switching to approach B feels like "wasting" that investment.

**Why solution fixation happens:**
1. Sunk cost: "I've already spent 3 hours on this"
2. Near-miss illusion: "I'm SO close, just one more fix"
3. Ego: "I should be able to make this work"
4. Switching cost: Starting over feels expensive
5. Tunnel vision: Can't see alternatives because you're deep in one approach

**How to break it:**
- Time-box approaches
- Define "bail-out" criteria BEFORE starting
- Use the "explain to a colleague" test
- Have a structured pivot protocol
</think>

**Breaking Solution Fixation**

**The fixation cycle you're in:**
```
1. Choose approach A
2. Hit a problem → patch it
3. Hit another problem → patch it
4. "I'm almost there" (you're not)
5. Hit a fundamental problem → add a workaround
6. Code is now a mess of patches
7. Still doesn't work
8. Sunk cost keeps you going: "I can't throw away 4 hours of work"
9. After 8 hours, give up and rewrite in 45 minutes with approach B
```

**Prevention: The Time-Box Protocol**
```
BEFORE starting any approach:
1. Set a time limit: "I'll try this for 90 minutes"
2. Define success criteria: "If I can't get X working by then..."
3. Define bail-out criteria: "If I hit more than 3 unexpected issues..."
4. Identify one alternative approach: "If this fails, I'll try Y"
```

**The "3 Patches" Rule:**
```
Patch 1: Normal — every approach needs some adjustment
Patch 2: Concerning — the approach might not fit
Patch 3: STOP — three patches means the approach is wrong

If you need 3+ patches/workarounds, the approach has a
fundamental mismatch with the problem. Patching won't fix it.
```

**The "Explain It" Test:**
When you feel stuck, try explaining your approach out loud:
```
"I'm trying to [goal] by [approach], but I'm running into
[problem], so I added [workaround], but now [new problem]..."

If this explanation sounds convoluted, the approach is wrong.
A good solution should be explainable in 1-2 sentences.
```

**The pivot protocol:**
```
1. STOP writing code
2. Save your current work (branch, stash — don't delete)
3. Step away for 10 minutes (literally walk away)
4. On return, describe the PROBLEM (not your solution) in one sentence
5. Brainstorm 3 different approaches on paper
6. Pick the simplest one
7. Time-box it at 90 minutes
```

**Reframing the sunk cost:**
| Feels like | Reality |
|------------|---------|
| "I'm throwing away 4 hours of work" | "I learned what doesn't work in 4 hours" |
| "I'm so close" | "I've been 'so close' for 2 hours" |
| "Starting over wastes time" | "Continuing wastes MORE time" |
| "I should be able to make this work" | "A better engineer would pivot faster" |

**The meta-principle:** The ability to abandon a failing approach is a skill, not a weakness. The fastest path to a solution often goes through a failed first attempt — but only if you abandon it early enough.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
