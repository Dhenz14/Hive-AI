"""Phase 4D: Self-Improvement — Meta-Learning (Part 6)

Identifying diminishing returns in learning — recognizing when additional
effort in a topic yields progressively less improvement.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-diminishing-returns-detection",
        r'''I've spent weeks optimizing my understanding of SQL query performance. I can now explain B-tree indexes, query plans, and join algorithms. But I feel like each new hour of study teaches me less. How do I know when I've hit diminishing returns?''',
        r'''<think>
Diminishing returns in learning follows a predictable curve. The first 20 hours give you 80% of practical value (the Pareto principle applied to learning). After that, each additional hour yields less.

**Signals of diminishing returns:**
1. New material feels like variations of what you already know
2. You can't find beginner/intermediate resources that teach you anything new
3. The remaining topics are highly specialized edge cases
4. You're optimizing knowledge you'll rarely use in practice
5. Your time would generate more value applied to a different skill

**The question isn't "can I learn more?" (you always can) but "is this the best use of my learning time?"**
</think>

**Detecting Diminishing Returns in Learning**

**The learning value curve:**
```
Value
  |  ****
  | *    ***
  |*        ****
  |             *****
  |                  ********
  |                          ***************
  +----------------------------------------→ Hours
  0    20    50    100   200   500   1000

  Hours 0-20:   Fundamentals (80% of practical value)
  Hours 20-50:  Intermediate (15% of practical value)
  Hours 50-100: Advanced (4% of practical value)
  Hours 100+:   Expert/niche (1% of practical value)
```

**Your SQL knowledge mapped to this curve:**

| Level | Knowledge | Hours | Practical value |
|-------|-----------|-------|-----------------|
| Fundamental | SELECT, JOIN, WHERE, GROUP BY | 0-20 | Covers 80% of work |
| Intermediate | Indexes, EXPLAIN plans, normalization | 20-50 | Covers 95% of work |
| Advanced | Join algorithms, B-tree internals, optimizer hints | 50-100 | Covers 99% of work |
| Expert | Custom statistics, query plan forcing, kernel-level I/O | 100+ | Covers the last 1% |

**You're likely in the 50-100 range, where each hour gives tiny incremental gains.**

**The "next hour" test:**
```
Ask yourself: "What would I learn in the next hour of SQL study?"

If the answer is:
  "How hash joins differ from merge joins in PostgreSQL 16"
  → That's expert-level, rarely applicable

Compare to:
  "How to build REST APIs" (if you don't know this yet)
  → That's fundamental, immediately applicable

The next hour of REST API learning > the next hour of SQL optimization
```

**When to STOP going deeper:**
1. You can solve 95%+ of problems you encounter in this topic
2. The remaining gaps are Google-able when needed
3. New material feels like trivia, not capability
4. A different skill would unlock more opportunities

**When to KEEP going deeper:**
1. You encounter this topic daily and the gaps hurt you
2. You're building expertise for a specialized role (DBA)
3. The advanced knowledge compounds with other skills you have
4. You genuinely enjoy it (learning for its own sake has value)

**The meta-principle:** Diminishing returns is not about reaching a limit — it's about opportunity cost. The question is never "can I learn more?" but "would learning something else create more value?"'''
    ),
    (
        "thinking/auto-metalearning-breadth-vs-depth-tradeoff",
        r'''I can go deeper into my current specialty (backend development) or branch out into frontend, DevOps, or ML. How do I decide when depth has diminishing returns and I should invest in breadth instead?''',
        r'''<think>
The depth vs. breadth tradeoff is one of the most important meta-learning decisions. The optimal strategy depends on career stage, goals, and the shape of the value curve.

**Key insight:** Depth and breadth aren't opposites — they're complements. The most valuable engineers are T-shaped (deep in one area, broad across many) or comb-shaped (deep in 2-3 areas, broad across many).

**When depth wins:**
- Early career (need to establish credibility)
- Specialized roles (DBA, security, ML engineer)
- Competitive differentiation

**When breadth wins:**
- You're leading teams (need to understand all parts)
- Your deep skill is commoditized
- Cross-domain knowledge creates unique combinations
</think>

**The Depth vs. Breadth Decision Framework**

**The T-shaped engineer model:**
```
Breadth: ████████████████████████████████
Depth:          ██
                ██
                ██
                ██  ← Backend (your deep skill)
                ██
```

**When to shift from depth to breadth:**

| Signal | Meaning | Action |
|--------|---------|--------|
| You're the go-to expert already | Depth ROI is diminishing | Add breadth |
| Backend skills alone don't solve your problems | Need cross-functional skills | Add breadth |
| You can't communicate with frontend/DevOps teams | Breadth gap hurts collaboration | Add breadth |
| Your deep skill is becoming automated/commoditized | Depth alone isn't enough | Add breadth urgently |

**When to keep deepening:**

| Signal | Meaning | Action |
|--------|---------|--------|
| You hit walls in backend regularly | Still have valuable depth to gain | Keep deepening |
| Your role requires deep specialization | Breadth isn't rewarded | Keep deepening |
| You're competing for senior/staff roles | Need to demonstrate mastery | Keep deepening |

**The "value multiplication" test:**
```
Pure depth value:
  Expert backend × zero frontend = zero full-stack capability

Depth + breadth value:
  Strong backend × basic frontend = can build complete features
  Strong backend × basic DevOps = can ship and operate systems
  Strong backend × basic ML = can build data-driven features

Breadth MULTIPLIES your depth. Zero breadth makes depth a bottleneck.
```

**The 80/20 breadth strategy:**
```
Don't become an expert in frontend. Just learn enough to:
- Read and modify React components (20 hours)
- Understand CSS layout (10 hours)
- Debug browser network issues (5 hours)

This 35-hour investment lets you:
- Review frontend PRs intelligently
- Build prototypes end-to-end
- Communicate with frontend engineers effectively
```

**The optimal investment schedule:**
```
Year 1-2: 90% depth, 10% breadth (build your core)
Year 3-4: 70% depth, 30% breadth (expand capabilities)
Year 5+:  50% depth, 50% breadth (become T-shaped or comb-shaped)
```

**The meta-principle:** Depth has diminishing returns when the next unit of depth creates less value than the first unit of breadth in an adjacent skill. The crossover point is usually earlier than you think.'''
    ),
    (
        "thinking/auto-metalearning-plateau-vs-stuck",
        r'''How do I tell the difference between a learning plateau (where I need to push through) and genuine diminishing returns (where I should move on)?''',
        r'''<think>
This is a subtle but critical distinction:

**Plateau:** You're not improving because you need to restructure your understanding or change your practice method. Pushing through will eventually lead to a breakthrough.

**Diminishing returns:** You've captured most of the available value. Further effort is genuinely less productive, not just temporarily stalled.

**Key differentiator:** On a plateau, your current practice method is the problem. With diminishing returns, ANY method yields less.

**How to distinguish:**
- Plateau: Changing HOW you practice would help
- Diminishing returns: Changing WHAT you practice would help
</think>

**Plateau vs. Diminishing Returns: A Diagnostic Guide**

**The key distinction:**
```
Plateau:             You're stuck because you're practicing WRONG
Diminishing returns: You're stuck because the topic is EXHAUSTED (for you)
```

**Diagnostic questions:**

| Question | If yes → Plateau | If yes → Diminishing returns |
|----------|------------------|------------------------------|
| "Have I tried different learning approaches?" | No (still using same method) | Yes (tried many approaches) |
| "Do experts know much more than me?" | Yes (clear gap exists) | No (I'm near expert level) |
| "Would a mentor help me level up?" | Yes (they'd show me what I'm missing) | No (they'd say "you know this well") |
| "Am I making the same mistakes?" | Yes (stuck on specific errors) | No (errors are rare edge cases) |
| "Is there a qualitative shift I haven't made?" | Yes (e.g., haven't gone from "using" to "understanding") | No (I understand deeply) |

**Plateau example (push through):**
```
Situation: "I can write SQL queries but can't optimize them"
Diagnosis: PLATEAU
Evidence:
  - Experts clearly know more (they read query plans fluently)
  - I haven't tried different practice (only reading, not doing)
  - There's a qualitative shift: reading → understanding query plans
Fix: Change practice method. Run EXPLAIN on every query for 2 weeks.
```

**Diminishing returns example (move on):**
```
Situation: "I can read query plans, optimize indexes, and tune
           PostgreSQL, but my queries are only 5% slower than
           a DBA's"
Diagnosis: DIMINISHING RETURNS
Evidence:
  - Expert gap is tiny (5% performance difference)
  - I've tried multiple approaches (courses, books, practice)
  - The remaining knowledge is niche (specific to PostgreSQL internals)
Fix: Move on. Learn a new skill. That 5% gap isn't worth the hours.
```

**The "change method" test:**
```
If you've been learning by reading:
  Try building something instead.
  If you improve → it was a plateau (method was wrong).
  If you don't → might be diminishing returns.

If you've been learning by building:
  Try teaching/explaining instead.
  If you improve → it was a plateau.
  If you don't → might be diminishing returns.

If you've tried reading, building, AND teaching:
  It's probably diminishing returns. Move on.
```

**The meta-principle:** A plateau means your learning strategy is wrong. Diminishing returns means your learning target is wrong. The fix for a plateau is to practice differently. The fix for diminishing returns is to practice something different.'''
    ),
    (
        "thinking/auto-metalearning-opportunity-cost-learning",
        r'''I have limited learning time — maybe 5 hours per week. How do I decide which learning investments give the best return, and when should I cut losses on a topic?''',
        r'''<think>
With 5 hours per week, prioritization is everything. This is an optimization problem: maximize learning ROI across limited time.

**Framework needed:**
1. How to estimate ROI of learning a topic
2. How to compare across different topics
3. When to cut losses (sunk cost avoidance)
4. How to avoid the "shiny new thing" trap while also avoiding the "comfort zone" trap
</think>

**Maximizing Learning ROI with Limited Time**

**The learning ROI formula:**
```
Learning ROI = (Value of skill × Likelihood of using it) / Hours to reach useful level

Example comparisons:
  Kubernetes: (High value × Use weekly) / 40 hours = HIGH ROI
  Haskell:    (Medium value × Use rarely) / 100 hours = LOW ROI
  TypeScript: (High value × Use daily) / 20 hours = VERY HIGH ROI
```

**The 5-hour weekly budget allocation:**

**Strategy 1: Focused sprints (recommended)**
```
Month 1: 20 hours → TypeScript fundamentals (high ROI, fast payoff)
Month 2: 20 hours → Docker/Kubernetes basics (high ROI, career value)
Month 3: 20 hours → System design patterns (compounds with experience)
Month 4: 20 hours → Testing strategies (immediate quality improvement)
```

**Strategy 2: Split time (less effective)**
```
Each week: 2.5h TypeScript + 2.5h Kubernetes
Problem: Neither reaches critical mass. You forget between sessions.
```

**The "cut losses" criteria:**

**Cut a learning investment when:**
```
1. After 10 hours, you can't see how it applies to your work
2. You dread the study sessions (motivation death spiral)
3. The field is moving so fast your learning is obsolete by the time you finish
4. Someone on your team already has this skill (diminishing team value)
5. You've learned enough to know when to Google the rest
```

**DON'T cut when:**
```
1. It's hard but clearly valuable (discomfort ≠ diminishing returns)
2. You're on a plateau but haven't tried changing methods
3. The payoff is delayed but real (e.g., learning algorithms for interviews)
4. You're 80% through the hard part
```

**The prioritization matrix:**
```
                    USE FREQUENTLY    USE RARELY
                 ┌─────────────────┬──────────────────┐
HIGH VALUE       │ LEARN FIRST     │ LEARN WHEN NEEDED│
                 │ (TypeScript,    │ (ML, if not your │
                 │  Docker, SQL)   │  primary role)   │
                 ├─────────────────┼──────────────────┤
LOW VALUE        │ LEARN MINIMALLY │ SKIP             │
                 │ (obscure tool   │ (niche language   │
                 │  you use daily) │  you'll never use)│
                 └─────────────────┴──────────────────┘
```

**The meta-principle:** With limited time, the biggest risk isn't learning the wrong thing — it's spending too long on one thing when the marginal hour would be better spent elsewhere. Review your learning allocation monthly.'''
    ),
    (
        "thinking/auto-metalearning-when-to-go-deep",
        r'''Are there topics where diminishing returns don't really apply — where going extremely deep continues to pay off? How do I identify those?''',
        r'''<think>
Yes, some topics have "increasing returns" — where deeper knowledge compounds and becomes exponentially more valuable. These are typically foundational topics where depth unlocks capabilities that breadth cannot.

**Characteristics of "always worth going deeper" topics:**
1. They're foundational — everything else builds on them
2. Deep knowledge compounds over time
3. They transfer across domains and technologies
4. They change slowly (long shelf-life)
5. Most people stop at surface level, so depth is a differentiator

**Examples:**
- Algorithms and data structures
- Operating systems internals
- Networking fundamentals
- Mathematics for CS
- Writing and communication
- Problem decomposition
</think>

**Topics Where Depth Always Pays Off**

**The "compounding knowledge" test:**
```
Does deeper knowledge in this topic make EVERY OTHER SKILL better?
  Yes → Depth has increasing returns
  No  → Depth has normal diminishing returns
```

**Topics with increasing returns to depth:**

**1. Fundamentals (long shelf-life, universal applicability)**
```
Topic: Algorithms & Data Structures
Why depth compounds:
  - Every programming problem is an algorithm problem underneath
  - Deep understanding lets you SEE the algorithm in any domain
  - Knowledge is timeless (quicksort hasn't changed in 60 years)
  - Most developers stop at "I can pass an interview"
    → Going deeper is a career differentiator
```

**2. Communication and writing**
```
Topic: Technical communication
Why depth compounds:
  - Every technical skill is multiplied by your ability to explain it
  - Senior/staff roles are increasingly about communication
  - Writing skill transfers to: docs, emails, PRs, design docs, talks
  - Improvement never stops being valuable
```

**3. Systems thinking**
```
Topic: How systems work at a low level (OS, networking, memory)
Why depth compounds:
  - Every abstraction leak eventually requires this knowledge
  - Debugging complex issues requires understanding the full stack
  - The developer who understands the machine outperforms at every level
  - This knowledge is rare and becoming rarer
```

**4. Problem decomposition**
```
Topic: Breaking complex problems into simple ones
Why depth compounds:
  - Applies to EVERY problem in EVERY domain
  - Gets better with practice and never maxes out
  - The #1 skill that separates senior from junior engineers
  - Can't be automated or commoditized
```

**Topics with NORMAL diminishing returns (depth caps out):**

| Topic | Useful depth | Beyond this → diminishing |
|-------|-------------|--------------------------|
| Specific framework (React, Django) | Intermediate-advanced | Framework-specific tricks |
| Specific language syntax | Fluent usage | Obscure language features |
| Specific tool (Webpack, Docker) | Confident usage | Internal implementation details |
| Specific database (PostgreSQL) | Optimization + operations | Source code internals |

**The identifying heuristic:**
```
If the topic has existed for 20+ years and is still relevant → depth pays off
If the topic is younger than 5 years → depth may not persist
If the topic applies to all programming → depth pays off
If the topic applies to one framework → depth diminishes
```

**The meta-principle:** Go deepest on topics that are old, foundational, and universal. Go broadest on topics that are new, specific, and changing. The best career investment is deep fundamentals plus broad modern tooling.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
