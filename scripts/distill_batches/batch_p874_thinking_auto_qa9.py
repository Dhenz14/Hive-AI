"""Phase 4F: Self-Improvement — Quality Assurance (Part 9)

Quality checklists for refactoring recommendations — ensuring refactoring
advice is safe, incremental, and justified by clear benefits.
"""

PAIRS = [
    (
        "thinking/auto-qa-refactoring-justification",
        r'''What quality checks should I apply before recommending a refactoring to ensure it's actually worth doing and not just making the code "different"?''',
        r'''<think>
Refactoring advice is risky because:
1. Refactoring has costs (time, risk of introducing bugs, code review burden)
2. "Cleaner" is subjective — one person's clean is another's over-engineered
3. Refactoring without tests can introduce bugs
4. Refactoring for its own sake wastes time that could be spent on features

**Quality dimensions:**
- Is the refactoring motivated by a real problem?
- Is the benefit clear and measurable?
- Is the cost proportional to the benefit?
- Is it safe (testable, reversible)?
- Is the timing right (not during a critical release)?
</think>

**Refactoring Recommendation Quality Checklist**

**Before recommending any refactoring:**

**Step 1: Justify the refactoring**
```
□ WHAT PROBLEM DOES THIS SOLVE?
  Valid reasons to refactor:
  ✓ Code is buggy and hard to fix because of structure
  ✓ Adding a new feature requires touching 10 files
  ✓ Multiple developers struggle to understand this code
  ✓ Performance bottleneck due to poor structure
  ✓ Duplicated logic is causing inconsistencies
  ✓ Tests are impossible to write for the current structure

  Invalid reasons (not worth the cost):
  ✗ "It could be cleaner" (subjective, no measurable benefit)
  ✗ "This isn't how I'd write it" (personal preference)
  ✗ "This pattern is outdated" (if it works, it works)
  ✗ "I read about a better pattern" (looking for problems to solve)
  ✗ "We should rewrite this in X language" (almost never worth it)

□ CAN I ARTICULATE THE BENEFIT IN ONE SENTENCE?
  "After this refactoring, adding new payment methods will
   require changes in 1 file instead of 7."

  If you can't state the benefit concretely, the refactoring
  isn't justified. "It'll be cleaner" is not concrete enough.

□ IS THE COST PROPORTIONAL?
  Refactoring cost: 3 days of work, code review, testing
  Benefit: Saves 30 minutes per feature addition
  Break-even: After 6 feature additions

  If the break-even is > 1 year away, reconsider.
```

**Step 2: Verify safety**
```
□ ARE THERE TESTS?
  Refactoring without tests is not refactoring — it's rewriting
  and hoping nothing breaks.

  If tests exist: Run them before AND after. Same results = safe.
  If tests don't exist: Write tests FIRST, then refactor.

  The #1 rule of refactoring:
  "Tests must pass before refactoring AND after refactoring.
   If you don't have tests, write them first."

□ IS IT INCREMENTAL?
  BAD: "Let's refactor the entire authentication system this sprint"
  GOOD: "Let's extract the token validation into its own module
         this sprint, then move the user lookup next sprint"

  Each increment should:
  - Be a separate commit (easy to revert)
  - Leave the codebase in a working state
  - Be deployable independently
  - Be small enough to review in 30 minutes

□ IS IT REVERSIBLE?
  If the refactoring turns out to be wrong, can it be undone?
  Renames → easily reversible
  Extract function → easily reversible
  Merge modules → harder to reverse
  Change database schema → very hard to reverse

  Higher risk = more justification needed.
```

**Step 3: Check the approach**
```
□ IS THE SIMPLEST REFACTORING SUFFICIENT?

  Refactoring complexity levels:
  1. RENAME: Rename variables/functions for clarity (lowest risk)
  2. EXTRACT: Pull code into a new function/class (low risk)
  3. MOVE: Move code to a different module/file (medium risk)
  4. RESTRUCTURE: Change the architecture (high risk)
  5. REWRITE: Replace entire components (highest risk)

  Always try the simplest level first.
  "Can we fix this with better naming?"
  → "If not, can we fix it by extracting a function?"
  → "If not, can we fix it by moving code?"
  → Only consider restructuring if simpler options fail.

□ AM I INTRODUCING UNNECESSARY ABSTRACTION?
  Common refactoring anti-pattern: Adding abstractions that
  no one needs.

  BAD refactoring:
    Before: get_user(id) → calls database directly
    After:  get_user(id) → UserRepository → UserDataSource →
            DatabaseAdapter → calls database
    (3 layers of abstraction for a simple query)

  GOOD refactoring:
    Before: 200-line function doing validation + transformation + storage
    After: validate(data), transform(data), store(data)
    (Clear separation with no unnecessary abstraction)

□ DOES IT FOLLOW ESTABLISHED PATTERNS?
  The refactoring should move toward patterns the team already
  uses, not introduce a new pattern nobody knows.

  "We're refactoring to use the repository pattern"
  → Does the team already use this pattern elsewhere?
  → If not, will the team adopt it consistently?
  → If not, you're creating inconsistency, not reducing it.
```

**Step 4: Scope control**
```
□ IS THE SCOPE BOUNDED?
  Refactoring tends to expand: "While I'm here, I'll also fix..."

  Set a clear scope BEFORE starting:
  "This refactoring touches files X, Y, Z.
   If I find issues in other files, I'll note them for later."

□ IS IT SEPARATE FROM FEATURE WORK?
  Refactoring commits should be separate from feature commits.
  A PR that adds a feature AND refactors is hard to review.

  "This PR extracts the validation logic into a module.
   Next PR will use this module to add the new validation rules."
```

**The meta-principle:** The best refactoring is motivated by a concrete problem, justified by a clear benefit, protected by tests, implemented incrementally, and scoped tightly. If you can't point to a specific pain that the refactoring solves, it's probably not worth the risk. Code that's "ugly but works and is tested" is better than code that's "elegant but introduced bugs during the rewrite."'''
    ),
    (
        "thinking/auto-qa-refactoring-code-smells",
        r'''What quality checks should I apply when identifying code smells to ensure I'm flagging real problems and not just personal style preferences?''',
        r'''<think>
Code smells are subjective by nature, which makes it easy to confuse "I don't like this" with "this is a maintainability problem." To give quality advice, I need to distinguish between smells that cause real maintenance problems and preferences that are just different styles.

**Real code smells (cause measurable problems):**
- God class/function (too many responsibilities)
- Duplicated logic (inconsistencies, bugs in one copy)
- Deep nesting (hard to follow, test, and modify)
- Long parameter lists (hard to call correctly)
- Feature envy (code that uses another class's data more than its own)

**Style preferences (not code smells):**
- Tabs vs spaces
- Single quotes vs double quotes
- Ternary vs if/else for simple conditions
- Naming conventions (camelCase vs snake_case)
- File organization preferences
</think>

**Code Smell Identification Quality Checklist**

**Before flagging a code smell:**

```
□ IS THIS A REAL SMELL OR A STYLE PREFERENCE?

  REAL SMELL test: Ask these questions:
  1. "Will this cause bugs in the future?" → Real smell
  2. "Will new team members struggle with this?" → Real smell
  3. "Does this make adding features harder?" → Real smell
  4. "Is this just not how I'd write it?" → Style preference

  If you answer "yes" to #4 and "no" to #1-3, don't flag it.
```

**Validated code smells with objective criteria:**

```
SMELL: Function too long
  Objective measure: > 50 lines (varies by language)
  BUT: A 100-line function that does one thing linearly
       is fine. A 20-line function with 5 nested conditions
       is worse.
  Real test: "Can I describe what this function does in
              one sentence?" If not → too many responsibilities.

SMELL: Too many parameters
  Objective measure: > 4-5 parameters
  BUT: Some domain functions legitimately need many params.
  Real test: "Are callers passing related params that should
              be grouped?" If yes → consider a data class/struct.

  Before flagging:
    BAD:  create_user(name, email, age, address, phone, role)
    GOOD: create_user(UserData(name, email, age, address, phone, role))
    → Only flag if grouping would actually improve the callsites.

SMELL: Deep nesting
  Objective measure: > 3-4 levels of indentation
  Real test: "Can I follow the logic without scrolling back
              to check which condition I'm inside?"
  Fix: Guard clauses, early returns, extract function.

  if user:
      if user.active:
          if user.has_permission("admin"):
              if request.valid:
                  do_thing()
  → Replace with guard clauses:
  if not user: return
  if not user.active: return
  if not user.has_permission("admin"): return
  if not request.valid: return
  do_thing()

SMELL: Duplicated logic
  Objective measure: Same logic in 2+ places
  BUT: Similar-looking code isn't always duplication.
  Real test: "If I change this logic, would I need to change
              the other copy too?" If yes → real duplication.
  Warning: Premature DRY is also a smell. If two pieces of
           code look similar but evolve independently, keeping
           them separate is correct.

SMELL: Dead code
  Objective measure: Unreachable code, unused variables/functions
  Real test: "Is this code ever executed in production?"
  Tools: Coverage reports, IDE analysis, grep for usages.
  → Always safe to remove. Dead code confuses maintainers.

SMELL: God class/module
  Objective measure: > 500 lines, many unrelated methods
  Real test: "Does this class have a single, clear responsibility?"
  If the class description requires "and" → multiple responsibilities:
    "Handles user authentication AND email sending AND logging"
    → Should be 3 separate classes.
```

**Things that are NOT code smells (despite common claims):**

| Often flagged | Actually fine when... |
|--------------|----------------------|
| Using `else` after `return` | The logic reads more clearly with the else |
| Long file names | They're descriptive and unambiguous |
| Comments explaining "why" | The why isn't obvious from the code |
| Multiple return statements | Guard clauses are cleaner than deep nesting |
| Using `print` for debugging | In development/scripts (not production) |
| Simple getter/setter | When the language requires them (Java) |

**The "so what?" test:**
```
For every code smell you identify, answer:

"So what? What bad thing will happen if we don't fix this?"

  Long function → "New developers will take 30 min to understand
                   what should take 5 min. Bug fixes will take
                   longer because of the complexity."
  → Valid concern. Flag it.

  Using single quotes instead of double → "Nothing bad will happen."
  → Not a real smell. Don't flag it.
```

**The meta-principle:** Code smells should be flagged when they cause measurable problems: bugs, slow onboarding, difficult modifications, or hard-to-write tests. Personal style preferences should be handled through linting rules and team conventions, not code review comments. If a code smell doesn't cause any concrete harm, it's not worth the cost of refactoring. Focus your smell-detection energy on things that actually make the codebase harder to work with.'''
    ),
    (
        "thinking/auto-qa-refactoring-incremental-approach",
        r'''What quality checks should I apply when planning an incremental refactoring to ensure each step is safe and the overall plan will actually reach the goal?''',
        r'''<think>
Incremental refactoring plans fail when:
1. Individual steps break the build (not truly incremental)
2. The plan loses momentum and stalls halfway (incomplete refactoring is worse than none)
3. Each step is too large to review comfortably
4. The intermediate states are worse than the original (the "worse before better" trap)
5. The plan doesn't account for concurrent development (other devs modifying the same code)

**Key principles:**
- Every step must leave the codebase deployable
- Every step should be independently revertible
- The plan should have checkpoints where stopping is acceptable
- Each step should be small enough for a single PR
</think>

**Incremental Refactoring Planning Quality Checklist**

**Before recommending an incremental refactoring plan:**

**Step 1: Validate the endpoint**
```
□ IS THE TARGET STATE CLEARLY DEFINED?
  Before refactoring, describe the end state:
  "When done, the authentication logic will be in auth/,
   with separate modules for token management, user lookup,
   and permission checking. Each module will have its own tests."

  If you can't describe the end state clearly, you'll
  wander during refactoring and potentially make things worse.

□ IS THE TARGET STATE ACTUALLY BETTER?
  "Better" means measurably improved:
  - Fewer files to change when adding features?
  - Easier to write tests?
  - Faster onboarding for new team members?
  - Fewer production bugs in this area?

  If you can't point to a specific improvement, reconsider.
```

**Step 2: Plan the steps**
```
□ DOES EACH STEP LEAVE THE CODE DEPLOYABLE?
  The golden rule: After every step, all tests pass and the
  application works in production.

  WRONG plan:
    Step 1: Delete the old UserService
    Step 2: Create the new UserService
    → Between step 1 and 2, the app is broken.

  RIGHT plan:
    Step 1: Create the new UserService alongside the old one
    Step 2: Update callers one by one to use the new service
    Step 3: Delete the old UserService (now unused)
    → The app works at every step.

□ IS EACH STEP SMALL ENOUGH FOR ONE PR?
  Target: Each PR is < 200 lines changed, reviewable in 15-30 min.

  If a step requires changing 50 files → it's too big.
  Break it down further:
    Instead of: "Update all callers to use new service"
    Try: "Update the API layer to use new service"
         "Update the background jobs to use new service"
         "Update the admin panel to use new service"

□ ARE THERE SAFE STOPPING POINTS?
  The refactoring might get interrupted (priorities change,
  people leave, crises happen). At which steps can you stop
  and have the codebase still be better than before?

  Good plan: Steps 1-3 improve things. Steps 4-6 improve more.
  If you stop after step 3, you're still better off.

  Bad plan: Steps 1-5 make things worse. Step 6 makes it better.
  If you stop after step 3, you've made things worse for nothing.
```

**Step 3: Handle the parallel branch technique**
```
□ THE STRANGLER FIG PATTERN:
  The safest large-scale refactoring approach:

  1. Create the new implementation alongside the old
  2. Route some traffic/calls to the new implementation
  3. Verify the new implementation works correctly
  4. Gradually migrate all traffic/calls
  5. Remove the old implementation

  Example:
    Old: OrderService.process_order() → giant monolithic function
    New: OrderPipeline.validate() → OrderPipeline.charge() →
         OrderPipeline.fulfill()

    Step 1: Build OrderPipeline alongside OrderService
    Step 2: For new orders, use OrderPipeline. Flag: use_new_pipeline=True
    Step 3: Monitor. Compare results. Fix bugs.
    Step 4: Enable for all orders (use_new_pipeline=True for everyone)
    Step 5: Delete OrderService.process_order()

  At any point, you can revert by setting the flag to False.

□ FEATURE FLAGS FOR SAFETY:
  Use feature flags to control which path is active:

  if feature_flag("new_auth_system"):
      return new_auth.authenticate(request)
  else:
      return old_auth.authenticate(request)

  This lets you:
  - Test in production with a subset of users
  - Instantly revert if something goes wrong
  - Run both paths and compare results (shadow mode)
```

**Step 4: Track progress**
```
□ IS THERE A TRACKING MECHANISM?
  For multi-step refactorings, track:
  - Which steps are complete
  - Which steps are in progress
  - Which steps are remaining
  - Estimated completion date

  A simple checklist in a ticket works:
  - [x] Step 1: Extract validation functions
  - [x] Step 2: Add tests for extracted functions
  - [ ] Step 3: Update callers in API layer
  - [ ] Step 4: Update callers in background jobs
  - [ ] Step 5: Remove old inline validation code

□ IS THERE AN OWNER?
  Refactorings without an owner stall.
  One person should be responsible for driving the plan
  to completion, even if others do individual steps.
```

**Step 5: Risk assessment**
```
□ WHAT'S THE WORST CASE?
  For each step, ask: "What's the worst thing that could happen?"
  - Step changes behavior subtly → tests should catch this
  - Step breaks in production → can we revert quickly?
  - Step conflicts with another developer's work → coordinate

□ IS THE TEAM AWARE?
  Refactoring the same code someone else is actively modifying
  creates merge conflicts and confusion.
  Communicate: "I'm refactoring auth/ this week. Let me know
  if you're planning changes in that area."
```

**The meta-principle:** An incremental refactoring plan should be like climbing stairs — each step takes you higher, and you can stop on any step and still be above where you started. If your plan requires completing ALL steps before any benefit is realized, it's too risky. Design the plan so that each step delivers value independently, even if the full plan is never completed.'''
    ),
    (
        "thinking/auto-qa-refactoring-when-not-to",
        r'''What quality checks help me decide when NOT to refactor? Sometimes the best advice is to leave working code alone, but how do I make that call?''',
        r'''<think>
Knowing when NOT to refactor is as important as knowing how to refactor. Many refactorings are done because a developer finds code "ugly" or "not how I'd write it," not because the code actually causes problems.

**Reasons NOT to refactor:**
1. The code works and is rarely modified (leave it alone)
2. The cost exceeds the benefit (time, risk, opportunity cost)
3. There are no tests (refactoring without tests is gambling)
4. The team has higher priorities
5. The code is about to be replaced anyway
6. The "improvement" is subjective (personal style)
7. The refactoring would require coordinating many teams/systems

**The fundamental question:** "Is the current state of this code causing actual problems, or does it just offend my aesthetic sensibilities?"
</think>

**When NOT to Refactor: Quality Decision Checklist**

**Apply these checks before recommending refactoring:**

```
□ CHECK 1: IS IT CAUSING ACTUAL PROBLEMS?

  "Is anyone struggling with this code right now?"

  If the code:
  - Works correctly in production ✓
  - Hasn't caused bugs recently ✓
  - Isn't being actively modified ✓
  - Is understood by the team ✓

  → DON'T REFACTOR. It's not broken. Fix what's broken first.

  "But it's not clean!" → Clean code that no one reads has
  zero value. Ugly code that works and is stable has high value.
```

```
□ CHECK 2: IS THE COST PROPORTIONAL TO THE BENEFIT?

  Estimate honestly:
  Cost:
    - Developer time: __ hours
    - Code review time: __ hours
    - Testing effort: __ hours
    - Risk of introducing bugs: low/medium/high
    - Opportunity cost: What ELSE could be built in this time?

  Benefit:
    - Saves __ minutes per future modification
    - How often is this code modified? __ times/year
    - Reduces bug risk by: minor/moderate/significant

  If the payback period is > 1 year, it's probably not worth it.
  If the code is modified < 2 times/year, it's rarely worth it.
```

```
□ CHECK 3: ARE THERE TESTS?

  Refactoring without tests → NO.

  Options:
  A) Write tests first, then refactor (adds to the cost)
  B) Leave the code alone (accept the current state)
  C) Refactor and manually verify (risky, not recommended)

  If writing tests first doubles the cost and pushes
  the payback period beyond 2 years → leave it alone.
```

```
□ CHECK 4: IS THE CODE ABOUT TO BE REPLACED?

  "We're rewriting this system next quarter."
  → Don't refactor code that's being replaced.

  "We're migrating to a new framework."
  → Don't refactor code in the old framework.

  "This feature is being deprecated."
  → Don't refactor deprecated code.

  Refactoring doomed code is the most wasteful use of
  engineering time.
```

```
□ CHECK 5: IS THIS A STYLE PREFERENCE?

  Different isn't wrong. Check if your recommendation is
  about a measurable improvement or a personal preference.

  "This function uses a for loop instead of a list comprehension"
  → If both are readable and correct, this is a style preference.
     Don't recommend refactoring.

  "This function has 4 levels of nesting and 3 flag variables"
  → This is a measurable readability problem.
     Refactoring is justified.
```

**The "leave it alone" scenarios:**

| Scenario | Why not refactor |
|----------|-----------------|
| Legacy code that works | Risk of breaking it exceeds benefit |
| Code modified once a year | Low modification frequency = low refactoring ROI |
| Code being replaced soon | Investment will be thrown away |
| No tests available | Refactoring without tests is reckless |
| Team has higher priorities | Opportunity cost is too high |
| "I'd write it differently" | Personal preference, not a problem |
| Third-party code/generated code | Will be overwritten on next update |

**The decision flowchart:**
```
Is this code causing bugs? → Yes → Refactor (to fix bugs)
                           → No ↓
Is this code being modified frequently? → Yes → Refactor (to reduce friction)
                                        → No ↓
Is there a specific feature that's hard to add? → Yes → Refactor (to enable feature)
                                                → No ↓
Does the team struggle to understand it? → Yes → Consider refactoring (improve docs first?)
                                         → No ↓
→ DON'T REFACTOR. Leave it alone.
```

**The "Chesterton's Fence" principle:**
```
Before removing or refactoring code, understand WHY it exists.

"This code looks unnecessary" → It might handle an edge case
you haven't seen yet. Or it might be a workaround for a
framework bug that still exists.

Before refactoring, ask:
  "Why was it written this way?"
  "What would break if I removed/changed this?"
  "Is there a comment or commit message explaining this?"

Many "ugly" code patterns exist because reality is ugly,
not because the developer was incompetent.
```

**The meta-principle:** Refactoring is not free — it costs time, carries risk, and has opportunity cost. The best engineers know when to refactor AND when to leave working code alone. Code that works, is tested, and is rarely modified is not a problem to solve, even if it's not how you'd write it today. Save your refactoring energy for code that's actively causing pain.'''
    ),
    (
        "thinking/auto-qa-refactoring-measuring-success",
        r'''How do I verify that a refactoring I recommended actually achieved its goals? What quality checks should I apply after a refactoring to ensure it was worthwhile?''',
        r'''<think>
Post-refactoring verification is often skipped, but it's crucial for closing the feedback loop. Without measuring whether the refactoring achieved its goals, you can't learn whether your refactoring recommendations are good.

**What to measure:**
1. Did the stated benefit materialize? (Faster feature additions? Fewer bugs?)
2. Did it introduce any regressions?
3. Was the effort close to the estimate?
4. Did the code actually become easier to work with?
5. Would you recommend the same refactoring again?
</think>

**Post-Refactoring Quality Verification**

**The post-refactoring checklist:**

```
□ IMMEDIATE VERIFICATION (same day):

  1. All tests pass?
     Before refactoring: X tests, Y% pass rate
     After refactoring: Same X tests, same Y% pass rate
     → Tests passing is the MINIMUM bar, not the goal.

  2. No functional changes?
     Refactoring should change structure, not behavior.
     Run the application and verify key workflows still work.

  3. No performance regression?
     If the refactoring touched hot paths:
     Before: API endpoint responds in ~50ms
     After: API endpoint responds in ~50ms (or better)
     → If it's slower, the refactoring may have introduced
        unnecessary abstraction layers.

  4. Code review approved?
     Reviewers should verify:
     - Behavior is preserved
     - New structure is actually clearer
     - No unnecessary abstraction was added
```

```
□ SHORT-TERM VERIFICATION (1-2 weeks):

  1. Were there any bugs caused by the refactoring?
     Track bug reports in the refactored area.
     Zero bugs → refactoring was safe.
     Bugs found → post-mortem: what did we miss?

  2. Is the new code easier to modify?
     The next developer who touches this code:
     Did they find it easier or harder to work with?
     Ask them directly.

  3. Were the next related PRs smaller/faster?
     If the refactoring was supposed to make changes easier:
     Before: Adding a feature in this area took 3 days
     After: Adding a feature took 1 day
     → The benefit is measurable.
```

```
□ LONG-TERM VERIFICATION (1-3 months):

  1. Did the stated benefit materialize?
     Original justification: "Adding new payment methods
     will require changes in 1 file instead of 7."
     → After 3 months, we've added 2 payment methods.
        Did it really take only 1 file change? Yes → success.

  2. Bug rate in the refactored area:
     Before refactoring: X bugs/month in this area
     After refactoring: Y bugs/month
     Y < X → refactoring improved quality
     Y > X → refactoring may have introduced complexity

  3. Would the team do this refactoring again?
     Ask: "Knowing what we know now, was this refactoring
           worth the time invested?"
     If yes → your refactoring judgment is calibrated correctly
     If no → adjust your threshold for recommending refactoring
```

**Red flags that a refactoring went wrong:**

```
- More abstraction layers but no clearer logic
  "We went from 3 files to 12 files. Each file is smaller
   but now you have to follow the call chain through 5 files
   to understand a simple operation."

- Tests had to change significantly
  Refactoring should not change tests (which test behavior,
  not implementation). If many tests broke, either the refactoring
  changed behavior (bug!) or the tests were testing implementation.

- Developers still struggle with the same problems
  "We refactored the auth system, but onboarding still takes
   a week for new devs to understand it."
  → The refactoring didn't address the real complexity.

- Performance degraded
  More function calls, more indirection, more object creation
  → measure before claiming "it doesn't matter."
```

**The refactoring feedback loop:**
```
1. RECOMMEND refactoring with stated benefit
2. EXECUTE refactoring incrementally
3. MEASURE whether the benefit materialized
4. LEARN from the measurement
5. CALIBRATE future recommendations

After 10 refactorings:
  8 achieved their goals → your judgment is good
  3 didn't achieve their goals → recalibrate

  What did the unsuccessful ones have in common?
  - Too large in scope?
  - Wrong type of refactoring?
  - Benefits overestimated?
  - Costs underestimated?

  Use this data to improve future recommendations.
```

**The meta-principle:** A refactoring is not successful just because the code looks better — it's successful when it achieves the specific benefit that justified the effort. If you said the refactoring would make adding features easier, verify that features are actually easier to add. If you said it would reduce bugs, verify that bug rates decreased. Without measurement, you're just rearranging code and hoping it helped.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
