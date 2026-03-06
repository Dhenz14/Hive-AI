"""Phase 4D: Self-Improvement — Meta-Learning (Part 9)

Adaptive learning rate — knowing when to dive deep into a topic
versus when to skim for a broad overview, and calibrating depth
to the situation.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-depth-vs-breadth-signals",
        r'''How do I decide when to dive deep into a technology versus just getting a surface-level understanding? I feel like I either spend too long on things that don't matter or skim things I should know deeply.''',
        r'''<think>
This is a meta-learning calibration problem. The optimal learning depth depends on context: your role, the technology's relevance to your work, and how quickly the technology is evolving.

**Framework for deciding depth:**
1. How often will I use this? (daily → deep, rarely → skim)
2. How critical is correctness? (security/data → deep, UI polish → skim)
3. How stable is the technology? (mature → invest deeply, bleeding-edge → skim until it stabilizes)
4. Am I a user or a contributor? (building on top → moderate, contributing to → deep)
5. Can I look it up when I need it? (yes → skim, no → deep)
</think>

**Calibrating Learning Depth: The Decision Framework**

**The depth levels:**
```
Level 0: AWARENESS — "I know this exists"
  Time: 5-15 minutes (read a blog post or overview)
  Goal: Know when to reach for it, recognize it in conversations
  Example: "Rust has a borrow checker that prevents memory bugs"

Level 1: WORKING KNOWLEDGE — "I can use the basics"
  Time: 2-8 hours (tutorial + small project)
  Goal: Accomplish common tasks, read others' code
  Example: Can write a basic Rust program, understand ownership

Level 2: PROFICIENCY — "I can build real things"
  Time: 40-100 hours (projects, reading docs thoroughly)
  Goal: Handle edge cases, make design decisions, debug issues
  Example: Can architect a Rust application, handle lifetimes

Level 3: EXPERTISE — "I can teach it and push its limits"
  Time: 500+ hours (deep projects, contribution, teaching)
  Goal: Know the internals, optimize, mentor others
  Example: Can write unsafe Rust, contribute to the compiler
```

**The decision matrix:**

| Factor | Skim (Level 0-1) | Deep (Level 2-3) |
|--------|-------------------|-------------------|
| Use frequency | Monthly or less | Daily or weekly |
| Failure cost | Low (can be fixed easily) | High (data loss, security, outage) |
| Technology maturity | Bleeding edge (may change) | Stable (investment won't be wasted) |
| Your role | Consumer/user | Builder/architect |
| Team dependency | Others on the team know it | You're the primary owner |
| Lookupability | Easy to reference docs | Needs internalized knowledge |

**Concrete examples:**

```
SKIM — Level 0-1:
  - A CSS framework your team uses (reference docs when needed)
  - A monitoring tool you check weekly (learn the dashboard)
  - A language your colleague's microservice uses (read, not write)
  - A new JavaScript framework (wait until it stabilizes)

DEEP — Level 2-3:
  - Your primary programming language
  - The database your app relies on (query optimization, indexing)
  - Security practices for your authentication system
  - The framework your main application is built on
  - Debugging and profiling tools for your stack
```

**The "just-in-time" vs. "just-in-case" rule:**
```
Just-in-time learning (skim now, deepen when needed):
  "I'll learn Kubernetes deeply when we actually need to deploy
   containers. For now, I know what it does."

Just-in-case learning (invest now):
  "SQL is fundamental to my work. I should understand query
   plans, indexing strategies, and transaction isolation levels
   even if I don't need them today — I WILL need them."

Rule of thumb:
  Foundational skills → just-in-case (invest deeply)
  Specific tools → just-in-time (skim until needed)
```

**The "regret minimization" test:**
```
Ask yourself:
  "If I DON'T learn this deeply and need it in 6 months,
   how bad would that be?"

  - "I'd spend a day learning it then" → skim now
  - "I'd cause a production outage" → learn deeply now
  - "I'd make a bad architecture decision" → learn deeply now
  - "I'd feel behind in conversations" → skim is fine
```

**The meta-principle:** Learning depth should be proportional to the cost of ignorance. If not knowing something deeply could cause significant harm (security, data loss, bad architecture), invest heavily. If the worst case is spending a day learning it later, skim now and invest your deep-learning time where it matters most.'''
    ),
    (
        "thinking/auto-metalearning-when-to-stop-learning",
        r'''When learning a new technology, I often go down rabbit holes and spend days on details I never end up using. How do I know when I've learned "enough" and should stop studying and start building?''',
        r'''<think>
The "rabbit hole" problem is extremely common, especially among curious developers. The underlying issue is that learning feels productive (and it is, to a point), but past a certain threshold, you get diminishing returns. You need a framework for recognizing when you've crossed from "productive learning" to "procrastination disguised as learning."

**Signs you've learned enough:**
1. You can explain the concept to someone else
2. You can start a real task without immediately getting stuck
3. You understand the 80% case even if edge cases are fuzzy
4. You know where to look up what you don't know
5. You're reading about increasingly niche scenarios

**Signs you're in a rabbit hole:**
1. You're reading about problems you don't have
2. You're optimizing before you have anything to optimize
3. You're comparing 5 libraries when any would work
4. You've been reading for 2+ hours without writing code
5. The material is interesting but not relevant to your task
</think>

**Knowing When to Stop Learning and Start Building**

**The "good enough" threshold:**
```
You've learned enough when you can:
  1. Start the task without being blocked immediately
  2. Recognize when you're stuck (and know what to search for)
  3. Explain the basic concepts in your own words
  4. Identify the major pitfalls to avoid

You DON'T need to:
  - Understand every edge case
  - Know the internal implementation
  - Have read the entire documentation
  - Have compared every alternative
```

**The rabbit hole detection checklist:**
```
Ask yourself every 30 minutes of learning:

□ "Am I learning something I need for my CURRENT task?"
  → No? Stop. Bookmark it for later.

□ "Could I start building with what I know now?"
  → Yes? Stop learning. Start building.

□ "Am I reading about problems I don't have yet?"
  → Yes? Stop. Solve problems when you have them.

□ "Am I comparing options when any option would work?"
  → Yes? Pick one. You can switch later if needed.

□ "Have I been reading for more than 2 hours without coding?"
  → Yes? Write some code, even if it's wrong.
```

**The "20-minute rule":**
```
For any new technology:
  1. Spend 20 minutes reading the overview/getting started guide
  2. Spend 20 minutes writing a minimal "hello world"
  3. Spend 20 minutes trying to do YOUR specific task

After 60 minutes, you should be either:
  - Making progress → keep building, learn as you go
  - Completely stuck → do targeted learning on the specific blocker
  - Realizing this isn't the right tool → switch

NEVER spend more than 2 hours reading before writing code.
```

**The learn-build cycle:**
```
WRONG approach (the rabbit hole):
  Read docs (3 hours) → Read blog posts (2 hours) →
  Watch tutorials (3 hours) → Read more docs (2 hours) →
  Still haven't written any code

RIGHT approach (iterative):
  Read basics (30 min) → Build something small (30 min) →
  Hit a problem → Learn about THAT problem (15 min) →
  Build more (30 min) → Hit another problem → Learn more →
  Build more → ...

  Learning is driven by REAL problems, not hypothetical ones.
```

**Common rabbit holes and how to escape:**

| Rabbit hole | Escape |
|-------------|--------|
| Comparing 5 frameworks | Pick the one with best docs. Switch later if needed. |
| Reading about advanced features | Use basic features first. Learn advanced when you need them. |
| Optimizing before building | Make it work, THEN make it fast. |
| Understanding internals | You don't need to know how the engine works to drive the car. |
| Reading every blog post | One official tutorial is worth ten blog posts. |

**The meta-principle:** Learning and building are not sequential phases — they're an interleaved loop. The fastest way to learn a technology is to build something with it and let real problems drive your learning. Every minute spent learning about a problem you don't have is a minute stolen from solving problems you do have.'''
    ),
    (
        "thinking/auto-metalearning-learning-priority-queue",
        r'''I have a long list of technologies I want to learn but limited time. How do I prioritize what to learn next in a way that maximizes my effectiveness?''',
        r'''<think>
Technology learning prioritization is a resource allocation problem. You have finite learning time and a potentially infinite list of things to learn. The key is maximizing the return on your learning investment.

**Prioritization factors:**
1. Impact on current work (immediate ROI)
2. Career trajectory alignment (future ROI)
3. Foundational vs. trendy (longevity of the knowledge)
4. Synergy with existing skills (faster learning, compounding value)
5. Market demand (employability)

**The trap:** Many developers prioritize based on "what's exciting" or "what's trending on Hacker News" rather than "what would make the biggest difference in my work."
</think>

**Technology Learning Priority Queue**

**The prioritization matrix:**

```
                    HIGH impact on your work
                           │
        ┌──────────────────┼──────────────────┐
        │   LEARN NEXT     │   LEARN FIRST    │
        │ (High impact,    │ (High impact,    │
        │  takes long)     │  quick to learn) │
        │ e.g., New lang   │ e.g., Better     │
        │ for your stack   │ git workflow      │
Long ───┼──────────────────┼──────────────────┤─── Quick
to      │   LEARN LATER    │   LEARN WHEN     │    to
learn   │ (Low impact,     │   BORED          │    learn
        │  takes long)     │ (Low impact,     │
        │ e.g., Niche      │  quick to learn) │
        │ language          │ e.g., New CSS    │
        │                  │  feature          │
        └──────────────────┼──────────────────┘
                           │
                    LOW impact on your work
```

**Priority tiers:**

**Tier 1: Learn NOW (blocks your current effectiveness)**
```
- Skills you need for your current project
- Gaps that cause you to be slow or make mistakes daily
- Tools your team has adopted that you're behind on

Examples:
  - Your team uses TypeScript and you only know JavaScript
  - You write SQL daily but don't understand query plans
  - Your deploys are manual and you need CI/CD
```

**Tier 2: Learn THIS QUARTER (multiplies your effectiveness)**
```
- Skills that would make you significantly faster
- Technologies on your team's roadmap
- Foundational knowledge gaps

Examples:
  - Docker/containers if your team is containerizing
  - Testing frameworks if your code is untested
  - Performance profiling if you're solving perf issues
```

**Tier 3: Learn THIS YEAR (career investment)**
```
- Skills aligned with where your career is heading
- Emerging technologies that are stabilizing
- Deep expertise in your core stack

Examples:
  - System design if you're moving toward senior/staff
  - A second programming language paradigm (FP if you know OOP)
  - Cloud architecture if you're moving toward platform eng
```

**Tier 4: Learn SOMEDAY (nice to have)**
```
- Interesting but not impactful right now
- Unstable/experimental technologies
- Skills for roles you're not pursuing

Move to a higher tier if circumstances change.
```

**The "learning ROI" calculation:**
```
For each technology on your list, estimate:

  Impact = How much faster/better would I be? (1-10)
  Frequency = How often would I use this? (1-10)
  Learning cost = How long to reach useful proficiency? (hours)

  ROI = (Impact x Frequency) / Learning Cost

Example:
  Learn Docker:  Impact=7, Frequency=8, Cost=20h → ROI = 2.8
  Learn Haskell: Impact=3, Frequency=1, Cost=200h → ROI = 0.015
  Learn vim:     Impact=4, Frequency=10, Cost=40h → ROI = 1.0

  Priority: Docker → vim → Haskell
```

**The "compound interest" principle:**
```
Some skills compound — they make learning other things faster:

HIGH compound value:
  - Touch typing (makes EVERYTHING faster)
  - Git (every project uses it)
  - SQL (most apps need databases)
  - Terminal/CLI proficiency (accelerates all dev work)
  - Reading documentation effectively (meta-skill)
  - Debugging methodology (applies everywhere)

LOW compound value:
  - A specific UI library (changes every 2 years)
  - A specific cloud provider's console UI
  - A specific build tool's config syntax
```

**The meta-principle:** Prioritize learning that compounds. Foundational skills (algorithms, system design, debugging methodology) pay dividends across every project for your entire career. Specific tool knowledge (this year's hot framework) has a short shelf life. Invest your deep-learning time in foundations and your skim-learning time in tools.'''
    ),
    (
        "thinking/auto-metalearning-recognizing-diminishing-returns",
        r'''How do I recognize when I've hit diminishing returns in learning a topic and should move on to something else that would give me more value per hour invested?''',
        r'''<think>
Diminishing returns in learning follow a predictable curve. The first hours of learning a new topic have enormous ROI — you go from "know nothing" to "can do basic things." But as you go deeper, each additional hour yields less new capability.

**The learning curve:**
- Hours 1-5: Rapid progress (0% → 60% useful knowledge)
- Hours 5-20: Good progress (60% → 85%)
- Hours 20-100: Slow progress (85% → 95%)
- Hours 100-500: Very slow progress (95% → 99%)
- Hours 500+: Diminishing returns (99% → 99.5%)

**The key insight:** For most technologies, the 80/20 rule applies — 20% of the knowledge handles 80% of the use cases. The last 20% of knowledge takes 80% of the learning time.
</think>

**Recognizing Diminishing Returns in Learning**

**The learning ROI curve:**
```
Knowledge
Gained    │           ╭────────────── 99% (expert)
(%)       │          ╱
          │        ╱
          │      ╱  ← Sweet spot (stop here for most things)
          │    ╱     85-90% handles almost all real situations
          │  ╱
          │╱
          └────────────────────────── Time invested
          0    20    50   100   500

  Hours 1-20:  Massive ROI. Learning the fundamentals.
  Hours 20-50: Good ROI. Handling common edge cases.
  Hours 50+:   Diminishing ROI. Rare scenarios, deep internals.
```

**Signals you've hit diminishing returns:**

```
Signal 1: THE PROBLEMS ARE INCREASINGLY RARE
  Early: "How do I connect to a database?" (daily problem)
  Later: "How do I handle connection pool exhaustion under
          heavy load with SSL renegotiation?" (yearly problem)
  → If the problem you're studying happens rarely, stop.

Signal 2: YOU'RE LEARNING EXCEPTIONS TO EXCEPTIONS
  Early: "How does async/await work?" (the rule)
  Later: "What happens when a Task is awaited in a
          SynchronizationContext after a ConfigureAwait(false)
          in a nested async lambda?" (exception to exception)
  → If you need 3 qualifiers to describe what you're learning, stop.

Signal 3: THE CONTENT IS ABOUT INTERNALS, NOT USAGE
  Early: "How do I use PostgreSQL indexes?" (practical)
  Later: "How does PostgreSQL's B-tree page split algorithm
          handle concurrent inserts?" (internal implementation)
  → Unless you're contributing to PostgreSQL itself, stop.

Signal 4: YOU CAN'T THINK OF WHEN YOU'D USE THIS
  Ask: "When would I use what I'm learning right now?"
  If you can't answer with a specific scenario from your work → stop.

Signal 5: YOU'RE RE-READING THE SAME CONCEPTS
  If you keep encountering the same ideas rephrased → you've
  absorbed the core material. More reading won't help.
  Start building something instead.
```

**The "good enough" levels by topic:**

| Topic | Good enough for most devs | Deep dive only if... |
|-------|---------------------------|---------------------|
| SQL | Joins, indexes, transactions | You're a DBA or performance engineer |
| Git | Commit, branch, merge, rebase | You're building Git tooling |
| Docker | Build, run, compose | You're managing infrastructure |
| HTTP | Methods, status codes, headers | You're building a web framework |
| Regex | Basic patterns, groups, quantifiers | You're writing a parser |
| CSS | Flexbox, Grid, responsive design | You're a design system engineer |

**The "teach it" test:**
```
Can you explain the topic to a colleague in 5 minutes?
  → Yes: You've learned enough. Build something or move on.
  → Almost: Spend 1 more hour consolidating.
  → No: You haven't learned the basics yet. Keep going.

Can you explain the topic in 30 minutes with examples?
  → Yes: You have working proficiency. Good enough for most roles.
  → No: You're still in the rapid-learning phase. Keep going.

Can you explain the topic for an hour, answering edge-case questions?
  → Yes: You have expertise. Diminishing returns start here.
  → No: You may need this depth if it's a core skill.
```

**The meta-principle:** Every hour you spend going from 90% to 95% knowledge in one topic is an hour you could spend going from 0% to 60% in another topic. Unless the topic is your core specialty, stop at "good enough" and redirect your learning time to where the ROI is highest. Breadth at 85% beats depth at 99% for most careers.'''
    ),
    (
        "thinking/auto-metalearning-learning-speed-self-assessment",
        r'''How do I assess whether I'm learning at a reasonable pace or if I'm being inefficient? What are the benchmarks for learning speed in software development?''',
        r'''<think>
Learning speed is hard to benchmark because it varies enormously based on:
- Prior experience (related skills transfer)
- Learning method (reading vs. building vs. teaching)
- Quality of learning resources
- Individual cognitive differences
- Complexity of the topic

But developers often compare themselves unfavorably to others (or to tutorial timelines), leading to impostor syndrome. Having rough benchmarks helps calibrate expectations.

**General benchmarks:**
- New programming language (if you know one): 2-4 weeks to be productive
- New framework: 1-2 weeks for basics, 1-3 months for proficiency
- New paradigm (OOP→FP): 2-6 months to think naturally in it
- New domain (web→embedded): 3-6 months to be productive
</think>

**Learning Speed Self-Assessment**

**Rough benchmarks (for a developer with 2+ years experience):**

```
TOPIC                          BASIC USAGE    PROFICIENCY    EXPERTISE
New language (similar paradigm)  1-2 weeks    1-3 months     1-2 years
New language (different paradigm) 2-4 weeks   3-6 months     2-3 years
New framework                    3-5 days     1-3 months     6-12 months
New tool (Docker, Git, etc.)     1-2 days     2-4 weeks      3-6 months
New concept (async, generics)    1-3 days     2-4 weeks      2-3 months
New domain (web → mobile)        2-4 weeks    3-6 months     1-2 years
```

**Note:** These assume focused learning. Part-time learning takes 3-5x longer in calendar time.

**Signs you're learning EFFICIENTLY:**

```
1. You're building things, not just reading
   Efficient: Read 30 min → code 60 min → read more → code more
   Inefficient: Read 8 hours → still haven't written code

2. You're solving real problems
   Efficient: "I need to build X, so I'm learning Y to accomplish it"
   Inefficient: "I'm going through the entire tutorial from start to finish"

3. Your questions are getting more specific
   Day 1: "How does React work?"
   Day 5: "How do I handle stale closures in useEffect?"
   → Questions becoming specific = progress

4. You can explain what you learned yesterday
   If you can articulate it → it's sticking
   If you can't → you're reading without absorbing

5. You're making NEW mistakes (not repeating old ones)
   New mistakes = exploring new territory = learning
   Same mistakes = not absorbing = inefficient
```

**Signs you're learning INEFFICIENTLY:**

```
1. Tutorial hell: Completing tutorials but can't build without one
   Fix: Close the tutorial. Build something from scratch.
        Get stuck. Look up the specific thing you're stuck on.

2. Passive consumption: Watching videos at 2x speed, feeling
   productive but retaining nothing
   Fix: After every 15 minutes of video, pause and implement
        what you just watched.

3. Breadth without depth: "I've read about 20 tools but
   can't use any of them"
   Fix: Pick ONE tool and build a real project with it.

4. Perfectionism: Refusing to move on until you understand
   everything about chapter 3
   Fix: Accept 80% understanding and move forward.
        Gaps fill in naturally with practice.

5. No output: You've been "learning" for a month but have
   nothing to show for it (no projects, no notes, no code)
   Fix: Produce something every week. A tiny project,
        a blog post, a code snippet.
```

**The learning efficiency formula:**
```
Efficiency = (Capability gained) / (Time invested)

Maximize by:
  - Active learning (building > reading > watching)
  - Spaced repetition (review yesterday's learning today)
  - Interleaving (alternate between topics to improve retention)
  - Teaching (explain to someone else — best retention method)
  - Deliberate practice (work on things just beyond your ability)

Minimize waste:
  - Don't re-learn things you already know (skip familiar sections)
  - Don't learn things you'll never use (apply the priority queue)
  - Don't optimize your learning setup for longer than 30 minutes
    (the tool doesn't matter as much as the practice)
```

**The meta-principle:** The most reliable signal of learning speed is your ability to build increasingly complex things independently. If you can build something today that you couldn't build last week, you're learning at a good pace. If you've consumed hours of content but your building ability hasn't changed, you need to switch to a more active learning method.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
