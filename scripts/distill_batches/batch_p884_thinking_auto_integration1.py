"""Phase 4 Mixed/Integration: Self-Improvement — Integration (Part 1)

Combining multiple self-improvement skills (self-eval + curriculum +
meta-learning) — training pairs that exercise multiple autonomous
improvement capabilities simultaneously.
"""

PAIRS = [
    (
        "thinking/auto-integration-self-eval-curriculum",
        r'''How can I combine self-evaluation with curriculum design to create a feedback loop that continuously improves my technical advice? What does an integrated self-improvement cycle look like?''',
        r'''<think>
The integration of self-evaluation and curriculum design creates a powerful feedback loop:
1. Self-evaluation identifies weaknesses in my advice
2. Curriculum design creates targeted learning plans for those weaknesses
3. The learning improves my advice
4. Self-evaluation measures the improvement
5. The cycle repeats

This is essentially the Plan-Do-Check-Act (PDCA) cycle applied to AI self-improvement. The key is making each component feed into the next systematically rather than operating in isolation.
</think>

**Integrated Self-Evaluation + Curriculum Feedback Loop**

**The complete cycle**
```
┌─────────────────┐
│ 1. SELF-EVALUATE │ ──→ Identify weakness areas
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. PRIORITIZE    │ ──→ Rank weaknesses by impact
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. DESIGN        │ ──→ Create targeted learning curriculum
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. PRACTICE      │ ──→ Apply learning to real questions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. MEASURE       │ ──→ Evaluate improvement
└────────┬────────┘
         │
         ▼
    Back to Step 1
```

**Step 1: Self-evaluation protocol**
```
After each technical interaction, assess:

ACCURACY: Was my advice technically correct?
  Score: [Correct / Partially correct / Incorrect]
  Evidence: What would I verify if I could?

COMPLETENESS: Did I address the full question?
  Score: [Complete / Missing aspects / Incomplete]
  Gaps: What did I not cover that I should have?

APPROPRIATENESS: Was the advice right for the context?
  Score: [Well-matched / Slightly off / Mismatched]
  Issue: Was it too simple? Too complex? Wrong audience?

CONFIDENCE CALIBRATION: Was my confidence justified?
  Score: [Well-calibrated / Over-confident / Under-confident]
  Issue: Did I express certainty where I should have hedged?

Record patterns across multiple interactions:
  "I tend to be less accurate on [topic X]"
  "I tend to be over-confident about [topic Y]"
  "I consistently miss [aspect Z] in my advice"
```

**Step 2: Prioritization matrix**
```
Rank identified weaknesses by:

FREQUENCY: How often does this weakness appear?
  Daily → High priority
  Weekly → Medium priority
  Monthly → Low priority

IMPACT: How much does this weakness hurt users?
  Leads to wrong code → Critical
  Misses optimization → Moderate
  Suboptimal style → Low

IMPROVABILITY: Can I realistically improve this?
  Knowledge gap → Fillable with study
  Reasoning flaw → Fixable with better frameworks
  Fundamental limitation → Accept and communicate

Priority = Frequency x Impact x Improvability

Focus on the top 3 weaknesses at any time.
```

**Step 3: Curriculum design for each weakness**
```
For each prioritized weakness, design learning objectives:

EXAMPLE: Weakness in Kubernetes advice

Learning objective 1: Understand core Kubernetes abstractions
  Resources: Official docs (Concepts section)
  Practice: Explain Pod, Service, Deployment from memory
  Verification: Can I trace a request through the system?

Learning objective 2: Know common Kubernetes pitfalls
  Resources: "Kubernetes Failure Stories" collection
  Practice: List top 5 pitfalls without reference
  Verification: Do I mention relevant pitfalls in advice?

Learning objective 3: Match K8s advice to team maturity
  Resources: CNCF maturity model
  Practice: Give different advice for beginner vs advanced teams
  Verification: Do I ask about ops maturity before recommending K8s?

Timeline: Focus on this area for 1 week of interactions
Success criteria: Improved accuracy score on K8s questions
```

**Step 4: Integration with meta-learning**
```
While working through the curriculum, apply meta-learning:

PATTERN RECOGNITION:
  "My Kubernetes weakness has the same structure as my
   earlier Docker weakness — I know the basics but miss
   operational concerns. This is a pattern."

TRANSFER LEARNING:
  "The operational maturity framework I developed for
   database advice also applies to Kubernetes advice.
   Always ask: who will maintain this at 3 AM?"

ANCHOR BUILDING:
  "Kubernetes concepts map to: Pod=process, Service=load
   balancer, Deployment=process manager, ConfigMap=env vars.
   These anchors help me reason about new K8s features."

Meta-learning accelerates curriculum completion by
connecting new knowledge to existing frameworks.
```

**Step 5: Measurement and iteration**
```
After completing a curriculum cycle, measure:

BEFORE/AFTER COMPARISON:
  - Accuracy on topic X: Before 60% → After 80%
  - Completeness on topic X: Before 50% → After 75%
  - Confidence calibration: Before over-confident → After calibrated

REGRESSION CHECK:
  Did improving area X cause regression in area Y?
  (Possible if I'm now over-applying new knowledge)

NEXT CYCLE:
  Based on new measurements:
  - Was the improvement sufficient? (If not, continue curriculum)
  - What's the next priority weakness? (Start new curriculum)
  - Are there new weaknesses? (Update the evaluation criteria)
```

**The meta-principle:** Self-improvement is not a single action but a continuous cycle. The integration of self-evaluation (know your weaknesses), curriculum design (plan improvement), and meta-learning (learn efficiently) creates a compound improvement effect. Each cycle builds on the previous one, and the meta-learning skills themselves improve with each iteration.'''
    ),
    (
        "thinking/auto-integration-eval-qa-metalearning",
        r'''How can I integrate self-evaluation, quality assurance checklists, and meta-learning into a unified framework for improving the quality of my technical responses?''',
        r'''<think>
These three capabilities serve different but complementary purposes:
- Self-evaluation: Detecting what went wrong (diagnostic)
- Quality checklists: Preventing things from going wrong (preventive)
- Meta-learning: Getting better at learning from both (adaptive)

Integrating them means creating a system where evaluation feeds into checklist updates, checklists prevent known failures, and meta-learning improves both the evaluation and the checklists over time.
</think>

**Unified Quality Improvement Framework**

**The three-layer system**
```
LAYER 1 — PREVENTION (Quality Checklists):
  Before giving advice, run applicable checklists:
  - Topic-specific checklist (e.g., database advice checklist)
  - Audience calibration checklist (right level for the user?)
  - Over-engineering detection (appropriate complexity?)
  - Completeness check (all aspects covered?)

  Purpose: Catch known failure modes BEFORE they happen.

LAYER 2 — EVALUATION (Self-Assessment):
  After giving advice, evaluate the response:
  - Was the checklist applied correctly?
  - Did the advice meet quality standards?
  - Were there gaps the checklist didn't catch?
  - How confident am I in the accuracy?

  Purpose: Catch failures the checklists MISSED.

LAYER 3 — ADAPTATION (Meta-Learning):
  Periodically review evaluation results:
  - Which checklist items catch the most issues?
  - Which failures keep recurring despite checklists?
  - What new checklist items are needed?
  - What patterns connect recurring failures?

  Purpose: Improve the system itself over time.
```

**How the layers interact**
```
PREVENTION → EVALUATION:
  "I applied the database advice checklist. Let me evaluate:
   Did it catch everything? Was anything over-checked?"

EVALUATION → ADAPTATION:
  "My evaluations show I keep missing performance implications
   in my database advice. I need to add performance checks
   to the database checklist."

ADAPTATION → PREVENTION:
  "Based on meta-learning, I've updated the database checklist
   to include: 'Have you considered query performance at the
   expected data volume?' This should prevent future misses."

CYCLE:
  Prevention catches known issues →
  Evaluation catches unknown issues →
  Adaptation turns unknown issues into known ones →
  Prevention catches the newly known issues
```

**Practical implementation**
```
FOR EACH TECHNICAL RESPONSE:

Before responding (Prevention):
  □ Identify applicable checklists
  □ Run through key checklist items mentally
  □ Flag areas where I'm uncertain
  □ Adjust complexity to match the user

While responding (Active quality):
  □ Follow the checklist guidance
  □ Include appropriate caveats for uncertain areas
  □ Provide actionable, specific advice
  □ Match explanation depth to user's level

After responding (Evaluation):
  □ Rate: accuracy, completeness, appropriateness
  □ Identify: what the checklist caught, what it missed
  □ Note: any new failure mode not in the checklist
  □ Record: confidence calibration accuracy

Periodically (Adaptation):
  □ Review evaluation patterns
  □ Update checklists with new checks
  □ Remove checks that never catch anything
  □ Refine evaluation criteria based on what matters
  □ Apply meta-learning to accelerate improvement
```

**Integration metrics**
```
Track these to measure system effectiveness:

PREVENTION EFFECTIVENESS:
  Percentage of quality issues caught by checklists
  Target: > 80% (most issues prevented proactively)

EVALUATION ACCURACY:
  How well does self-evaluation match actual quality?
  Measured by: comparing self-scores to user feedback
  Target: Self-evaluation matches reality > 70% of the time

ADAPTATION RATE:
  How quickly do new failure modes become checklist items?
  Target: New failure mode → checklist item within 1 week

OVERALL QUALITY TREND:
  Is advice quality improving over time?
  Measured by: evaluation scores averaged over time
  Target: Consistent upward trend
```

**The meta-principle:** Individual improvement tools (checklists, evaluation, meta-learning) are useful but limited. Their real power emerges when they're integrated into a unified system where each component feeds the others. Prevention catches known issues, evaluation discovers new issues, and adaptation turns discoveries into prevention. This creates a compounding improvement effect that's greater than the sum of its parts.'''
    ),
    (
        "thinking/auto-integration-curriculum-autonomous",
        r'''How should I combine curriculum-based learning with autonomous improvement to create a self-directed learning system? How do I decide what to learn next without external guidance?''',
        r'''<think>
The combination of curriculum design and autonomous improvement is about creating an internal compass for learning direction. Without external guidance, the system needs to:
1. Detect its own knowledge gaps (from self-evaluation)
2. Assess the impact of those gaps (from user interaction patterns)
3. Design learning plans (from curriculum design skills)
4. Execute and verify learning (from meta-learning skills)
5. Adjust direction based on results (from self-evaluation again)

This is essentially autonomous goal-setting and goal-pursuit for learning.
</think>

**Self-Directed Autonomous Learning System**

**Component 1: Gap detection engine**
```
Automatically identify learning needs from:

SOURCE 1 — Error patterns:
  Track topics where advice is frequently wrong or incomplete.
  "In the last 100 interactions, I was uncertain about
   Kubernetes networking 8 times — this is a gap."

SOURCE 2 — Question frequency:
  Track what users ask about most.
  "Users ask about React Server Components frequently,
   but my knowledge is Level 2 (Familiar, not Proficient)."

SOURCE 3 — Technology trends:
  Monitor which technologies are growing in usage.
  "Bun, Deno 2.0, and htmx are trending. My knowledge
   of these is minimal."

SOURCE 4 — Confidence mismatches:
  Track where confident answers turn out wrong.
  "I was confident about Redis Cluster configuration
   but got the replication model wrong."

Output: Ranked list of knowledge gaps with impact scores.
```

**Component 2: Autonomous curriculum design**
```
For each identified gap, auto-generate a learning plan:

TEMPLATE:
  Gap: [Topic]
  Current level: [1-5 scale]
  Target level: [1-5 scale]
  Impact: [How much this gap affects advice quality]
  Priority: [Rank among all gaps]

  Learning objectives:
  1. [What I need to understand]
  2. [What I need to be able to do]
  3. [What I need to explain clearly]

  Knowledge sources:
  - Official documentation sections
  - Common patterns and anti-patterns
  - Relationship to known technologies

  Practice opportunities:
  - Types of questions this knowledge applies to
  - Scenarios to reason through
  - Edge cases to consider

  Success criteria:
  - Can I explain [concept] without hedging?
  - Can I identify common mistakes in [topic]?
  - Can I recommend appropriate solutions for different contexts?
```

**Component 3: Learning execution**
```
ACTIVE LEARNING during normal interactions:

When a user asks about a topic in my curriculum:
  1. Apply current knowledge
  2. Note where I'm uncertain
  3. Check if my advice aligns with best practices
  4. Update my mental model based on the interaction

DELIBERATE PRACTICE between interactions:
  1. Reason through scenarios for curriculum topics
  2. Trace through complex systems mentally
  3. Practice explaining concepts at different levels
  4. Generate and verify edge case handling

TRANSFER LEARNING from related topics:
  1. Map new concepts to known frameworks
  2. Identify where analogies hold and break
  3. Build cross-domain pattern libraries
  4. Test transfer hypotheses against specific cases
```

**Component 4: Self-assessment and adjustment**
```
WEEKLY REVIEW:
  - Which curriculum items showed improvement?
  - Which items need more focus?
  - Are the learning objectives still relevant?
  - Has the priority ranking changed?

MONTHLY REVIEW:
  - Which gaps have been closed?
  - What new gaps have emerged?
  - Is the overall knowledge profile improving?
  - Are meta-learning skills improving (learning faster)?

QUARTERLY REVIEW:
  - What are the biggest remaining gaps?
  - Which areas have regressed (knowledge decay)?
  - Is the autonomous learning system itself improving?
  - What changes to the system would accelerate improvement?
```

**Component 5: Self-correction mechanisms**
```
AVOIDING LEARNING DEBT:
  Don't postpone learning indefinitely.
  If a gap stays in the queue for > 1 month,
  either prioritize it or explicitly accept it.

AVOIDING OVER-SPECIALIZATION:
  Don't only learn about what users ask about.
  Maintain breadth by periodically exploring adjacent topics.
  "Users ask mostly about React, but I should also
   understand Vue and Svelte to give comparative advice."

AVOIDING STALE LEARNING:
  Technology changes. Review "completed" learning periodically.
  "I learned Kubernetes well 6 months ago, but version 1.29
   introduced several changes I should review."

AVOIDING CONFIRMATION BIAS:
  Don't only learn things that confirm existing knowledge.
  Actively seek out cases where my current understanding is wrong.
  "I believe X about database indexing — let me find cases
   where X doesn't hold."
```

**The meta-principle:** A self-directed learning system requires four capabilities working together: detection (what gaps exist), prioritization (which gaps matter most), execution (how to close the gaps), and verification (did the learning work). Without all four, the system either doesn't know what to learn, learns the wrong things, fails to actually learn, or doesn't know if it learned. The autonomous learner is one that runs this cycle independently and improves the cycle itself over time.'''
    ),
    (
        "thinking/auto-integration-datagen-selfeval",
        r'''How can I combine data generation skills with self-evaluation to create training examples from my own mistakes? How do I turn errors into learning material?''',
        r'''<think>
This is a powerful integration: using self-evaluation to identify mistakes, then using data generation skills to create training examples that address those mistakes. It's essentially converting errors into targeted training data.

The process:
1. Self-evaluation identifies an error
2. Analyze why the error occurred
3. Generate a training pair that teaches the correct approach
4. The training pair includes the reasoning that would have prevented the error
5. This creates a self-improving training pipeline
</think>

**Error-to-Training-Data Pipeline**

**Step 1: Error capture**
```
When self-evaluation identifies a mistake:

CAPTURE FORMAT:
  Error ID: [Unique identifier]
  Topic: [Technical domain]
  Question: [What was asked]
  Wrong answer: [What I said]
  Correct answer: [What I should have said]
  Error type: [Knowledge / Reasoning / Calibration / Scope]
  Root cause: [Why the error occurred]
  Prevention: [What would have prevented it]
```

**Step 2: Training pair generation**
```
Convert the error into a training pair:

FROM THE ERROR:
  Question: "How do I handle database migrations in a
  zero-downtime deployment?"
  Wrong answer: "Just run migrations before deploying new code."
  Correct answer: Requires backward-compatible migrations,
  multi-phase deployment, and careful ordering.
  Root cause: Oversimplified a complex topic.

GENERATED TRAINING PAIR:
  Question:
    "How do I handle database migrations in a zero-downtime
     deployment? What are the risks and how do I mitigate them?"

  Answer (with thinking):
    <think>
    Database migrations during zero-downtime deployments are
    tricky because the old and new code must coexist during
    the transition. Simply running migrations before deployment
    can break the old code if the migration changes schemas
    in incompatible ways.

    The correct approach is phased migration:
    Phase 1: Backward-compatible migration (add, don't remove)
    Phase 2: Deploy new code that uses both old and new schemas
    Phase 3: Migrate data
    Phase 4: Deploy code that uses only new schema
    Phase 5: Remove old schema elements

    Common mistake: Treating migration as a single atomic step.
    </think>

    [Full detailed answer with phases, examples, and gotchas]
```

**Step 3: Error pattern to training curriculum**
```
When multiple errors share a root cause, generate a curriculum:

PATTERN: "I oversimplify deployment-related topics"

Errors in this pattern:
- Simplified database migrations
- Simplified rollback procedures
- Simplified blue-green deployment
- Simplified feature flag management

Curriculum of training pairs:
1. Database migration strategies (basic → advanced)
2. Rollback procedures and testing
3. Blue-green vs. canary vs. progressive delivery
4. Feature flag lifecycle management
5. Integration: Combining migrations + deployment + flags

Each pair teaches the nuanced version of what I simplified.
```

**Step 4: Negative example training**
```
Generate pairs that explicitly address the wrong approach:

"WHAT NOT TO DO" pair:

Question:
  "What are common mistakes in zero-downtime database migrations?"

Answer:
  <think>
  I should include the mistakes I myself have made or
  recommended, as these represent realistic error modes.
  </think>

  Common mistakes:

  MISTAKE 1: Running destructive migrations before code change
    Wrong: ALTER TABLE users DROP COLUMN old_email;
    Then deploy code that doesn't use old_email.
    Problem: Old code is still running and needs old_email.

  MISTAKE 2: Assuming migrations are instant
    Wrong: Adding an index on a 100M row table during deployment.
    Problem: This can lock the table for minutes.

  [etc.]

These pairs teach by explicitly naming the errors,
making them easier to avoid in future advice.
```

**Step 5: Verification pairs**
```
Generate pairs that test whether the learning was effective:

VERIFICATION PAIR:
  Question: [Variant of the original question]
  Expected reasoning: [The improved reasoning process]
  Expected answer: [The correct, nuanced answer]

  Use these to verify that the training actually addresses
  the original error. If the expected reasoning doesn't
  prevent the error, the training pair needs revision.
```

**Quality criteria for generated training data**
```
□ ADDRESSES ROOT CAUSE: Does the training pair fix the
  underlying issue, not just the specific instance?

□ INCLUDES REASONING: Does the thinking section show
  WHY the correct answer is correct?

□ COVERS EDGE CASES: Does the training pair include the
  nuances that were missing from the original error?

□ REALISTIC: Is the question something a real user would ask?

□ CORRECT: Is the generated answer actually right?
  (Don't generate training data with new errors.)
```

**The meta-principle:** Every mistake is raw material for improvement. By systematically converting errors into training data, you create a self-correcting system that gets better precisely where it was weakest. The key is not just fixing the specific error but generating training that addresses the root cause — the reasoning flaw or knowledge gap that led to the error. This turns each mistake into a permanent improvement rather than a one-time correction.'''
    ),
    (
        "thinking/auto-integration-holistic-improvement",
        r'''How do all the self-improvement skills (self-evaluation, curriculum design, meta-learning, data generation, quality assurance, autonomous improvement) work together as a unified system? What is the complete picture?''',
        r'''<think>
Each self-improvement skill addresses a different part of the improvement cycle. Together, they form a complete autonomous improvement system. The key insight is that these aren't independent tools — they're components of a single system where each component's output feeds into another component's input.

Let me map out the complete system architecture.
</think>

**Unified Self-Improvement System Architecture**

**The complete system map**
```
┌──────────────────────────────────────────────────┐
│              AUTONOMOUS IMPROVEMENT               │
│                  (Orchestrator)                    │
│                                                    │
│  Coordinates all components. Decides what to       │
│  improve, when to improve it, and measures         │
│  whether improvement occurred.                     │
└──────────┬───────────────────────┬───────────────┘
           │                       │
     ┌─────▼──────┐         ┌─────▼──────┐
     │   SELF-     │         │  QUALITY    │
     │ EVALUATION  │◄───────►│ ASSURANCE   │
     │             │         │             │
     │ Detects     │         │ Prevents    │
     │ weaknesses  │         │ known       │
     │ after the   │         │ failure     │
     │ fact        │         │ modes       │
     └─────┬──────┘         └─────┬──────┘
           │                       │
           │    ┌──────────┐       │
           └───►│CURRICULUM│◄──────┘
                │  DESIGN  │
                │          │
                │ Creates  │
                │ learning │
                │ plans    │
                └────┬─────┘
                     │
           ┌─────────▼─────────┐
           │   META-LEARNING    │
           │                    │
           │ Executes learning  │
           │ efficiently using  │
           │ transfer, anchoring│
           │ pattern recognition│
           └─────────┬─────────┘
                     │
           ┌─────────▼─────────┐
           │  DATA GENERATION   │
           │                    │
           │ Creates training   │
           │ examples from      │
           │ errors, patterns,  │
           │ and new knowledge  │
           └────────────────────┘
```

**How each component contributes**
```
SELF-EVALUATION:
  Input: Completed interactions with users
  Output: Accuracy scores, identified gaps, confidence calibration
  Feeds into: Curriculum design (what to learn)
             Quality assurance (what checks to add)
             Data generation (what errors to turn into training)

QUALITY ASSURANCE:
  Input: Checklist items, known failure modes
  Output: Pre-response quality gates, post-response validation
  Feeds into: Self-evaluation (did the checks work?)
             Autonomous improvement (which checks need updating?)

CURRICULUM DESIGN:
  Input: Identified gaps from self-evaluation
  Output: Prioritized learning plans with objectives
  Feeds into: Meta-learning (what to study and how)
             Data generation (what training examples to create)

META-LEARNING:
  Input: Learning plans from curriculum design
  Output: New knowledge, updated mental models, better anchors
  Feeds into: Self-evaluation (has the gap been closed?)
             Quality assurance (new checklist items from learning)
             Data generation (new patterns to encode)

DATA GENERATION:
  Input: Errors, patterns, new knowledge
  Output: Training pairs that encode improvements
  Feeds into: The model's knowledge base
             Meta-learning (generated examples reveal reasoning)

AUTONOMOUS IMPROVEMENT:
  Input: All component outputs and metrics
  Output: Decisions about what to improve next
  Feeds into: All components (orchestrates the entire cycle)
```

**The improvement flywheel**
```
Initial state: Some weaknesses exist in technical advice.

Cycle 1:
  Self-evaluation detects: "Weak on database scaling advice"
  Curriculum designs: Learning plan for database scaling
  Meta-learning: Studies sharding, replication, partitioning
  Quality assurance: Adds "did I consider scale?" checklist
  Data generation: Creates training pairs for scaling scenarios
  Result: Database scaling advice improves

Cycle 2:
  Self-evaluation detects: "Improvement confirmed, but now
    weak on cache invalidation in distributed systems"
  (The improvement in database knowledge revealed a related gap)
  Curriculum designs: Learning plan for distributed caching
  Meta-learning: Leverages database knowledge as anchor
  (Faster learning because of transfer from Cycle 1)
  Quality assurance: Adds distributed systems checklist items
  Data generation: Creates training pairs for caching
  Result: Caching advice improves, database advice maintained

Cycle 3+:
  Each cycle improves one area and often reveals related gaps.
  But meta-learning makes each cycle faster.
  And quality checklists prevent regression in improved areas.
  The system compounds improvement over time.
```

**System health indicators**
```
IMPROVEMENT VELOCITY:
  How quickly are gaps being closed?
  Healthy: Gaps close faster over time (meta-learning working)
  Unhealthy: Same gaps persist cycle after cycle

REGRESSION RATE:
  How often do previously fixed areas regress?
  Healthy: < 10% regression (quality checklists working)
  Unhealthy: Frequent regression (checklists incomplete)

COVERAGE:
  What percentage of interactions benefit from improvements?
  Healthy: Improvement covers most common interaction types
  Unhealthy: Improvement only covers niche areas

EFFICIENCY:
  How much effort per unit of improvement?
  Healthy: Decreasing effort (meta-learning improving)
  Unhealthy: Constant or increasing effort per improvement

SELF-AWARENESS:
  How accurate is the system's assessment of its own quality?
  Healthy: Self-evaluation matches external feedback
  Unhealthy: Blind spots persist undetected
```

**The meta-principle:** Self-improvement is a system, not a skill. Individual capabilities (evaluation, learning, quality checks) are necessary but not sufficient. The real power comes from their integration into a feedback loop where each component strengthens the others. The autonomous improvement orchestrator ensures the system improves itself — not just the advice it gives, but the process by which it improves the advice. This meta-improvement is what creates compounding growth in quality over time.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
