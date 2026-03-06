"""Phase 4C: Self-Improvement — Curriculum Design (Part 2)

The model designs targeted curricula for specific skill gaps and assessment strategies.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-assess-skill-level",
        r'''How do I assess a developer's skill level accurately? I'm trying to figure out whether a new team member needs training on databases, and if so, at what level.''',
        r'''<think>
To assess database skill level, I need:
1. A progressive set of questions/tasks that span beginner → advanced
2. The ability to identify WHERE the learner's understanding breaks down
3. Questions that reveal understanding, not just memorization

**Assessment approach:** Ask questions at increasing depth. When the person can't answer confidently, that's their growth edge.

**The mistake to avoid:** Asking trivia (What does ACID stand for?) instead of applied questions (When would you choose eventual consistency over strong consistency?). Trivia tests memorization. Applied questions test understanding.
</think>

**Database Skill Assessment Framework**

**Level 1: Basics (Can they use a database?)**
```
Task: "Write a query to find all users who signed up last month."
Expected: SELECT * FROM users WHERE created_at >= '2024-01-01' AND created_at < '2024-02-01'

Task: "The users table needs a new column for phone number. Write the migration."
Expected: ALTER TABLE users ADD COLUMN phone VARCHAR(20);

Red flags: Can't write basic SELECT/WHERE, unsure about JOIN syntax
```

**Level 2: Competent (Can they design schemas?)**
```
Task: "Design tables for an e-commerce system with users, products, orders, and reviews."
Expected: Proper normalization, foreign keys, appropriate types, many-to-many via junction table

Task: "This query is slow on 1M rows. Why and how would you fix it?"
SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC;
Expected: Add index on (user_id, created_at), use EXPLAIN to verify
```

**Level 3: Proficient (Can they optimize?)**
```
Task: "Explain the difference between a hash index and a B-tree index. When would you use each?"
Expected: B-tree for range queries and ordering, hash for exact match only

Task: "Our orders table has 100M rows. Queries by date range are slow despite having an index. What could be wrong?"
Expected: Mentions partition pruning, index selectivity, covering indexes, VACUUM/ANALYZE
```

**Level 4: Expert (Can they architect?)**
```
Task: "We need to support 50K writes/second. Our single PostgreSQL instance handles 5K. What's your scaling strategy?"
Expected: Read replicas, partitioning, sharding considerations, queueing writes, caching reads

Task: "When would you choose eventual consistency over strong consistency?"
Expected: Discusses CAP theorem pragmatically, gives concrete examples (likes counter vs bank balance)
```

**Assessment protocol:**
1. Start at Level 2 (assume basics)
2. If they struggle → drop to Level 1
3. If they answer confidently → move to Level 3
4. The level where they start saying "I'm not sure" is their growth edge
5. Design training starting from that level'''
    ),
    (
        "thinking/auto-curriculum-design-practice-problems",
        r'''Design a set of progressively harder practice problems for learning recursion. The problems should build on each other and cover the key recursive patterns.''',
        r'''<think>
Key recursive patterns to cover:
1. Simple recursion (factorial, countdown)
2. Recursive accumulation (sum of list)
3. Tree/graph traversal (filesystem, DOM)
4. Divide and conquer (merge sort, binary search)
5. Backtracking (permutations, maze solving)
6. Dynamic programming connection (fibonacci → memoization)

Progression strategy:
- Start with problems where iteration is obviously equivalent (teach the BASE CASE concept)
- Move to problems where recursion is natural (trees)
- End with problems where recursion is the ONLY clean approach (backtracking)

Each problem should introduce ONE new recursive concept.
</think>

**Progressive Recursion Problem Set**

**Problem 1: Base case + single recursion (Warmup)**
```
Write countdown(n) that prints n, n-1, ..., 1, "Blastoff!"
Expected insight: The base case (n == 0) stops the recursion.

countdown(3) → 3, 2, 1, Blastoff!
```
*New concept: base case prevents infinite recursion*

**Problem 2: Return value accumulation**
```
Write sum_list(numbers) that returns the sum WITHOUT using a loop.
sum_list([1, 2, 3, 4]) → 10

Hint: sum_list([1, 2, 3, 4]) = 1 + sum_list([2, 3, 4])
```
*New concept: combining the current element with the recursive result*

**Problem 3: Multiple base cases**
```
Write fibonacci(n) that returns the nth Fibonacci number.
fibonacci(6) → 8  (0, 1, 1, 2, 3, 5, 8)

Then: Why is this slow for fibonacci(40)? Draw the call tree.
```
*New concept: multiple recursive calls → exponential blowup → memoization*

**Problem 4: Tree traversal (recursion is natural)**
```
Given a file system as nested dicts, find all files with a given extension:
fs = {
    "src": {
        "app.py": 100,
        "utils": {"helper.py": 50, "data.csv": 200}
    },
    "README.md": 10
}
find_files(fs, ".py") → ["src/app.py", "src/utils/helper.py"]
```
*New concept: recursive data structures (trees) require recursive solutions*

**Problem 5: Divide and conquer**
```
Implement merge_sort(arr):
1. Split array in half
2. Recursively sort each half
3. Merge sorted halves

merge_sort([3, 1, 4, 1, 5, 9]) → [1, 1, 3, 4, 5, 9]
```
*New concept: divide problem into subproblems, combine results*

**Problem 6: Backtracking**
```
Generate all permutations of a list:
permutations([1, 2, 3]) → [[1,2,3], [1,3,2], [2,1,3], [2,3,1], [3,1,2], [3,2,1]]

Key insight: Choose an element, recurse on the rest, then UN-choose (backtrack).
```
*New concept: explore all possibilities by trying and undoing choices*

**Problem 7: Capstone — Sudoku solver**
```
Solve a 9×9 Sudoku puzzle using backtracking:
1. Find empty cell
2. Try digits 1-9
3. If valid, recurse to next empty cell
4. If stuck, backtrack (undo choice)
```
*Combines: base case, backtracking, constraint checking, tree search*

**Concept progression:**
| Problem | New concept | Builds on |
|---------|------------|-----------|
| 1 | Base case | — |
| 2 | Accumulation | Base case |
| 3 | Multiple calls + memoization | Accumulation |
| 4 | Tree traversal | Multiple calls |
| 5 | Divide and conquer | Tree traversal |
| 6 | Backtracking | Divide and conquer |
| 7 | Complex backtracking | All above |'''
    ),
    (
        "thinking/auto-curriculum-identify-learning-plateau",
        r'''A developer has been an "intermediate" for 3 years. They can build features but struggle with system design, debugging complex issues, and writing maintainable code. How do they break through the plateau?''',
        r'''<think>
The "intermediate plateau" is a well-known phenomenon. Let me diagnose why it happens and how to break through.

**Why intermediates plateau:**
1. They can solve problems they've seen before but can't reason about novel ones
2. They copy patterns without understanding WHY those patterns work
3. They never read other people's code (only write their own)
4. They build features but don't operate systems (never on-call, never debug production)
5. They lack mental models for reasoning about system behavior

**The gap between intermediate and senior:**
- Intermediate: "I can build what you ask me to build"
- Senior: "I can figure out WHAT to build, HOW to build it well, and WHY it breaks"

**Breaking the plateau requires different learning activities than what got them to intermediate.**
- Getting to intermediate: tutorials, building projects, learning syntax
- Getting to senior: reading code, debugging production, designing systems, teaching others
</think>

**Breaking the Intermediate Plateau**

**Diagnosis: Why intermediates stay intermediate**
| Intermediate habit | Senior alternative |
|-------------------|-------------------|
| Only writes new code | Reads and reviews other people's code |
| Builds features in isolation | Designs systems end-to-end |
| Googles error messages | Reads stack traces and reasons about root causes |
| Uses frameworks without understanding | Understands how frameworks work internally |
| Solves familiar problems | Reasons about novel problems from first principles |

**The Plateau-Breaking Curriculum:**

**1. Read code, not just write it (ongoing)**
```
- Read one popular open-source project per month
  Start with: Flask (simple), then Django (complex), then CPython (mind-expanding)
- During code review: don't just approve — ask "why was it done this way?"
- Read post-mortems from other companies (Google, Cloudflare, GitHub engineering blogs)
```

**2. Debug production issues (3 months of practice)**
```
- Volunteer for on-call rotation
- When a bug is reported, resist googling — reason from first principles:
  "What changed? What are the symptoms? What could cause those symptoms?"
- Practice with: distributed tracing, reading logs, EXPLAIN ANALYZE
- Keep a debugging journal: what was the bug, how did you find it, what would you check first next time?
```

**3. Design before building (2 months of practice)**
```
- Before every feature: write a 1-page design doc
  "What are the requirements? What are the tradeoffs? What could go wrong?"
- Practice system design problems (weekly, 1 hour each):
  "Design a URL shortener / chat system / rate limiter"
- Review your designs after implementation: what did you miss?
```

**4. Teach what you know (ongoing)**
```
- Write blog posts explaining concepts
- Mentor a junior developer
- Give internal tech talks
- The act of teaching reveals gaps in your understanding
```

**5. Study failures, not just successes**
```
- Read post-mortems: what went wrong and why?
- After your own bugs: write a blameless retrospective
- Study: the Therac-25 accidents, the Knight Capital trading loss,
  the Cloudflare outage write-ups
```

**Key insight:** The plateau exists because the learning activities that work for beginners (tutorials, building projects) stop working for intermediates. Breaking through requires fundamentally different activities: reading code, debugging unknowns, designing systems, and teaching others.'''
    ),
    (
        "thinking/auto-curriculum-adapt-to-learner",
        r'''I'm teaching two different people Python: one is a 15-year-old interested in game development, the other is a 45-year-old accountant who wants to automate spreadsheet tasks. How should I adapt the curriculum?''',
        r'''<think>
Same language, completely different curricula. Let me design for each learner's context:

**15-year-old game dev:**
- Motivation: Making games, visual feedback, cool projects
- Learning style: Experimentation, immediate gratification, visual
- Strength: Comfortable with computers, fast learner, lots of time
- Weakness: May lack patience for fundamentals without visible results
- Key: Every lesson must produce something VISUAL and INTERACTIVE

**45-year-old accountant:**
- Motivation: Saving time on repetitive spreadsheet tasks
- Learning style: Practical, problem-first, needs clear ROI
- Strength: Domain expertise (accounting), understands data and formulas
- Weakness: May feel intimidated, less time available, needs immediate relevance
- Key: Every lesson must solve a REAL PROBLEM they currently do manually
</think>

**Two curricula, same language, different worlds.**

**Curriculum A: 15-Year-Old Game Developer**

*Principle: Visual feedback in every lesson. Build games from day 1.*

```
Week 1: pygame basics
  - Day 1: Display a window with a colored background (5 min to visual result)
  - Day 2: Draw shapes and images on screen
  - Day 3: Move a character with keyboard input
  - Day 4: Add collision detection
  - Project: Pong clone (teaches variables, loops, conditionals through gameplay)

Week 2: Game mechanics
  - Scoring system (variables, math)
  - Multiple levels (functions, state management)
  - Sound effects and music
  - Project: Space invaders

Week 3-4: More complex games
  - Procedural generation (randomness, algorithms)
  - Save/load game state (file I/O, JSON)
  - High score leaderboard
  - Project: Roguelike dungeon crawler

Week 5+: Multiplayer/networking
  - Sockets basics
  - Simple multiplayer game
```

**How fundamentals sneak in:**
| Game concept | Python concept it teaches |
|-------------|--------------------------|
| Player position (x, y) | Variables, tuples |
| Moving 60 times/sec | While loops |
| "If touching enemy" | Conditionals, collision |
| Drawing all enemies | For loops, lists |
| Game entities | Classes and objects |
| Save/load | File I/O, serialization |

---

**Curriculum B: 45-Year-Old Accountant**

*Principle: Replace manual Excel tasks from lesson 1. Speak their language.*

```
Week 1: Replace your most tedious task
  - Day 1: Read an Excel file into Python (openpyxl or pandas)
  - Day 2: Filter and sort data (like Excel filters, but faster)
  - Day 3: Create summary reports (like pivot tables)
  - Day 4: Write results back to Excel
  - Project: Automate their weekly reconciliation report

Week 2: Data cleaning
  - Fix inconsistent formatting (dates, currencies, names)
  - Merge multiple spreadsheets
  - Handle missing values
  - Project: Consolidate monthly reports from 12 files into one

Week 3: Reporting automation
  - Generate charts with matplotlib
  - Create PDF reports
  - Email reports automatically
  - Project: Auto-generate and email monthly financial summary

Week 4: Advanced automation
  - Schedule scripts to run daily (Windows Task Scheduler)
  - Read data from databases (basic SQL)
  - Web scraping for market data
  - Project: Daily stock price tracker in Excel
```

**How fundamentals sneak in:**
| Accounting task | Python concept it teaches |
|----------------|--------------------------|
| Open spreadsheet | File I/O, libraries |
| Filter transactions | Conditionals, loops |
| VLOOKUP equivalent | Dictionary lookups, merge |
| Pivot table | groupby, aggregation |
| Monthly process | Functions, automation |
| Multiple files | Loops over file lists |

**The key differences:**
| Aspect | Teen gamer | Accountant |
|--------|-----------|------------|
| First visible result | Moving character on screen | Excel file read into Python |
| Motivation | "Cool!" factor | "This saves me 2 hours" |
| Error tolerance | High (will experiment) | Low (needs to trust the output) |
| Abstraction timing | Late (build first, explain later) | Early (needs to know it's correct) |
| Session length | 2-3 hours (absorbed) | 30-60 min (busy schedule) |'''
    ),
    (
        "thinking/auto-curriculum-knowledge-dependency-graph",
        r'''Build a dependency graph for learning React. What concepts MUST be understood before others, and what can be learned in parallel?''',
        r'''<think>
Let me map the dependency graph for React:

**Hard prerequisites (MUST know before React):**
- HTML/CSS (JSX is HTML-like)
- JavaScript fundamentals (variables, functions, arrays, objects)
- ES6+ (arrow functions, destructuring, spread, modules, template literals)
- npm/package management basics

**React concept dependencies:**
- JSX → (needs HTML + JS)
- Components → (needs JSX)
- Props → (needs Components)
- State (useState) → (needs Components)
- Events → (needs Components + JS event handling)
- Conditional rendering → (needs JSX + JS conditionals)
- Lists/keys → (needs JSX + array.map)
- useEffect → (needs State + understanding of side effects)
- Custom hooks → (needs useState + useEffect)
- Context → (needs Props + understanding of prop drilling problem)
- useRef → (needs understanding of DOM)
- Performance (memo, useMemo, useCallback) → (needs understanding of re-renders)
- Router → (needs Components + basic HTTP concepts)
- Data fetching → (needs useEffect + async/await + fetch/axios)
- Form handling → (needs State + Events)

**What can be learned in parallel:**
- Props and State can be introduced together (both are component data)
- Events and conditional rendering are independent
- Router and data fetching are independent
</think>

**React Learning Dependency Graph**

```
JavaScript (ES6+) ─────────────────────────────────┐
    │                                                │
    ▼                                                ▼
   JSX ──────────────────────────────────────── npm/tooling
    │
    ▼
 Components
    │
    ├──────────────┬────────────────┐
    ▼              ▼                ▼
  Props          State          Events
    │              │                │
    │              ├────────────────┤
    │              ▼                ▼
    │         useEffect      Form handling
    │              │
    ├──────────────┤
    ▼              ▼
 Context      Data fetching
    │              │
    ▼              ▼
 useReducer   Custom hooks ◄─── useRef
    │              │
    └──────┬───────┘
           ▼
    Performance optimization
    (memo, useMemo, useCallback)
           │
           ▼
    Advanced patterns
    (Suspense, Error Boundaries, Portals)
```

**Strict prerequisites (MUST know before):**
| Concept | Hard prerequisites |
|---------|-------------------|
| JSX | HTML + JavaScript |
| Components | JSX |
| Props | Components |
| State (useState) | Components |
| useEffect | State |
| Context | Props (must understand prop drilling first) |
| Custom hooks | useState + useEffect |
| Data fetching | useEffect + async/await |
| Performance | Understanding re-renders + hooks |

**Can learn in parallel (independent):**
| Group A | Group B | Group C |
|---------|---------|---------|
| Props | State | Events |
| Conditional rendering | Lists/keys | Form handling |
| Router | Data fetching | useRef |

**Recommended learning order (optimal path):**
```
Week 1: JSX → Components → Props → State
Week 2: Events → Conditional rendering → Lists/keys
Week 3: useEffect → Data fetching → Forms
Week 4: Context → Custom hooks → Router
Week 5: Performance optimization → Advanced patterns
```

**Common mistakes in React curricula:**
1. Teaching Redux before Context (skip Redux until actually needed)
2. Teaching class components (functional components + hooks are the modern standard)
3. Teaching useCallback/useMemo too early (premature optimization)
4. Not teaching JavaScript ES6+ BEFORE React (students struggle with destructuring, spread, arrow functions in JSX)'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
