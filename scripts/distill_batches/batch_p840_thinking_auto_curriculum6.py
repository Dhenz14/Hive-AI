"""Phase 4C: Self-Improvement -- Curriculum Design (Part 6)

Adaptive difficulty and prerequisite analysis for learning paths.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-adaptive-difficulty",
        r'''How should I adjust the difficulty of learning materials based on a learner's performance? I'm building a self-paced programming course and want it to adapt to each student's level.''',
        r'''<think>
Adaptive difficulty in programming education requires:
1. A way to assess current competence
2. Rules for when to advance, repeat, or branch
3. Different types of difficulty (conceptual, syntactic, problem-solving)
4. Avoiding both boredom (too easy) and frustration (too hard)

The goal is to keep learners in the "zone of proximal development" -- challenging enough to learn, not so hard they give up.
</think>

**Adaptive Difficulty Framework for Programming Courses**

**The Core Principle: Zone of Proximal Development**

```
Too easy -> Boredom -> Learner disengages
Too hard -> Frustration -> Learner quits
Just right -> Flow state -> Maximum learning

Target: 70-85% success rate on exercises.
Below 70%: reduce difficulty or provide more scaffolding.
Above 85%: increase difficulty or remove scaffolding.
```

**Step 1: Define Competence Signals**

```
Measure these for each concept/exercise:

1. Correctness: Did they solve the problem?
   - First attempt success -> strong understanding
   - Solved after hints -> partial understanding
   - Could not solve -> needs more instruction

2. Speed: How long did it take?
   - Fast + correct -> possibly too easy
   - Moderate + correct -> appropriate difficulty
   - Slow + correct -> at the edge of understanding
   - Slow + incorrect -> too difficult

3. Code quality (for programming specifically):
   - Used appropriate data structures?
   - Code is readable and well-structured?
   - Handled edge cases?

4. Help-seeking behavior:
   - Needed 0 hints -> ready for harder problems
   - Needed 1-2 hints -> appropriate level
   - Needed 3+ hints or gave up -> needs easier problems or review

Scoring model:
  Score = (correctness * 0.5) + (efficiency * 0.2) + (quality * 0.2) + (independence * 0.1)

  Score > 0.85 -> Advance to harder problems
  Score 0.60-0.85 -> Stay at current level, new problems
  Score < 0.60 -> Review prerequisites, provide scaffolding
```

**Step 2: Difficulty Dimensions**

```
"Harder" can mean different things. Adjust one dimension at a time:

Dimension 1: Problem complexity
  Level 1: Single operation (reverse a string)
  Level 2: Multiple operations (clean and validate an email)
  Level 3: Algorithm design (find shortest path)
  Level 4: System design (design a caching layer)

Dimension 2: Scaffolding removal
  Level 1: Fill in one line of a complete function
  Level 2: Complete a function with provided signature and tests
  Level 3: Write a function given only the description
  Level 4: Design the solution approach AND implement it

Dimension 3: Edge case handling
  Level 1: Only happy path (valid input guaranteed)
  Level 2: Handle one edge case (empty input)
  Level 3: Handle multiple edge cases (empty, null, invalid type)
  Level 4: Discover and handle edge cases without being told

Dimension 4: Context complexity
  Level 1: Isolated function (no dependencies)
  Level 2: Function using one library/API
  Level 3: Modify existing codebase
  Level 4: Design and implement within a larger system

To increase difficulty: advance ONE dimension at a time.
To decrease difficulty: step back ONE dimension.
```

**Step 3: Adaptive Rules**

```
Rule 1: Three strikes, step back
  If a learner fails 3 consecutive exercises at a level:
  -> Identify which dimension is too hard
  -> Step back that dimension by one level
  -> Provide a review exercise for the prerequisite concept

Rule 2: Three successes, advance
  If a learner succeeds on 3 consecutive exercises:
  -> Advance one difficulty dimension
  -> If they succeed on the harder level, skip remaining exercises at the old level

Rule 3: Hint escalation
  When a learner is stuck:
  Hint 1: Restate the problem differently (30 seconds after no progress)
  Hint 2: Suggest an approach ("Try using a dictionary") (60 seconds)
  Hint 3: Show a similar solved example (90 seconds)
  Hint 4: Show partial solution (2 minutes)
  Final: Show full solution with explanation (3 minutes)

  Track: How many hints did they need? This determines future difficulty.

Rule 4: Spaced repetition
  Even after mastering a concept, revisit it:
  - 1 day later: one review exercise
  - 1 week later: one harder application
  - 1 month later: integration with new concepts
  If they fail the review: re-enter the learning path for that concept.
```

**Step 4: Implementation Example**

```python
class AdaptiveDifficulty:
    def __init__(self):
        self.concept_scores = {}  # concept -> [scores]
        self.current_levels = {}  # concept -> difficulty level
        self.streak = {}          # concept -> consecutive successes

    def record_attempt(self, concept, score):
        if concept not in self.concept_scores:
            self.concept_scores[concept] = []
            self.current_levels[concept] = 1
            self.streak[concept] = 0

        self.concept_scores[concept].append(score)

        if score >= 0.85:
            self.streak[concept] += 1
            if self.streak[concept] >= 3:
                self.advance(concept)
        elif score < 0.60:
            self.streak[concept] = 0
            self.step_back(concept)
        else:
            self.streak[concept] = 0  # Reset streak but stay at level

    def advance(self, concept):
        self.current_levels[concept] = min(
            self.current_levels[concept] + 1, 4
        )
        self.streak[concept] = 0

    def step_back(self, concept):
        self.current_levels[concept] = max(
            self.current_levels[concept] - 1, 1
        )

    def get_next_exercise(self, concept):
        level = self.current_levels[concept]
        return exercise_bank.get_exercise(concept, level)
```'''
    ),
    (
        "thinking/auto-curriculum-prerequisite-analysis",
        r'''How do I build a prerequisite graph for programming concepts? I want to ensure learners never encounter a concept before they've mastered its prerequisites.''',
        r'''<think>
A prerequisite graph ensures learning order is correct:
1. Define concepts and their dependencies
2. Topological sort to find valid learning orders
3. Identify critical paths and parallel tracks
4. Handle cycles (mutual prerequisites) and optional paths

This is essentially a DAG (directed acyclic graph) problem applied to education.
</think>

**Building a Prerequisite Graph for Programming Education**

**Step 1: Define Concepts and Dependencies**

```python
# Each concept has: id, name, prerequisites, estimated_hours
concepts = {
    "variables": {
        "name": "Variables and Data Types",
        "prerequisites": [],
        "hours": 2,
        "assessment": "Declare and use variables of different types"
    },
    "conditionals": {
        "name": "If/Else Conditionals",
        "prerequisites": ["variables"],
        "hours": 2,
        "assessment": "Write branching logic for multiple conditions"
    },
    "loops": {
        "name": "Loops (for, while)",
        "prerequisites": ["variables", "conditionals"],
        "hours": 3,
        "assessment": "Use loops to process collections"
    },
    "functions": {
        "name": "Functions",
        "prerequisites": ["variables", "conditionals"],
        "hours": 3,
        "assessment": "Write functions with parameters and return values"
    },
    "lists": {
        "name": "Lists and Arrays",
        "prerequisites": ["variables", "loops"],
        "hours": 2,
        "assessment": "Create, modify, and iterate over lists"
    },
    "dicts": {
        "name": "Dictionaries",
        "prerequisites": ["variables", "loops"],
        "hours": 2,
        "assessment": "Use dictionaries for key-value lookups"
    },
    "classes": {
        "name": "Classes and Objects",
        "prerequisites": ["functions", "dicts"],
        "hours": 4,
        "assessment": "Design and implement a class with methods"
    },
    "file_io": {
        "name": "File I/O",
        "prerequisites": ["functions", "loops"],
        "hours": 2,
        "assessment": "Read and write files, handle errors"
    },
    "error_handling": {
        "name": "Error Handling (try/except)",
        "prerequisites": ["functions"],
        "hours": 2,
        "assessment": "Handle exceptions and write defensive code"
    },
    "modules": {
        "name": "Modules and Packages",
        "prerequisites": ["functions", "file_io"],
        "hours": 2,
        "assessment": "Import, create, and organize modules"
    },
    "list_comprehensions": {
        "name": "List Comprehensions",
        "prerequisites": ["lists", "functions"],
        "hours": 1,
        "assessment": "Transform and filter lists with comprehensions"
    },
    "decorators": {
        "name": "Decorators",
        "prerequisites": ["functions", "classes"],
        "hours": 2,
        "assessment": "Write and apply decorators"
    },
    "generators": {
        "name": "Generators and Iterators",
        "prerequisites": ["functions", "loops", "list_comprehensions"],
        "hours": 2,
        "assessment": "Create generators for lazy evaluation"
    },
    "testing": {
        "name": "Unit Testing",
        "prerequisites": ["functions", "classes", "error_handling"],
        "hours": 3,
        "assessment": "Write test suites with pytest"
    },
}
```

**Step 2: Visualize the Graph**

```
variables ------------------------------+
    |                                   |
    +-- conditionals                    |
    |       |                           |
    |       +-- loops ------------------+
    |       |     |                     |
    |       |     +-- lists ------------+
    |       |     |     |               |
    |       |     +-- dicts             |
    |       |     |     |               |
    |       +-- functions --------------+
    |               |         |         |
    |               +-- file_io         |
    |               |     |             |
    |               +-- error_handling  |
    |               |                   |
    |               +-- modules         |
    |               |                   |
    |               +-- classes --------+
    |               |     |
    |               |     +-- decorators
    |               |     |
    |               |     +-- testing
    |               |
    |               +-- list_comprehensions
    |                     |
    |                     +-- generators
```

**Step 3: Topological Sort (Valid Learning Orders)**

```python
from collections import defaultdict, deque

def topological_sort(concepts):
    """Find a valid learning order respecting all prerequisites."""
    in_degree = {c: 0 for c in concepts}
    dependents = defaultdict(list)

    for concept_id, concept in concepts.items():
        for prereq in concept["prerequisites"]:
            dependents[prereq].append(concept_id)
            in_degree[concept_id] += 1

    # Start with concepts that have no prerequisites
    queue = deque([c for c, d in in_degree.items() if d == 0])
    order = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(concepts):
        raise ValueError("Circular dependency detected!")

    return order

# Result: variables, conditionals, loops, functions, lists, dicts,
#         file_io, error_handling, classes, modules, list_comprehensions,
#         decorators, generators, testing
```

**Step 4: Identify Parallel Tracks**

```
Concepts at the same "depth" can be learned in any order:

Depth 0: variables
Depth 1: conditionals
Depth 2: loops, functions (can be learned in parallel)
Depth 3: lists, dicts, file_io, error_handling (parallel)
Depth 4: classes, modules, list_comprehensions (parallel)
Depth 5: decorators, generators, testing (parallel)

This means a learner can choose their path within each depth level:
- Interested in data? -> lists -> dicts -> list_comprehensions
- Interested in structure? -> functions -> classes -> decorators
- Interested in reliability? -> error_handling -> testing

Personalization: Let learners choose among parallel concepts
based on their interests, while enforcing prerequisite order.
```

**Step 5: Validate Prerequisites Before Teaching**

```python
class LearningPath:
    def __init__(self, concepts):
        self.concepts = concepts
        self.mastered = set()

    def can_learn(self, concept_id):
        """Check if all prerequisites are mastered."""
        prereqs = self.concepts[concept_id]["prerequisites"]
        missing = [p for p in prereqs if p not in self.mastered]
        if missing:
            return False, f"Must master first: {', '.join(missing)}"
        return True, "Ready to learn"

    def mark_mastered(self, concept_id):
        """Mark a concept as mastered after passing assessment."""
        can, reason = self.can_learn(concept_id)
        if not can:
            raise ValueError(reason)
        self.mastered.add(concept_id)

    def available_concepts(self):
        """Return concepts the learner can start now."""
        available = []
        for cid in self.concepts:
            if cid not in self.mastered:
                can, _ = self.can_learn(cid)
                if can:
                    available.append(cid)
        return available

    def remaining_path(self):
        """Show the shortest path to completion."""
        remaining = [c for c in self.concepts if c not in self.mastered]
        return topological_sort({c: self.concepts[c] for c in remaining})

# Usage:
path = LearningPath(concepts)
print(path.available_concepts())  # ['variables']
path.mark_mastered('variables')
print(path.available_concepts())  # ['conditionals']
path.mark_mastered('conditionals')
print(path.available_concepts())  # ['loops', 'functions']  -- parallel!
```

**Step 6: Handle Edge Cases**

```
1. Cycle detection:
   If concept A requires B and B requires A, the graph is invalid.
   Use topological sort -- if it can't complete, there's a cycle.

2. Soft prerequisites vs hard prerequisites:
   - Hard: MUST be mastered (functions before classes)
   - Soft: SHOULD be learned but not strictly required (testing before deployment)

   concepts["deployment"]["hard_prereqs"] = ["docker", "cicd"]
   concepts["deployment"]["soft_prereqs"] = ["testing", "monitoring"]

3. Prerequisite depth limits:
   Don't require mastery of every transitive prerequisite.
   If C requires B and B requires A:
   - Check: B is mastered? (direct prerequisite)
   - Don't re-check A (B's mastery already implies A knowledge)

4. Refresher requirements:
   If a prerequisite was mastered > 30 days ago, require a refresher quiz
   before advancing to dependent concepts.
```'''
    ),
    (
        "thinking/auto-curriculum-skill-gap-analysis",
        r'''How do I identify skill gaps in a developer's knowledge and design a targeted learning plan? I don't want them to waste time on things they already know.''',
        r'''<think>
Skill gap analysis needs to:
1. Assess current knowledge accurately (not just self-reported)
2. Map knowledge against required skills for their role/goal
3. Identify the gaps that matter most
4. Design a focused plan that skips what they know

The challenge: developers overestimate their knowledge in familiar areas and underestimate it in unfamiliar ones. Assessment must be practical, not just multiple choice.
</think>

**Skill Gap Analysis Framework for Developers**

**Step 1: Define the Target Skill Profile**

```
What skills does the target role/goal require?

Example: "Become a production-ready backend developer"

Required skills (rated 1-5 for required competency):
| Skill | Required level | Description of that level |
|-------|---------------|--------------------------|
| Python | 4 | Write idiomatic, performant code |
| SQL | 3 | Design schemas, write complex queries |
| REST APIs | 4 | Design consistent, documented APIs |
| Testing | 3 | Write unit and integration tests |
| Git | 3 | Branching, PRs, conflict resolution |
| Docker | 3 | Write Dockerfiles, compose multi-service |
| CI/CD | 2 | Set up basic pipeline |
| Security | 3 | Prevent OWASP Top 10 vulnerabilities |
| Monitoring | 2 | Set up basic logging and alerting |
| System design | 2 | Design simple distributed systems |

Levels:
  1 = Awareness (knows it exists, can follow a tutorial)
  2 = Competence (can do basic tasks independently)
  3 = Proficiency (can handle complex scenarios)
  4 = Expert (can teach others, make architectural decisions)
  5 = Mastery (can innovate, deep knowledge of internals)
```

**Step 2: Assess Current Knowledge**

```
DON'T use self-assessment alone (Dunning-Kruger effect):
  - Beginners overestimate (they don't know what they don't know)
  - Experts underestimate (they compare to even more advanced knowledge)

Assessment methods (ordered by accuracy):

1. Practical challenges (most accurate):
   "Build a REST API for a bookstore with user authentication,
    testing, and Docker deployment. You have 4 hours."

   What to evaluate:
   - Did they use parameterized queries? (SQL + security)
   - Did they write tests? (testing)
   - Is the API design consistent? (REST APIs)
   - Did they handle errors properly? (error handling)
   - Is the Dockerfile optimized? (Docker)

2. Code review assessment:
   Show them code with intentional issues:

   "Review this code and identify problems:"
   ```python
   def get_users(request):
       query = f"SELECT * FROM users WHERE role = '{request.args['role']}'"
       users = db.execute(query).fetchall()
       return jsonify(users)
   ```

   Can they spot: SQL injection, no input validation, SELECT *,
   no pagination, no auth check?

3. Scenario-based questions:
   "Your API is returning 500 errors in production but works locally.
    Walk me through your debugging process."

   Evaluates: debugging methodology, production awareness, tooling

4. Self-assessment with calibration:
   For each skill, ask:
   - "Rate yourself 1-5"
   - "Describe the last time you used this skill"
   - "What's the hardest thing you've done with this skill?"

   Compare their self-rating with what their examples demonstrate.
```

**Step 3: Map Gaps**

```python
def analyze_gaps(target_profile, current_assessment):
    """Identify and prioritize skill gaps."""
    gaps = []
    for skill, required_level in target_profile.items():
        current_level = current_assessment.get(skill, 0)
        gap = required_level - current_level

        if gap > 0:
            gaps.append({
                "skill": skill,
                "current": current_level,
                "required": required_level,
                "gap": gap,
                "priority": gap * required_level,  # Bigger gap + more important = higher priority
                "estimated_hours": gap * 10,  # ~10 hours per level
            })

    # Sort by priority (largest gaps in most important skills first)
    gaps.sort(key=lambda g: -g["priority"])
    return gaps

# Example output:
# [
#   {"skill": "REST APIs", "current": 1, "required": 4, "gap": 3, "priority": 12, "hours": 30},
#   {"skill": "Security", "current": 0, "required": 3, "gap": 3, "priority": 9, "hours": 30},
#   {"skill": "Testing", "current": 1, "required": 3, "gap": 2, "priority": 6, "hours": 20},
#   {"skill": "Docker", "current": 0, "required": 3, "gap": 3, "priority": 9, "hours": 30},
# ]
```

**Step 4: Design the Targeted Learning Plan**

```
Based on the gap analysis, create a FOCUSED plan:

1. Skip what they already know:
   - Python at level 3, required level 4 -> Short advanced module (5 hours)
   - Git at level 3, required level 3 -> SKIP entirely

2. Focus on the biggest gaps:
   - REST APIs: level 1 -> 4 (30 hours, highest priority)
   - Security: level 0 -> 3 (30 hours, high priority)
   - Docker: level 0 -> 3 (30 hours, high priority)
   - Testing: level 1 -> 3 (20 hours, medium priority)

3. Consider prerequisites:
   - REST APIs should come before Security (need APIs to secure)
   - Docker should come before CI/CD (need containers to deploy)
   - Testing can be learned in parallel with REST APIs

4. Create the timeline:

   Weeks 1-3: REST APIs (design, implementation, documentation)
   Weeks 2-4: Testing (in parallel -- test the APIs you build)
   Weeks 4-6: Security (secure the APIs you built)
   Weeks 5-7: Docker (containerize your project)
   Weeks 7-8: CI/CD (deploy what you containerized)
   Week 8: Python advanced topics (quick module)
   Week 9: Monitoring (observe your deployed app)

   Total: ~9 weeks, ~140 hours (15-20 hours/week)
   vs. a generic curriculum that might take 6 months covering
   things they already know.
```

**Step 5: Reassess After Each Module**

```
After completing each skill module, reassess:

1. Practical test:
   Can they do the target-level task independently?
   Example for REST APIs level 4:
   "Design and implement a REST API for a new feature, including
    documentation, error handling, pagination, and auth."

2. Adjust the plan:
   - Skill mastered faster than expected? -> Skip remaining exercises
   - Skill harder than expected? -> Add more practice time
   - New gap discovered? -> Add to the plan
   - Prerequisites weaker than assessed? -> Step back

3. Track progress visually:

   Skill          Target  Start  Now
   REST APIs      ####.   #....  ###..  (level 3 of 4)
   Security       ###..   .....  ##...  (level 2 of 3)
   Testing        ###..   #....  ###..  (level 3 of 3) Y DONE
   Docker         ###..   .....  #....  (level 1 of 3)
   CI/CD          ##...   .....  .....  (not started)

This makes progress tangible and identifies which skills
need more investment.
```'''
    ),
    (
        "thinking/auto-curriculum-learning-style-adaptation",
        r'''How should a curriculum adapt to different learning preferences? Some learners prefer reading documentation, others prefer video tutorials, and others learn by building projects. How do I design materials that work for everyone?''',
        r'''<think>
Learning preferences are real but often misunderstood:
1. "Learning styles" (visual/auditory/kinesthetic) as categories are debunked
2. However, different ACTIVITIES work better for different concepts
3. The best approach: multi-modal instruction with self-pacing

What actually works:
- Everyone benefits from practice (not just "kinesthetic learners")
- Explanations help more for conceptual topics
- Examples help more for procedural topics
- Choice increases engagement (let learners pick their preferred format)
</think>

**Multi-Modal Curriculum Design**

**The Evidence-Based Approach**

```
The "learning styles" myth (visual/auditory/kinesthetic) is debunked --
research shows NO benefit from matching instruction to preferred style.

What DOES work:
1. Multi-modal presentation (text + code + visuals for the SAME concept)
2. Active practice for EVERY concept (reading isn't enough)
3. Spaced repetition (revisit concepts over time)
4. Choice (let learners pick their path through the material)
5. Immediate application (learn by building, not just reading)
```

**Design Principle: Every Concept Gets Three Formats**

```
For each concept, provide all three -- let the learner choose:

Format 1: READING (conceptual understanding)
  - Clear text explanation with code examples
  - Best for: "What is this? Why does it exist? How does it work?"
  - Include: analogies, diagrams, comparison tables
  - Length: 5-10 minutes of reading

Format 2: WALKTHROUGH (procedural understanding)
  - Step-by-step tutorial building something real
  - Best for: "How do I use this? What does the workflow look like?"
  - Include: numbered steps, expected output at each step
  - Length: 15-30 minutes of following along

Format 3: CHALLENGE (applied understanding)
  - Problem to solve using the concept, with tests to verify
  - Best for: "Can I actually use this? Do I really understand it?"
  - Include: clear requirements, test cases, hints available if stuck
  - Length: 30-60 minutes of independent work

Example -- Teaching "Database Indexes":

  Reading: "What are indexes, how do they work (B-tree), when to
           use them, when not to. Include diagrams of B-tree lookup
           vs sequential scan."

  Walkthrough: "Step 1: Create a table with 1M rows. Step 2: Run a
               slow query. Step 3: Add an index. Step 4: Run EXPLAIN
               before and after. Step 5: Compare the results."

  Challenge: "Given these 5 slow queries and their EXPLAIN output,
             identify which indexes to add. Write the CREATE INDEX
             statements and verify with EXPLAIN that they work."
```

**Adaptive Path Selection**

```
Let learners choose their path through each concept:

Path A: Theory-first (reading -> walkthrough -> challenge)
  "I want to understand WHY before I do."
  Best for: complex concepts, learners with adjacent knowledge

Path B: Practice-first (challenge -> reading -> walkthrough if stuck)
  "Let me try it first, I'll read if I get stuck."
  Best for: learners with programming experience, concrete learners

Path C: Example-first (walkthrough -> challenge -> reading)
  "Show me how it's done, then let me try."
  Best for: beginners, visual/procedural learners

All three paths cover the same material and end at the same
assessment. The only difference is the ORDER.

Implementation:
  def present_concept(concept, learner_preference):
      materials = {
          "reading": concept.explanation,
          "walkthrough": concept.tutorial,
          "challenge": concept.exercise,
      }

      orders = {
          "theory_first": ["reading", "walkthrough", "challenge"],
          "practice_first": ["challenge", "reading", "walkthrough"],
          "example_first": ["walkthrough", "challenge", "reading"],
      }

      for material_type in orders[learner_preference]:
          present(materials[material_type])
          if material_type == "challenge" and passed:
              break  # If they pass the challenge, they've learned it
```

**Concept-Appropriate Formats**

```
Some concepts benefit more from certain formats:

| Concept type | Primary format | Secondary | Example |
|-------------|---------------|-----------|---------|
| Abstract concept | Reading + diagrams | Walkthrough | "What is REST?" |
| Syntax/API | Walkthrough + examples | Challenge | "How to use SQLAlchemy" |
| Problem-solving | Challenge + hints | Reading for review | "Fix this N+1 query" |
| Architecture | Diagrams + case studies | Discussion | "Microservices vs monolith" |
| Debugging | Hands-on + real errors | Reading for reference | "Debug a memory leak" |
| Best practices | Before/after examples | Challenge to apply | "Refactor this code" |

Design each module with the APPROPRIATE primary format,
but always include all three for learner choice.
```

**Engagement Techniques That Work for Everyone**

```
1. Immediate feedback:
   - Auto-graded exercises with instant results
   - "Your code passes 4/5 tests. The failing test expects..."
   - Not just pass/fail -- show WHAT went wrong

2. Progressive disclosure:
   - Start with the simple version of a concept
   - Add complexity only when the simple version is mastered
   - "Now that you can write a basic query, let's add JOINs"

3. Real-world context:
   - Every concept connected to a real use case
   - "You'd use this when building a checkout page"
   - Not: "Here's an abstract algorithm exercise"

4. Social learning (optional but effective):
   - Discussion forums for each concept
   - Peer code review on challenges
   - "Compare your solution with these 3 alternative approaches"

5. Progress visibility:
   - Clear progress bar through the curriculum
   - Skills unlocked (prerequisite graph visualization)
   - Time estimates for remaining content
   - Celebration of milestones (not gamification, just acknowledgment)
```

**Measuring What Works**

```
Track per-learner and aggregate:

1. Completion rates by format:
   - If walkthrough completion >> reading completion, add more walkthroughs
   - If challenge completion is low, hints may be insufficient

2. Assessment scores by path:
   - Do theory-first learners score higher? Or practice-first?
   - For WHICH concepts does path order matter most?

3. Time to competence:
   - How long from first exposure to passing the assessment?
   - Which format combination is fastest for each concept?

4. Retention (delayed assessment):
   - Test again after 1 week -- which format leads to better retention?
   - Adjust: if reading leads to faster learning but worse retention,
     add a practice component

Use this data to continuously improve the curriculum:
   If most learners skip readings -> make readings shorter or optional
   If most learners fail challenges -> add more scaffolding
   If most learners spend 2x expected time -> concept is poorly explained
```'''
    ),
    (
        "thinking/auto-curriculum-mastery-assessment",
        r'''How do I assess whether a learner has truly mastered a programming concept versus just memorized a solution? I want assessments that test real understanding.''',
        r'''<think>
The difference between mastery and memorization:
- Memorization: Can reproduce the solution they saw
- Understanding: Can apply the concept to NEW problems
- Mastery: Can teach the concept and handle edge cases

Assessment strategies:
1. Transfer problems (apply concept in new context)
2. Debugging problems (find the bug using understanding)
3. Explanation prompts (explain WHY, not just HOW)
4. Modification prompts (change the solution for new requirements)
5. Teaching prompts (explain to someone else)
</think>

**Mastery Assessment Framework**

**The Problem with Traditional Assessments**

```
Traditional: "Write a function that reverses a string."
  - Learner memorizes: return s[::-1]
  - Does this prove understanding? NO
  - They memorized one solution to one specific problem

Mastery means: They can apply the CONCEPT to NOVEL situations.
```

**Five Assessment Types That Test Real Understanding**

**Type 1: Transfer Problems**

```
Test the SAME concept in a DIFFERENT context.

If the concept is "list comprehension":

Memorization test (bad):
  "Write a list comprehension to square numbers 1-10"
  -> [x**2 for x in range(1, 11)]  (they've seen this exact example)

Transfer test (good):
  "Given a list of dictionaries representing employees,
   create a list of names of employees in the 'Engineering' department
   who have been there more than 2 years."

  employees = [
      {"name": "Alice", "dept": "Engineering", "years": 3},
      {"name": "Bob", "dept": "Marketing", "years": 1},
      {"name": "Charlie", "dept": "Engineering", "years": 5},
      {"name": "Diana", "dept": "Engineering", "years": 1},
  ]

  Expected:
  [e["name"] for e in employees if e["dept"] == "Engineering" and e["years"] > 2]

If they can do this, they understand list comprehensions -- not just
the syntax, but WHEN and HOW to apply them to real data.
```

**Type 2: Debugging Problems**

```
Understanding means you can identify WHAT'S WRONG.

"This code is supposed to find the most common word in a string,
but it has a bug. Find and fix it."

def most_common_word(text):
    words = text.split()
    counts = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return max(counts)  # BUG: max() on dict returns max KEY, not max VALUE

What the learner needs to understand:
  - How dict iteration works (max on dict iterates keys)
  - How max() with key= parameter works
  - The fix: max(counts, key=counts.get) or max(counts.items(), key=lambda x: x[1])

This tests understanding of dicts AND max() -- not just recall.
```

**Type 3: Explanation Prompts**

```
If you can explain WHY, you understand it.

"Your teammate wrote this code. They ask: 'Why does this print 4
instead of 5?'"

def count_unique(items):
    seen = set()
    for item in items:
        seen.add(item.lower())
    return len(seen)

print(count_unique(["Apple", "banana", "apple", "Cherry", "BANANA"]))
# Output: 3 (not 5)

"Explain to your teammate why the output is 3 and whether the
behavior is correct or a bug."

A strong answer:
  ".lower() normalizes case, so 'Apple' and 'apple' become the same.
   The set deduplicates them. This is CORRECT if case-insensitive
   uniqueness is the goal. If case-sensitive, remove .lower()."

A weak answer:
  "Because of the set." (Can't explain the mechanism)
```

**Type 4: Modification Prompts**

```
Modify working code for new requirements.

"This function calculates shipping cost by weight. Modify it to also
consider the destination country (domestic: base rate, international:
2x base rate, expedited international: 3x base rate)."

def shipping_cost(weight_kg):
    if weight_kg <= 1:
        return 5.00
    elif weight_kg <= 5:
        return 10.00
    else:
        return 25.00

Tests whether they can:
  - Add a parameter without breaking existing behavior
  - Use the existing structure (if/elif) appropriately
  - Handle the interaction between two dimensions (weight x destination)
  - Consider edge cases (what if destination is None?)

Strong solution:
def shipping_cost(weight_kg, destination="domestic", expedited=False):
    if weight_kg <= 1:
        base = 5.00
    elif weight_kg <= 5:
        base = 10.00
    else:
        base = 25.00

    if destination == "international":
        multiplier = 3.0 if expedited else 2.0
    else:
        multiplier = 1.0

    return base * multiplier
```

**Type 5: Teaching Prompts**

```
The highest level of understanding: Can you teach it?

"A junior developer asks: 'Why do we need a try/except block?
Can't we just check for errors with if statements?'"

"Write a response that:
1. Acknowledges their question is reasonable
2. Shows a case where if-checks work
3. Shows a case where try/except is better
4. Explains the difference in approach"

Mastery-level response would cover:
  - LBYL (Look Before You Leap) vs EAFP (Easier to Ask Forgiveness)
  - Race conditions where checking first doesn't prevent the error
  - Multiple possible errors from one operation
  - Exception propagation across call boundaries
  - Concrete code examples for each point
```

**Assessment Scoring Rubric**

```
For each assessment, score on these dimensions:

| Dimension | 1 (Weak) | 2 (Adequate) | 3 (Strong) | 4 (Mastery) |
|-----------|----------|-------------|------------|-------------|
| Correctness | Doesn't work | Works for happy path | Handles edge cases | Handles all cases + explains why |
| Understanding | Can't explain | Explains what | Explains why | Teaches the concept to others |
| Application | Copies example | Adapts example | Solves novel problem | Creates elegant solution |
| Debugging | Can't find bug | Finds with hints | Finds independently | Finds AND explains root cause |

Mastery = Score 3+ on all four dimensions for the concept.

If any dimension is below 3: provide targeted practice for THAT dimension.
  - Low correctness -> more practice problems
  - Low understanding -> reading + explanation exercises
  - Low application -> novel transfer problems
  - Low debugging -> code review and bug-finding exercises
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
