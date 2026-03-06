"""Phase 4C: Self-Improvement — Curriculum Design (Part 1)

The model learns to design learning curricula — ordering topics, identifying prerequisites,
and building progressive skill ladders.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-design-web-dev",
        r'''Design a learning curriculum for someone who wants to become a full-stack web developer. They know basic HTML/CSS but no JavaScript or backend programming. What should they learn, in what order, and why?''',
        r'''<think>
To design an effective curriculum, I need to consider:

1. **Prerequisites**: What does the learner already know? (HTML/CSS)
2. **End goal**: Full-stack web development
3. **Dependency graph**: What concepts depend on what?
4. **Motivation curve**: Keep early wins to maintain momentum
5. **Practice-to-theory ratio**: Favor building things over reading docs

Key dependencies:
- JavaScript → DOM manipulation → async/await → APIs → Node.js → Express → full-stack
- Can't learn React before JavaScript fundamentals
- Can't learn databases before understanding data modeling
- Can't learn authentication before understanding HTTP and sessions

I should structure this as phases where each phase builds on the previous, with a concrete project at the end of each phase.
</think>

**Full-Stack Web Developer Curriculum**

**Phase 1: JavaScript Fundamentals (2-3 weeks)**
Prerequisites: HTML/CSS (already known)
```
Week 1: Variables, functions, arrays, objects, loops
Week 2: DOM manipulation, event handling, forms
Week 3: Async basics (callbacks, promises, async/await)
Project: Interactive todo list (vanilla JS, no frameworks)
```
**Why this order:** JS fundamentals must come before anything else. The todo list project provides immediate gratification — they can see and interact with their creation.

**Phase 2: Modern JavaScript + Git (2 weeks)**
Prerequisites: Phase 1
```
Week 4: ES6+ (arrow functions, destructuring, modules, template literals)
Week 5: Git basics, npm, basic tooling (ESLint, Prettier)
Project: Weather app that fetches data from a public API
```
**Why:** API fetching is the bridge to backend development. Git is needed before any serious project work.

**Phase 3: Backend Basics (3 weeks)**
Prerequisites: Phase 2
```
Week 6: Node.js basics, HTTP protocol, Express.js
Week 7: REST API design, routing, middleware
Week 8: Databases (PostgreSQL), SQL basics, ORMs
Project: REST API for a bookstore (CRUD operations)
```
**Why:** Building an API first (without frontend) forces focus on data modeling and HTTP concepts.

**Phase 4: React (3 weeks)**
Prerequisites: Phase 2 (JS fundamentals + ES6)
```
Week 9: Components, props, JSX, state (useState)
Week 10: Effects (useEffect), routing, forms
Week 11: State management, API integration
Project: Frontend for the bookstore API from Phase 3
```
**Why this is Phase 4, not Phase 2:** Learning React before understanding JavaScript leads to cargo-culting. The learner needs to know what React is abstracting over.

**Phase 5: Full-Stack Integration (2 weeks)**
Prerequisites: Phases 3 + 4
```
Week 12: Authentication (JWT, sessions), password hashing
Week 13: Deployment (Docker basics, cloud hosting)
Project: Full-stack blog with user accounts, deployed live
```

**Curriculum design principles applied:**
- Each phase has ONE new major concept (JS, backend, frontend framework, integration)
- Each phase ends with a working project (motivation)
- Dependencies are respected (no React before JS, no auth before HTTP)
- Total: ~13 weeks to employable full-stack skills'''
    ),
    (
        "thinking/auto-curriculum-design-python-data",
        r'''Design a learning path for a data analyst who knows Excel and basic SQL. They want to learn Python for data analysis and eventually machine learning. What's the optimal order?''',
        r'''<think>
Let me map the dependency graph for this learner:

**What they know:** Excel (formulas, pivot tables), basic SQL (SELECT, WHERE, JOIN)
**Goal:** Python for data analysis → machine learning

**Key insight:** Their SQL knowledge is an asset. Pandas operations map closely to SQL concepts (filter = WHERE, groupby = GROUP BY, merge = JOIN). I should leverage this.

**Dependency chain:**
Python basics → pandas → visualization → statistics → scikit-learn → deep learning

**Pitfall to avoid:** Don't start with Python fundamentals aimed at software engineers (OOP, design patterns). Start with Python for DATA (DataFrames, plotting) — it's more relevant and motivating for this learner.

**Motivation consideration:** This person analyzes data in Excel daily. If I can show them doing their Excel work faster in Python within week 1, they'll stay motivated.
</think>

**Python for Data Analysis → ML Learning Path**

**Phase 1: Python Basics Through Data (2 weeks)**
*Leverage their Excel/SQL knowledge*
```
Week 1: Python syntax via data tasks
  - Variables, lists, dicts (like Excel cells and tables)
  - Loops and conditionals (like Excel IF formulas)
  - Functions (like Excel custom formulas)
  - File reading (replace manual CSV opens)

Week 2: pandas fundamentals
  - DataFrame = spreadsheet/SQL table
  - df.query() = SQL WHERE
  - df.groupby() = SQL GROUP BY / Excel pivot tables
  - df.merge() = SQL JOIN
  - df.to_excel() = instant Excel export

Project: Replicate their most common Excel task in Python
```
**Why:** Starting with pandas immediately makes Python relevant to their daily work. The SQL analogy accelerates learning.

**Phase 2: Data Visualization + EDA (2 weeks)**
```
Week 3: matplotlib + seaborn
  - Histograms, scatter plots, bar charts
  - Customizing plots
  - Subplots and layouts

Week 4: Exploratory Data Analysis workflow
  - .describe(), .info(), .value_counts()
  - Handling missing data
  - Data cleaning patterns

Project: Full EDA report on a real dataset (Kaggle)
```

**Phase 3: Statistics Foundations (2 weeks)**
```
Week 5: Descriptive stats + distributions
  - Mean, median, std (already know from Excel)
  - Normal distribution, hypothesis testing
  - Correlation vs causation

Week 6: Statistical testing in Python
  - scipy.stats: t-tests, chi-squared
  - A/B testing framework
  - Confidence intervals

Project: A/B test analysis with statistical significance
```

**Phase 4: Machine Learning Fundamentals (3 weeks)**
```
Week 7: scikit-learn basics
  - Train/test split, cross-validation
  - Linear regression (extension of their Excel trendlines)
  - Evaluation metrics (RMSE, R², accuracy)

Week 8: Classification
  - Logistic regression, decision trees, random forest
  - Feature engineering
  - Handling imbalanced data

Week 9: Model selection and tuning
  - Grid search, hyperparameter tuning
  - Feature importance
  - Model comparison

Project: Predict customer churn with scikit-learn
```

**Phase 5: Advanced Topics (choose path)**
```
Path A (Deep Learning): PyTorch basics, neural networks
Path B (NLP): Text processing, sentiment analysis
Path C (Production): MLOps, model deployment, APIs
```

**Key curriculum design decisions:**
1. **Leveraged existing knowledge** — SQL/Excel analogies accelerate pandas learning
2. **Delayed pure Python fundamentals** — OOP, decorators, etc. can come later
3. **Statistics before ML** — understanding distributions prevents black-box ML
4. **Real datasets from Phase 1** — motivation through relevance'''
    ),
    (
        "thinking/auto-curriculum-design-identify-gaps",
        r'''A junior developer can write basic CRUD APIs but their code breaks in production. They don't understand why things work locally but fail at scale. What skills are they missing, and how should they learn them?''',
        r'''<think>
Let me diagnose the skill gaps:

**Symptom:** "Works locally, breaks in production"
**Root causes (skill gaps):**

1. **Concurrency understanding** — Locally they have one user. Production has hundreds. Race conditions, connection pool exhaustion, thread safety.

2. **Error handling** — Locally errors are visible in terminal. Production errors need logging, monitoring, graceful degradation.

3. **Resource management** — Locally resources are abundant. Production has memory limits, connection limits, disk limits.

4. **Database under load** — Locally queries are instant on empty tables. Production has millions of rows, N+1 queries matter.

5. **Network reliability** — Locally everything is on the same machine. Production has network partitions, timeouts, retries.

6. **Configuration management** — Locally hardcoded values work. Production needs environment variables, secrets management.

7. **Observability** — Locally they can add print statements. Production needs structured logging, metrics, tracing.

**Priority ordering:** The most impactful gaps to fill first are the ones that cause the most production incidents. Based on common patterns:
1. Database performance (N+1, missing indexes) — most common
2. Error handling (unhandled exceptions → 500s) — most visible
3. Configuration (hardcoded values → wrong in production) — most embarrassing
4. Concurrency (race conditions) — hardest to debug
5. Observability (can't debug what you can't see)
</think>

**Skill gap analysis: "Local works, production breaks"**

| Gap | Impact | Priority |
|-----|--------|----------|
| Database performance | High | Learn first |
| Error handling | High | Learn second |
| Configuration management | Medium | Learn third |
| Concurrency | High (hard to debug) | Learn fourth |
| Observability | High (enables fixing everything else) | Learn throughout |

**Curriculum for closing these gaps:**

**Module 1: Database Performance (1 week)**
*Most production issues are slow queries*
```
Day 1: EXPLAIN ANALYZE — read query plans
Day 2: N+1 queries — identify and fix with eager loading
Day 3: Indexing — when to add, how to choose columns
Day 4: Connection pooling — why 100 concurrent users exhaust connections
Day 5: Practice: Take their actual app, profile queries, fix the slow ones
```

**Module 2: Error Handling Patterns (1 week)**
*Stop returning 500 errors*
```
Day 1: Exception hierarchy — catch specific, not bare except
Day 2: Structured logging — logger.exception(), not print()
Day 3: Graceful degradation — fallback behavior when dependencies fail
Day 4: Error monitoring — Sentry or similar
Day 5: Practice: Add error handling to their existing API endpoints
```

**Module 3: Production Configuration (3 days)**
```
Day 1: Environment variables — no hardcoded secrets
Day 2: Config validation at startup — crash early, not at 3am
Day 3: Feature flags — deploy without releasing
```

**Module 4: Concurrency (1 week)**
```
Day 1: Race conditions — check-then-act is broken
Day 2: Database transactions — SELECT FOR UPDATE
Day 3: Idempotency — safe retries
Day 4: Connection pools and timeouts
Day 5: Practice: Find race conditions in their code
```

**Module 5: Observability (ongoing)**
```
- Structured logging from day 1
- Request tracing (correlation IDs)
- Metrics (response time, error rate)
- Alerting on symptoms, not causes
```

**Teaching approach:** Each module should use THEIR actual production code, not toy examples. The most effective learning happens when they find and fix bugs in code they wrote.'''
    ),
    (
        "thinking/auto-curriculum-design-prerequisite-chain",
        r'''I'm designing a course on distributed systems. What's the correct prerequisite chain? Students often jump into Kubernetes and microservices without foundations. What should they learn first?''',
        r'''<think>
Let me build the prerequisite dependency graph for distributed systems:

**The problem:** Students want to learn Kubernetes because it's on job postings. But Kubernetes is an orchestration layer that assumes you understand what it's orchestrating.

**Prerequisite chain (bottom-up):**

Level 0 (Foundations): Networking basics → operating systems basics
Level 1 (Single machine): Processes, threads, file systems, IPC
Level 2 (Communication): TCP/IP, HTTP, DNS, load balancing
Level 3 (Data): Databases, transactions, replication, consistency
Level 4 (Distribution): CAP theorem, consensus, distributed state
Level 5 (Patterns): Service discovery, circuit breakers, sagas
Level 6 (Infrastructure): Containers, orchestration, service mesh
Level 7 (Operations): Monitoring, tracing, incident response

**Critical mistake students make:** Jumping from Level 0 to Level 6. They can kubectl apply -f deployment.yaml but don't understand why a pod is crash-looping because they don't understand health checks, resource limits, or networking.

**Each level should be grounded in "why":**
- Why containers? → Because "works on my machine" but not in production
- Why orchestration? → Because managing 50 containers manually doesn't scale
- Why service mesh? → Because microservice-to-microservice communication needs reliability
</think>

**Distributed Systems Prerequisite Chain**

```
Level 0: Foundations (assumed)
    ├── Operating systems (processes, memory, file systems)
    └── Networking (TCP/IP, DNS, HTTP)
         │
Level 1: Single-Machine Scalability
    ├── Concurrency (threads, locks, async I/O)
    ├── Databases (indexes, transactions, connection pools)
    └── Caching (in-memory, Redis, CDN)
         │
Level 2: Multi-Machine Communication
    ├── Client-server architecture
    ├── Load balancing (round-robin, least connections)
    ├── Reverse proxies (Nginx, HAProxy)
    └── Serialization (JSON, Protocol Buffers)
         │
Level 3: Data Distribution
    ├── Replication (leader-follower, multi-leader)
    ├── Consistency models (strong, eventual, causal)
    ├── CAP theorem (and why it's often misunderstood)
    └── Partitioning / sharding
         │
Level 4: Distributed Patterns
    ├── Consensus (Raft, Paxos — at a high level)
    ├── Distributed transactions (2PC, sagas)
    ├── Event-driven architecture (queues, pub/sub)
    └── Idempotency and exactly-once delivery
         │
Level 5: Microservices (NOW you're ready)
    ├── Service decomposition (when to split)
    ├── Service discovery
    ├── Circuit breakers, retries, timeouts
    └── API gateways
         │
Level 6: Infrastructure (NOW Kubernetes makes sense)
    ├── Containers (Docker — what and why)
    ├── Orchestration (Kubernetes — what and why)
    ├── Service mesh (Istio/Linkerd — what and why)
    └── Infrastructure as Code (Terraform)
         │
Level 7: Operations
    ├── Distributed tracing (Jaeger, Zipkin)
    ├── Centralized logging (ELK stack)
    ├── Metrics and alerting (Prometheus, Grafana)
    └── Chaos engineering (deliberate failure testing)
```

**Why this order matters:**

Students who skip to Kubernetes without Level 1-4:
- Can't debug network issues (don't understand TCP)
- Can't debug data inconsistency (don't understand replication)
- Can't design services (don't understand consistency tradeoffs)
- Can deploy YAML but can't reason about system behavior

**Each level's key question:**
| Level | Question it answers |
|-------|-------------------|
| 1 | How far can a single machine go? |
| 2 | How do machines talk to each other? |
| 3 | How is data shared across machines? |
| 4 | How do machines agree on things? |
| 5 | How do you split a system into parts? |
| 6 | How do you run and manage the parts? |
| 7 | How do you know if it's working? |'''
    ),
    (
        "thinking/auto-curriculum-design-spaced-repetition",
        r'''How should I structure a programming course to maximize retention? I've noticed students forget concepts they learned weeks ago.''',
        r'''<think>
This is about learning science applied to programming education. Key principles:

1. **Spaced repetition** — Review concepts at increasing intervals
2. **Interleaving** — Mix different concept types in practice, don't block
3. **Retrieval practice** — Recall is more effective than re-reading
4. **Elaboration** — Connecting new concepts to existing knowledge
5. **Concrete examples before abstractions** — Show first, explain later

The problem with typical programming courses:
- Week 1: Variables → never revisited
- Week 2: Loops → never revisited
- Week 3: Functions → never revisited
- Week 8: Students have forgotten variables

The fix: Build each week's exercises to REQUIRE using concepts from previous weeks.
</think>

**Retention-Optimized Course Structure**

**Problem:** Traditional courses teach concepts once and move on. Students forget ~80% within 2 weeks (Ebbinghaus forgetting curve).

**Solution: Build cumulative projects that force spaced retrieval.**

**Principle 1: Spiral curriculum (revisit concepts at increasing depth)**
```
Week 1: Variables and types → simple calculator
Week 3: Variables again → but now with type conversion edge cases
Week 6: Variables again → but now with mutability and references
Week 10: Variables again → but now with memory management considerations
```

**Principle 2: Cumulative projects (each project uses ALL previous concepts)**
```
Week 1 project: Calculator (variables, operators)
Week 2 project: Todo list (+ loops, conditionals)
Week 3 project: Contact book (+ functions, data structures)
Week 4 project: Expense tracker (+ file I/O, ALL previous concepts)
Week 5 project: API client (+ HTTP, ALL previous concepts)
```

Each project is new but REQUIRES the student to USE concepts from every previous week. This creates natural spaced repetition.

**Principle 3: Interleaved practice (mix concept types)**
```
# Bad (blocked practice):
Exercise 1-10: All about loops
Exercise 11-20: All about functions
Exercise 21-30: All about classes

# Good (interleaved practice):
Exercise 1: Write a loop
Exercise 2: Write a function
Exercise 3: Write a loop that calls a function
Exercise 4: Write a class with a method that uses a loop
Exercise 5: Debug a function with a loop error
```

**Principle 4: Retrieval practice over re-reading**
```
# Bad: "Review chapter 3 on functions"
# Good: "Without looking at notes, write a function that..."

Weekly quizzes:
- Write code from memory (not multiple choice)
- Debug code without documentation
- Explain a concept in your own words
- Predict what code will output before running it
```

**Principle 5: Connect new concepts to known ones**
```
# When teaching recursion:
"Remember how a loop repeats a block? Recursion is when a function
repeats by calling itself. Think of it as a loop where the 'counter'
is the function call stack."

# When teaching async/await:
"Remember how we used threading for concurrent I/O? async/await gives
you the same concurrency but in a single thread, using an event loop
instead of OS threads."
```

**Concrete course calendar example:**
| Week | New concept | Revisited concepts | Project |
|------|------------|-------------------|---------|
| 1 | Variables, types | — | Calculator |
| 2 | Loops, conditionals | Variables | Number guessing game |
| 3 | Functions | Variables, loops | Todo CLI |
| 4 | Data structures | Functions, loops | Contact book |
| 5 | File I/O | All above | Expense tracker |
| 6 | Error handling | Functions, file I/O | Robust file processor |
| 7 | OOP basics | All above | Bank account system |
| 8 | APIs/HTTP | OOP, errors, data structures | API client |

**The key insight:** Students don't forget because they're bad at learning. They forget because courses don't create enough opportunities for spaced retrieval. Design the curriculum so that using old concepts is REQUIRED, not optional.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
