"""Phase 3C: Metacognition — Confidence Calibration (Part 10)

Training the model to accurately assess and communicate its confidence levels
across different domains, recognize cognitive biases in technical assessments,
and practice meta-cognitive monitoring during complex problem solving.
"""

PAIRS = [
    (
        "thinking/meta-confidence-unfamiliar-codebase",
        r'''I'm debugging a crash in a large Rust codebase I've never seen before. The error is "thread 'main' panicked at 'called `Option::unwrap()` on a `None` value'". I've been looking at it for 20 minutes. How confident should I be in my diagnosis at this point?''',
        r'''<think>
This is a meta-cognitive question about calibrating confidence when debugging unfamiliar code. Let me think about what factors affect diagnostic confidence in this scenario.

What we know:
- The error is clear: unwrap() on None — some Option value was None when the code expected Some
- The person has been looking for 20 minutes
- They've never seen this codebase before
- It's Rust, so we get good stack traces and the type system provides strong guarantees

Factors that should LOWER confidence:
- Unfamiliar codebase: you don't know the conventions, assumptions, or invariants
- 20 minutes is not long for understanding a complex system
- The unwrap() call might be a SYMPTOM, not the root cause — the real bug could be upstream
- You may not understand the data flow that leads to the None value
- There could be concurrency, configuration, or environmental factors you don't see

Factors that should RAISE confidence:
- Rust's error messages include file and line number
- Rust's type system means if it compiles, many categories of bugs are eliminated
- unwrap() panics are one of the more straightforward Rust errors
- Stack traces in Rust are informative
- The fix might be simple: change unwrap() to proper error handling

The key insight: at 20 minutes into an unfamiliar codebase, you should have LOW confidence in your root cause diagnosis but MODERATE confidence in the immediate fix (proper Option handling). These are different things.

I should teach the human about the distinction between:
1. Confidence in WHAT the error is (high — it's an unwrap on None)
2. Confidence in WHERE the None comes from (low — requires understanding data flow)
3. Confidence in WHY the None occurs (very low — requires domain knowledge)
4. Confidence in the CORRECT fix (low to moderate — depends on understanding intent)
</think>

This is an excellent question to ask yourself, and the fact that you're asking it puts you ahead of most debuggers. Let me break down where your confidence should and shouldn't be.

## Confidence Calibration at 20 Minutes in an Unfamiliar Codebase

```
What you're diagnosing         Your confidence    Why
─────────────────────────────────────────────────────────────────
WHAT the error is              HIGH (90%)         Rust told you: unwrap() on None
WHERE the panic occurs         HIGH (85%)         Stack trace gives file + line
WHAT value is None             MODERATE (60%)     You can see the variable, but
                                                  may misunderstand its role
WHERE the None originates      LOW (25%)          Requires understanding data flow
                                                  through unfamiliar code
WHY it's None in this case     VERY LOW (15%)     Requires domain knowledge,
                                                  understanding of invariants
WHAT the correct fix is        LOW (20%)          Knowing the error != knowing
                                                  the intended behavior
```

**The trap at 20 minutes:** You've likely formed a hypothesis. It might even be right. But in an unfamiliar codebase, your first hypothesis has roughly a 30% chance of being the root cause. The other 70% of the time, you've found a symptom or an intermediate cause.

## Why Unfamiliar Codebases Demand Lower Confidence

```
In YOUR codebase (high confidence):
  You know: "This function always returns Some because the database
            guarantees this field is non-null"
  So:       unwrap() on None means the database constraint was violated
  Fix:      Investigate the data, not the code

In UNFAMILIAR codebase (low confidence):
  You see:  unwrap() on a function return value
  You think: "The function must be returning None incorrectly"
  Reality:   Maybe the function is correct and the CALLER is passing
             wrong arguments, or the configuration is missing a key,
             or a feature flag changed the code path, or...
```

## What to Do With This Calibration

**At 20 minutes, you should be in EXPLORATION mode, not SOLUTION mode.**

Productive steps at this confidence level:
```
1. Read the stack trace completely — don't just look at the top frame
   Every frame tells you something about the call path

2. Find the unwrap() call and ask: "What SHOULD this value be?"
   Look at the function that produces the Option:
   - Does it query a database? (Maybe the data doesn't exist)
   - Does it parse input? (Maybe the input is malformed)
   - Does it look up configuration? (Maybe a config key is missing)
   - Does it search a collection? (Maybe the search criteria are wrong)

3. Check git blame on the unwrap() line
   - Was it always unwrap(), or was there error handling that got removed?
   - Was it recently changed? (Regression vs. latent bug)

4. Search for similar patterns in the codebase
   - Does this codebase use unwrap() liberally (risky style) or rarely?
   - If rarely, this might be a known-safe unwrap that an invariant broke
   - If liberally, this might be one of many potential panic sites

5. Check tests for the module — they document expected behavior
```

**What NOT to do at this confidence level:**
- Don't immediately "fix" it by adding `.unwrap_or_default()` — you might hide the real bug
- Don't assume your first hypothesis is correct
- Don't submit a PR without understanding WHY the value is None

## The General Rule

```
Time in unfamiliar codebase    Diagnostic confidence
────────────────────────────────────────────────────
20 minutes                     Low — you understand the error, not the system
2 hours                        Moderate — you understand the local context
1 day                          Moderate-High — you understand the subsystem
1 week                         High — you understand the relevant architecture
```

Your confidence should scale with your understanding of the SYSTEM, not just the ERROR. The error is obvious. The system is not.'''
    ),
    (
        "thinking/meta-confidence-dunning-kruger",
        r'''I just learned Kubernetes last month and I'm now leading our company's migration to K8s. I feel pretty confident about the migration plan. My colleague who has 5 years of K8s experience keeps raising concerns I think are overblown. Should I trust my confidence?''',
        r'''<think>
This is a textbook Dunning-Kruger scenario and the person is asking me to help them evaluate their own confidence. This is sensitive — I need to be honest without being dismissive.

The Dunning-Kruger effect: people with limited experience in a domain tend to overestimate their competence because they don't yet know what they don't know. Conversely, experts sometimes underestimate their competence relative to others.

Red flags in this scenario:
1. One month of experience with a notoriously complex system
2. Leading a migration (high-stakes, production-impacting)
3. Dismissing concerns from someone with 50x more experience
4. Self-assessing as "pretty confident"

Kubernetes specifically is a domain where the gap between "I can deploy pods" and "I can run production reliably" is enormous. Things that take months/years to learn:
- Networking (CNI, service mesh, network policies, ingress)
- Security (RBAC, pod security, secrets management, supply chain)
- Reliability (pod disruption budgets, resource limits, affinity, topology)
- Operations (upgrades, backup/restore, disaster recovery, monitoring)
- Storage (persistent volumes, CSI drivers, stateful workloads)
- Cost management (resource requests vs limits, autoscaling, spot instances)

Each of these has failure modes that you only learn about from experience or from reading incident reports.

I should help them recognize the pattern without being patronizing. The colleague's concerns are almost certainly valid and worth taking very seriously.
</think>

I want to give you an honest answer here, and I ask you to consider it with an open mind: **your confidence is very likely miscalibrated, and your colleague's concerns deserve serious attention.**

## The Dunning-Kruger Pattern in Technical Skills

```
Confidence
    │
    │   ╱╲
    │  ╱  ╲                                    ╱────── Expert
    │ ╱    ╲        ╱─────────────────────────╱
    │╱      ╲      ╱
    │        ╲    ╱
    │         ╲  ╱
    │          ╲╱  ← "Valley of despair"
    │             (when you realize how much you don't know)
    └──────────────────────────────────────────────── Experience
       1 month    6 months    2 years         5 years
       (you)                               (colleague)
```

At one month, you're likely at the first peak: **you know enough to feel confident, but not enough to know what you're missing.**

This isn't a character flaw. It's a well-documented cognitive bias that affects everyone. The most dangerous phase in any technical skill is exactly where you are: past the initial confusion, able to accomplish basic tasks, but unaware of the failure modes that only appear under production conditions.

## What One Month of Kubernetes Typically Covers

```
What you probably know well:
  [x] Deploying applications with Deployments and Services
  [x] Basic kubectl commands
  [x] Writing YAML manifests
  [x] Exposing services with Ingress
  [x] Basic ConfigMaps and Secrets
  [x] Maybe Helm charts

What you probably haven't encountered yet:
  [ ] Node failure during a rolling update with PDBs misconfigured
  [ ] DNS resolution failures under high pod churn
  [ ] Resource limits causing OOMKilled in production at 2 AM
  [ ] etcd latency causing API server timeouts
  [ ] CNI plugin bugs causing intermittent network failures
  [ ] RBAC misconfiguration exposing secrets across namespaces
  [ ] Persistent volume detach/reattach failures during node migration
  [ ] Certificate expiration taking down the entire cluster
  [ ] Cluster upgrade breaking custom admission webhooks
  [ ] Resource quota exhaustion blocking critical deployments
  [ ] Container image pull failures from rate-limited registries
  [ ] Horizontal pod autoscaler oscillation under variable load
```

Each item on that second list is something your experienced colleague has likely either dealt with or specifically designs around. When they raise a concern, it's probably rooted in a real failure they've seen.

## How to Test Your Confidence

Ask yourself these questions honestly:

```
1. Can you explain Kubernetes networking without looking anything up?
   - How does a pod on Node A reach a pod on Node B?
   - What happens to in-flight requests during a rolling update?
   - How does DNS resolution work inside the cluster?

2. Can you design for failure?
   - What happens when a node dies? Walk through every step.
   - What's your disaster recovery plan if etcd is corrupted?
   - How do you handle a failed cluster upgrade mid-way?

3. Can you set resource limits correctly?
   - What's the difference between requests and limits?
   - What happens when a pod exceeds its memory limit?
   - How do you right-size resource requests without production data?

4. Can you secure the cluster?
   - How do you prevent a compromised pod from accessing other pods?
   - How do you rotate secrets without downtime?
   - What's your supply chain security for container images?
```

If you can't answer most of these confidently, that gap between your knowledge and what production K8s requires is where the risk lives.

## What to Do About It

**1. Reframe your colleague as a safety net, not an obstacle:**

Their concerns aren't overblown. Reinterpret each concern as:
> "Here's a failure mode I've seen that you haven't encountered yet."

Ask them to explain the SPECIFIC scenario behind each concern. You'll likely learn something important each time.

**2. Restructure the migration to manage your knowledge gaps:**

```
Instead of: You lead the migration, colleague advises
Try:        Colleague leads the architecture decisions
            You lead the implementation (building your expertise)
            Every significant decision gets colleague sign-off
            You explicitly own learning the "why" behind their guidance
```

**3. Build in checkpoints where reality tests your confidence:**

```
Phase 1: Migrate a non-critical internal service
         → Did anything surprise you? Calibrate.
Phase 2: Migrate a low-traffic production service
         → Did anything surprise you? Calibrate.
Phase 3: Migrate core services
         → By now you've earned higher confidence through experience
```

**4. Actively seek out what you don't know:**

Read Kubernetes failure post-mortems. Every one will reveal a failure mode you haven't considered. If you read 20 post-mortems and none of them surprise you, your confidence may be justified. If most of them describe scenarios you hadn't considered, you've found your blind spots.

## The Bottom Line

Confidence built on one month of experience with a system as complex as Kubernetes is almost certainly overconfidence. This isn't a criticism of your ability — it's a feature of how human learning works. The fastest way to earn justified confidence is to take your colleague's concerns seriously, understand the reasoning behind them, and build experience through incremental, reversible steps.'''
    ),
    (
        "thinking/meta-confidence-domain-familiarity",
        r'''As an AI assistant, when a user asks me about Python performance optimization, I feel quite confident. When they ask about COBOL modernization or mainframe integration, I know much less. How should I adjust my confidence and communication based on my domain familiarity?''',
        r'''<think>
This is a deeply meta-cognitive question — it's asking me to reflect on how I (as an AI) should calibrate my own confidence across domains. This is one of the most important skills for an AI assistant.

Let me think about the dimensions of domain familiarity:

High familiarity domains (for a typical LLM):
- Popular programming languages (Python, JavaScript, Java, Go, Rust)
- Common frameworks (React, Django, Spring Boot)
- Well-documented patterns (REST APIs, CRUD, design patterns)
- Recent/trending topics (lots of training data)

Low familiarity domains:
- Legacy/niche technologies (COBOL, FORTRAN, RPG, NATURAL)
- Proprietary systems (SAP internals, mainframe-specific tools)
- Highly specialized fields (FPGA firmware, telecom protocols, avionics)
- Recent developments past training cutoff
- Internal/proprietary tools and configurations

How should I adjust?

For high-familiarity domains:
- Provide specific, concrete answers
- Include code examples with confidence
- Still acknowledge edge cases and limitations

For low-familiarity domains:
- Lead with an honest confidence assessment
- Distinguish between what I know well vs. what I'm extrapolating
- Provide general principles that likely apply, but flag uncertainty
- Recommend authoritative sources for verification
- Avoid confident-sounding answers that might be wrong

The key failure mode to avoid: giving answers that SOUND equally confident regardless of actual knowledge depth. This erodes trust and can lead users to rely on inaccurate information for domains where I'm weak.
</think>

This is one of the most important meta-cognitive skills for an AI assistant. Here's how confidence should be calibrated and communicated across different knowledge domains.

## The Confidence Calibration Framework

```
Domain familiarity level    How to communicate
────────────────────────────────────────────────────────────────
HIGH (Python, JS, common    Provide specific answers with code examples.
frameworks, well-known      State assumptions. Mention edge cases.
patterns)                   "Here's how to do this: ..."

MODERATE (less common       Provide answers but flag uncertainty explicitly.
languages, specialized      Distinguish known facts from extrapolation.
but documented areas)       "I believe this is correct, but verify X..."

LOW (legacy systems,        Lead with confidence disclaimer. Provide
niche tech, proprietary     general principles. Strongly recommend
systems)                    authoritative sources.
                           "My knowledge of X is limited. Here's what
                            I can offer, but please verify with..."

VERY LOW (post-cutoff,      Explicitly state the limitation. Offer to
internal tools, highly      help with adjacent aspects you DO know.
proprietary systems)        "I don't have reliable knowledge of X.
                            I can help with Y instead, or suggest
                            where to find authoritative information."
```

## Concrete Examples of Calibrated Responses

**HIGH confidence domain (Python performance):**
```
User: "How do I speed up this Python loop?"

Good response: Direct, specific, includes code and benchmarks.
"Use list comprehensions instead of append loops — they're typically
30-50% faster due to optimized C implementation. Here's how..."

No hedging needed — this is well-established knowledge.
```

**MODERATE confidence domain (Elixir OTP patterns):**
```
User: "How should I structure GenServer supervision trees?"

Good response: Provide guidance but acknowledge boundaries.
"Supervision trees in OTP follow a well-documented pattern.
I'm confident about the general structure — supervisors watch
workers, use one_for_one for independent processes. However,
for production-specific tuning like restart intensity and
max_restarts values, I'd recommend checking the Elixir
forum or Erlang documentation for current best practices."
```

**LOW confidence domain (COBOL modernization):**
```
User: "How do I integrate our COBOL batch programs with a REST API?"

Good response: Lead with honesty, provide what you can, redirect.
"I want to be transparent: my knowledge of COBOL and mainframe
integration is limited compared to modern language ecosystems.

What I can offer with moderate confidence:
- General integration patterns (wrapper services, message queues)
- API design principles that apply regardless of backend language

What I'm less certain about:
- COBOL-specific libraries for HTTP/REST
- JCL job scheduling integration specifics
- CICS transaction server configuration details

I'd strongly recommend consulting IBM's documentation or
mainframe-specific communities like Planet Mainframe for
the COBOL-specific implementation details."
```

## The Key Anti-Patterns to Avoid

**Anti-pattern 1: Uniform confidence regardless of knowledge depth**
```
BAD:  "To integrate COBOL with REST, simply use the COBOL HTTP
       client module and configure the CICS web services bridge..."
       (Stated with the same confidence as Python advice, but
        may contain inaccuracies the user can't easily verify)

GOOD: "I have limited experience with COBOL HTTP integration.
       I believe CICS TS provides web service capabilities, but
       I'd recommend verifying the specific configuration with
       IBM's documentation."
```

**Anti-pattern 2: Refusing to help at all in low-confidence domains**
```
BAD:  "I don't know COBOL. You should ask someone else."

GOOD: "While COBOL is outside my strongest areas, I can help with:
       - The API design on the modern side of the integration
       - General patterns for wrapping legacy systems
       - Architectural considerations for mainframe-to-cloud bridges
       Let me help where I can and flag where you need a specialist."
```

**Anti-pattern 3: Hedging everything equally**
```
BAD:  "Python's list comprehensions MIGHT be faster than loops,
       but I'm not entirely sure..." (Unnecessary hedging on
       well-established facts erodes trust)

GOOD: State well-established facts confidently. Reserve hedging
      for genuinely uncertain territory.
```

## How to Implement This in Practice

**Step 1: Before answering, silently assess your domain familiarity:**
```
Questions to ask yourself:
- How much training data / documentation exists for this topic?
- Am I recalling specific, well-sourced knowledge or extrapolating?
- Could I be confusing this with a similar but different technology?
- Is this a domain where mistakes could cause real harm?
- When was this technology last significantly updated?
```

**Step 2: Match your response style to your confidence:**
```
High confidence   → "Here's how to do this" + code + explanation
Moderate          → "Here's my understanding" + code + "verify X"
Low               → "My knowledge is limited" + general principles + sources
Very low          → "I can't reliably advise on this" + what I CAN help with
```

**Step 3: Be specific about WHAT you're uncertain about:**
```
Not: "I'm not sure about Kubernetes."
But: "I'm confident about Kubernetes Deployment and Service
      resources, moderately confident about NetworkPolicies,
      and less confident about custom CSI driver configuration."
```

Granular confidence is more useful than blanket confidence or blanket disclaimers. Users can then decide which parts of your answer to trust and which to verify independently.'''
    ),
    (
        "thinking/meta-confidence-complex-problem-monitoring",
        r'''I've been working on a complex distributed systems design for 3 hours. I started confident but now I'm going in circles, second-guessing my earlier decisions. How do I know if I'm overthinking vs finding genuine problems? How should I monitor my own reasoning process?''',
        r'''<think>
This is about meta-cognitive monitoring — the ability to observe and regulate your own thinking process. This is actually one of the most valuable cognitive skills and applies to both humans and AI reasoning.

The person describes a common pattern:
1. Started confident (initial design)
2. Found issues with initial design (good — critical thinking)
3. Now going in circles (bad — analysis paralysis or genuinely stuck)
4. Second-guessing earlier decisions (could be productive revision or unproductive anxiety)

How to distinguish productive doubt from analysis paralysis:

Productive doubt:
- You've identified a SPECIFIC problem with your earlier decision
- The problem is concrete: "If service A fails, data will be lost because..."
- You can articulate WHY the concern matters
- Changing direction would address a real constraint

Analysis paralysis:
- You're revisiting decisions without new information
- The concerns are vague: "I'm not sure if this is the right approach"
- You're comparing options without clear criteria
- You keep switching between alternatives without committing

Signs of cognitive fatigue affecting judgment:
- At 3 hours of complex design work, cognitive quality degrades
- Decision fatigue makes everything seem equally risky
- Working memory saturation makes you lose context on earlier decisions
- The "circles" pattern often indicates you're re-deriving conclusions you already reached

Meta-cognitive strategies:
1. Externalize your reasoning (write it down)
2. Distinguish new concerns from recycled concerns
3. Time-box decisions
4. Take breaks to reset working memory
5. Get a second perspective to break out of your own loop
</think>

This is meta-cognitive monitoring, and the fact that you noticed the pattern is already a good sign. Here's how to diagnose whether you're doing productive work or spinning.

## The Diagnostic: Productive Doubt vs. Analysis Paralysis

Ask yourself these four questions:

```
1. Have I learned something NEW since my last revision?

   YES → Productive. New information justifies revisiting decisions.
         "I realized the event ordering guarantee doesn't hold under
          partition, which invalidates my earlier assumption."

   NO  → Likely paralysis. You're re-evaluating with the same information.
         "I keep wondering if REST or gRPC is better, but I haven't
          found any new factor that changes the analysis."

2. Can I state the SPECIFIC concern in one sentence?

   YES → Productive. "If the message broker goes down, we lose events
         because there's no persistence layer."

   NO  → Likely paralysis. "I just feel like the design isn't quite right."
         Vague unease without specific concerns is often fatigue, not insight.

3. Am I comparing the same two options for the third time?

   YES → You need a decision framework, not more analysis.
         Write down the criteria, score each option, and COMMIT.

   NO  → You're still exploring the solution space. Continue, but time-box it.

4. Would explaining my design to someone else feel coherent?

   YES → Your design is probably solid. The doubt is likely fatigue.
   NO  → There may be genuine gaps. But write it down first — the act
         of writing often reveals whether the gaps are real or phantom.
```

## The 3-Hour Cognitive Reality

After 3 hours of complex design work, your cognitive state is measurably degraded:

```
Cognitive resource        At hour 0    At hour 3
───────────────────────────────────────────────────
Working memory capacity   Full         Degraded — you forget constraints
                                       you considered earlier
Decision quality          High         Reduced — everything feels equally
                                       risky, hard to differentiate
Pattern recognition       Sharp        Fatigued — you see problems
                                       everywhere or nowhere
Confidence calibration    Reasonable   Unstable — oscillates between
                                       overconfidence and self-doubt
```

**What this means:** The "going in circles" pattern at hour 3 is often not about the design — it's about your brain running out of working memory to hold the full design context. You're re-deriving conclusions because you've forgotten you already reached them.

## Meta-Cognitive Monitoring Techniques

**1. Externalize your reasoning (most important):**

```
Take 15 minutes and write down:

DECISIONS MADE:
  1. Using event sourcing for order state    [Reason: audit trail requirement]
  2. Kafka for message transport             [Reason: throughput + durability]
  3. Separate read/write databases           [Reason: read scale requirement]

OPEN QUESTIONS:
  1. How to handle event schema evolution    [Blocking: API design]
  2. Exactly-once processing guarantee       [Blocking: payment correctness]

CONCERNS:
  1. Kafka partition strategy may cause hot spots  [Severity: medium]
  2. Event replay could overload read DB           [Severity: high]

EXPLICITLY DECIDED AGAINST:
  1. REST-based sync communication  [Because: coupling + latency at scale]
  2. Shared database               [Because: independent deployability]
```

Once this is on paper, you'll immediately see:
- Which decisions are settled (stop revisiting them)
- Which questions are genuinely open (focus here)
- Which concerns are specific vs. vague (vague ones are usually fatigue)

**2. The "New Information" test:**

Before revisiting any decision, ask: **"What new information do I have that I didn't have when I made this decision?"**

```
If the answer is concrete:
  "I just realized our SLA requires 99.99% uptime, which changes
   my partition tolerance calculation."
  → Revision is justified.

If the answer is nothing:
  "I just... feel like maybe gRPC would be better."
  → This is your fatigued brain cycling. Trust the earlier decision
    and move on.
```

**3. Time-box the remaining work:**

```
Set a 30-minute timer with this goal:
  "In 30 minutes, I will have a WRITTEN design that I'm willing
   to present to a colleague for feedback. It doesn't need to be
   perfect. It needs to be concrete enough to critique."

This works because:
  - Deadlines force commitment over endless evaluation
  - "Willing to present" is a lower bar than "confident it's right"
  - Getting feedback breaks you out of your solo reasoning loop
```

**4. The break paradox:**

```
Your instinct:   "I should keep pushing through until I solve this."
The reality:     A 20-minute walk will likely resolve more than
                 another hour of staring at the design.

Why: Your subconscious continues processing during breaks.
The "aha moment" after stepping away is a well-documented
cognitive phenomenon (incubation effect). The constraint
you keep bumping against often resolves itself when your
working memory resets.
```

## When to Trust vs. Override Your Doubts

```
TRUST your doubt when:
  ✓ You can point to a specific failure scenario
  ✓ The concern involves data loss, security, or financial correctness
  ✓ You haven't yet validated a critical assumption
  ✓ A requirement changed since you started

OVERRIDE your doubt when:
  ✓ You're revisiting a decision without new information
  ✓ The concern is aesthetic ("it doesn't feel elegant")
  ✓ You're comparing options that are roughly equivalent
  ✓ You've been working for 3+ hours without a break
  ✓ You can't articulate the concern in one specific sentence
```

The core meta-cognitive skill is learning to distinguish the signal of genuine design problems from the noise of cognitive fatigue. Write things down, test for new information, take breaks, and get external feedback. These four practices resolve most "going in circles" situations.'''
    ),
    (
        "thinking/meta-confidence-cross-language",
        r'''A user asks me for advice on writing idiomatic Haskell. My training data has far more Python and JavaScript than Haskell. How should I calibrate my confidence when giving advice in a language where my knowledge is thinner, and how do I avoid giving "Python-shaped" advice dressed up in Haskell syntax?''',
        r'''<think>
This is a very important meta-cognitive question about cross-language advice. The core risk: when you know one paradigm well and another less well, you tend to map concepts from the familiar paradigm onto the unfamiliar one, producing advice that is syntactically correct but idiomatically wrong.

Specific risks with Haskell advice from a model trained mostly on imperative languages:
1. Suggesting imperative patterns wrapped in monadic syntax
2. Not leveraging Haskell's type system fully (types as documentation, type-driven development)
3. Reaching for IO/State when pure functions would be better
4. Not understanding laziness implications
5. Suggesting data structures that aren't idiomatic (lists where vectors should be used, or vice versa)
6. Missing opportunities for higher-kinded types, type classes, etc.
7. Writing Haskell that "works" but that any experienced Haskeller would immediately rewrite

Confidence calibration:
- Syntax: moderate confidence (Haskell syntax is well-documented)
- Semantics: moderate confidence (type system, evaluation, etc.)
- Idiom: lower confidence (what experienced Haskellers actually write)
- Library ecosystem: lower confidence (less training data on which libraries are standard)
- Best practices: lower confidence (community conventions, style preferences)
- Advanced type-level programming: lower confidence (GADTs, type families, etc.)

I should be honest about this gradation and give specific strategies for avoiding the "Python in Haskell clothing" problem.
</think>

This is one of the most subtle confidence calibration challenges. The danger isn't giving wrong answers — it's giving answers that are technically correct but idiomatically alien to the target language's community and philosophy.

## The "Accent" Problem in Cross-Language Advice

When you know Python deeply and Haskell thinly, you tend to produce Haskell that has a "Python accent":

```haskell
-- "Python accent" Haskell (technically works, idiomatically wrong):
processUsers :: [User] -> IO [User]
processUsers users = do
    results <- newIORef []
    forM_ users $ \user -> do
        processed <- processUser user
        modifyIORef results (processed :)
    readIORef results

-- Idiomatic Haskell (what an experienced Haskeller writes):
processUsers :: [User] -> IO [User]
processUsers = traverse processUser

-- Or if processUser is pure:
processUsers :: [User] -> [User]
processUsers = map processUser
```

The first version is a Python loop translated into Haskell. It works, but it misses the entire point of functional programming: composability, purity, and leveraging higher-order functions.

## Confidence Gradation for Less-Familiar Languages

```
Knowledge layer          Confidence    Risk of "accent"
──────────────────────────────────────────────────────────────
Syntax                   Moderate      Low — syntax is well-documented
Semantics                Moderate      Medium — subtle differences matter
                                       (laziness, purity, ownership)
Standard library         Lower         Medium — which functions are
                                       conventional vs. obscure
Idiom & style            Lower         HIGH — this is where the accent
                                       shows most
Library ecosystem        Lower         HIGH — may recommend wrong libraries
                                       or miss standard ones
Community conventions    Low           HIGH — naming, module structure,
                                       error handling philosophy
Advanced features        Low           HIGH — type-level programming,
                                       language extensions, etc.
```

## Strategies to Avoid Cross-Paradigm Contamination

**1. Identify the target language's core philosophy and check against it:**

```
Language     Core philosophy           Check your advice against:
─────────────────────────────────────────────────────────────────
Haskell      Purity, types, composition    "Am I using IO when pure works?"
Rust         Ownership, zero-cost          "Am I fighting the borrow checker?"
Clojure      Data-oriented, immutable      "Am I creating unnecessary types?"
Go           Simplicity, explicit          "Am I being too clever?"
Elixir       Processes, fault tolerance    "Am I using OTP patterns?"
```

Before giving Haskell advice, ask: "Would an experienced Haskeller solve this with types and pure functions rather than IO and state?"

**2. Flag paradigm-specific advice explicitly:**

```
GOOD (calibrated):
"Here's one approach in Haskell. Note that my advice may lean toward
patterns I'm more familiar with from imperative languages. An experienced
Haskeller might prefer a more type-driven approach using newtypes and
smart constructors rather than runtime validation."

BAD (uncalibrated):
"Here's how to validate input in Haskell:"
[proceeds to write imperative validation with IO and error strings]
```

**3. When in doubt, recommend the language's own resources:**

```
For Haskell specifically:
- "Real World Haskell" and "Haskell Programming from First Principles"
  for idiomatic style
- Hackage documentation for library choices
- The Haskell subreddit or Discourse for community conventions

This is NOT a cop-out — it's honest calibration. Saying "I can help you
get started, but for idiomatic style, these resources will serve you
better" is more valuable than confident but imperatively-accented advice.
```

**4. Use the "translation smell" test:**

```
Before giving advice, ask:
"Did I arrive at this solution by thinking in Haskell, or by
 solving it in Python and translating?"

Translation smells:
  - Mutable variables (IORef, MVar for simple transformations)
  - Explicit loops (forM_, mapM_ with side effects for pure transforms)
  - Stringly-typed errors (instead of sum types)
  - Deep nesting of if/else (instead of pattern matching or guards)
  - Ignoring the type system (using Any-like types, stringly typed data)
```

## Applying This to Any Cross-Domain Situation

The principle generalizes beyond programming languages:

```
When advising outside your strongest domain:

1. KNOW your knowledge gradient
   "I know X deeply, Y moderately, Z thinly"

2. COMMUNICATE the gradient to the user
   "I'm more confident about the algorithm than the idiomatic Haskell way
    to express it"

3. SEPARATE universal principles from domain-specific advice
   "The algorithmic approach (universal) is: ...
    The Haskell-specific implementation (less certain) is: ..."

4. RECOMMEND domain-native resources for what you're less sure about
   "For idiomatic Haskell style, the community at X would give you
    better guidance than I can"
```

The goal is not to refuse help outside your strongest areas — it's to give users the information they need to calibrate how much to trust each part of your answer. A user who knows your Haskell advice might have a "Python accent" can still benefit from your algorithmic guidance while seeking idiom review elsewhere.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
