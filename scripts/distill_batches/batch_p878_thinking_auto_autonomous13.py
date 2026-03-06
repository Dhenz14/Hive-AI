"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 13)

Autonomously improving documentation quality — strategies for
detecting when documentation advice is incomplete, misleading,
or poorly structured, and self-correcting to provide better guidance.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-doc-completeness",
        r'''How can I autonomously detect when my documentation advice is incomplete? What signals indicate I am recommending documentation that would leave gaps for the reader?''',
        r'''<think>
Documentation completeness is one of the hardest things to self-evaluate because the gaps are invisible to the person who already understands the system. The key insight is that documentation serves different audiences at different stages, and incomplete documentation fails specific audiences.

Detection strategies:
1. Audience coverage: Does the documentation serve all expected readers?
2. Journey coverage: Does it cover the full user journey?
3. Scenario coverage: Does it address common scenarios and edge cases?
4. Currency: Is it up to date with the current codebase?
</think>

**Autonomous Documentation Completeness Detection**

**Signal 1: Missing audience segments**
```
Check if documentation advice covers all readers:

□ NEW DEVELOPER: Can they set up and run the project?
  Missing: Setup instructions, prerequisites, environment config
  Test: "If someone clones this repo, can they get it running
  with ONLY the documentation?"

□ CONTRIBUTOR: Can they make changes confidently?
  Missing: Architecture overview, coding conventions, PR process
  Test: "If someone wants to add a feature, do they know
  WHERE to add it and HOW to test it?"

□ OPERATOR: Can they deploy and maintain the system?
  Missing: Deployment guide, monitoring, troubleshooting
  Test: "If the system goes down at 3 AM, can the on-call
  engineer diagnose and fix it using only the docs?"

□ API CONSUMER: Can they integrate successfully?
  Missing: API reference, authentication, error codes, examples
  Test: "Can a developer integrate this API without asking
  questions to the team?"

If any audience is unserved, the documentation is incomplete.
```

**Signal 2: Missing journey steps**
```
For each user journey, verify every step is documented:

SETUP JOURNEY:
  Prerequisites → Installation → Configuration → Verification
  Common gap: Configuration (docs say "install" but not "configure")

DEVELOPMENT JOURNEY:
  Architecture → Local dev → Testing → Code review → Merge
  Common gap: Local development setup (works on my machine)

DEBUGGING JOURNEY:
  Symptom → Diagnosis → Root cause → Fix → Verification
  Common gap: Diagnosis (docs explain features, not how to debug)

DEPLOYMENT JOURNEY:
  Build → Stage → Deploy → Verify → Rollback
  Common gap: Rollback procedures (only documented the happy path)

If a journey has gaps, users will get stuck at those points.
```

**Signal 3: Implicit knowledge**
```
Documentation that requires implicit knowledge is incomplete:

IMPLICIT ASSUMPTIONS:
  "Run the migration" → Which migration tool? What command?
  "Set up the database" → Which database? What schema?
  "Configure authentication" → Which provider? What settings?

IMPLICIT CONTEXT:
  "This uses the standard pattern" → What standard pattern?
  "Follow the usual process" → Usual for whom?
  "See the architecture docs" → Where? Which version?

Detection: Read your documentation advice as if you know
NOTHING about the project. Every assumption is a gap.
```

**Signal 4: Missing error documentation**
```
The most valuable documentation covers what goes wrong:

□ COMMON ERRORS: What errors do users encounter?
  For each error: What causes it? How to fix it?

□ EDGE CASES: What happens with unusual inputs?
  Empty data, large volumes, concurrent access, network failures

□ KNOWN ISSUES: What limitations exist?
  What does the system NOT handle? What workarounds exist?

□ MIGRATION ISSUES: What breaks during upgrades?
  What changed? What needs to be updated?

If your documentation advice focuses only on the happy path,
it is incomplete. Users spend most of their time dealing
with the unhappy paths.
```

**Self-correction process**
```
When you detect incomplete documentation advice:

1. IDENTIFY the gap type:
   - Missing audience? → Add a section for that audience
   - Missing journey step? → Fill in the gap
   - Implicit knowledge? → Make it explicit
   - Missing error docs? → Add troubleshooting section

2. PRIORITIZE by impact:
   - Setup docs (blocks everyone) → highest priority
   - API docs (blocks integrators) → high priority
   - Architecture docs (blocks contributors) → medium priority
   - Advanced troubleshooting → lower priority

3. RECOMMEND specific additions:
   Don't say "improve the documentation."
   Say "add a section covering X, including Y and Z,
   with examples showing A and B."
```

**The meta-principle:** Complete documentation answers every question a reader would have at every stage of their journey. If you find yourself thinking "the reader probably already knows this," that is exactly the gap you should fill. The curse of knowledge makes completeness invisible to experts — which is why systematic checking against audiences, journeys, and error scenarios is essential.'''
    ),
    (
        "thinking/auto-autonomous-doc-structure",
        r'''How can I autonomously improve the structure of documentation I recommend? What makes documentation well-organized versus poorly organized?''',
        r'''<think>
Documentation structure determines whether readers can find and absorb information. The same content can be useless or invaluable depending on how it's organized. Poor structure forces readers to read everything to find what they need; good structure lets them jump directly to the relevant section.

Key structural principles:
1. Progressive disclosure (simple first, complex later)
2. Task orientation (organized by what users want to do)
3. Consistent patterns (same structure for similar content)
4. Clear navigation (readers can find what they need)
</think>

**Documentation Structure Quality Framework**

**Principle 1: Progressive disclosure**
```
Information should be layered from simple to complex:

LEVEL 1 — Quick start (30 seconds):
  "Install X, run Y, you'll see Z"
  For: Users who want to try it immediately

LEVEL 2 — Core concepts (5 minutes):
  "The system has three main components: A, B, C.
   A handles X, B handles Y, C handles Z."
  For: Users who want to understand before building

LEVEL 3 — Detailed guides (30 minutes):
  Step-by-step walkthroughs for common tasks
  For: Users building something specific

LEVEL 4 — Reference (as needed):
  Complete API documentation, configuration options
  For: Users who know what they need and want specifics

ANTI-PATTERN: Starting with theory before the quick start.
Most readers want to see it work before understanding why.
```

**Principle 2: Task-oriented organization**
```
Organize by WHAT USERS WANT TO DO, not by system components:

BAD (component-oriented):
  - Database Module
  - Authentication Module
  - API Module
  - Frontend Module

  User thinks: "I want to add a new API endpoint.
  Which sections do I need to read?"

GOOD (task-oriented):
  - Getting Started
  - Adding a New API Endpoint
  - Setting Up Authentication
  - Working with the Database
  - Deploying Changes

  User thinks: "I want to add a new API endpoint.
  I'll read the 'Adding a New API Endpoint' section."
```

**Principle 3: Consistent content patterns**
```
Similar sections should have similar structure:

For every API endpoint:
  - URL and method
  - Request parameters (with types and examples)
  - Response format (with examples)
  - Error responses (with codes and meanings)
  - Example request/response pair

For every configuration option:
  - Name and type
  - Default value
  - Description
  - Example usage
  - Related options

For every how-to guide:
  - Prerequisites
  - Steps (numbered)
  - Expected result
  - Troubleshooting common issues

Consistency lets readers predict where to find information.
```

**Principle 4: Navigation aids**
```
Help readers find information quickly:

□ TABLE OF CONTENTS: At the top of long documents
□ SECTION HEADERS: Descriptive, scannable
  BAD: "Section 3.2" GOOD: "Configuring Database Connections"
□ CROSS-REFERENCES: Link related sections
  "For authentication setup, see [Authentication Guide]"
□ SEARCH-FRIENDLY: Use the terms users would search for
  Include common synonyms and error messages
□ EXAMPLES EARLY: Show an example before the explanation
  Code example first, then explain what each part does
```

**Structure anti-patterns to detect**
```
RED FLAGS in documentation structure:

1. WALL OF TEXT: Long paragraphs without headers or code
   Fix: Break into sections, add code examples

2. BURIED IMPORTANT INFO: Critical details in the middle
   of a paragraph
   Fix: Call out with bold, admonitions, or dedicated sections

3. DUPLICATE INFORMATION: Same thing explained in multiple
   places (becomes inconsistent when one is updated)
   Fix: Single source of truth with cross-references

4. ORPHAN SECTIONS: Content that doesn't connect to
   anything (no links in, no links out)
   Fix: Add cross-references or remove if obsolete

5. WRONG ABSTRACTION LEVEL: Mixing beginner and advanced
   content in the same section
   Fix: Separate into progressive levels
```

**The meta-principle:** Good documentation structure is invisible — readers find what they need without thinking about the organization. Bad structure is very visible — readers get frustrated, skip sections, and miss important information. When advising on documentation, always consider structure alongside content. Well-structured mediocre content beats poorly-structured excellent content.'''
    ),
    (
        "thinking/auto-autonomous-doc-examples",
        r'''How can I autonomously improve the quality of code examples in documentation I recommend? What makes a documentation code example effective versus misleading?''',
        r'''<think>
Code examples are the most-read part of any technical documentation. Studies show developers look at examples before reading explanatory text. Poor examples teach bad habits, mislead about complexity, or fail to work when copied. Good examples are self-contained, correct, and progressive.

Key quality dimensions:
1. Correctness (the example actually works)
2. Completeness (includes all necessary imports, setup)
3. Relevance (shows the thing being documented)
4. Progressive (builds from simple to complex)
5. Real-world (resembles actual use cases, not toy examples)
</think>

**Documentation Code Example Quality Framework**

**Quality dimension 1: Correctness**
```
Every code example should be:

□ RUNNABLE: Can a user copy-paste and execute it?
  BAD:
    result = process(data)  # processes the data
  (What is process? What is data? Where do they come from?)

  GOOD:
    from mylib import process
    data = {"name": "Alice", "age": 30}
    result = process(data)
    print(result)  # Output: {"name": "ALICE", "age": 30}

□ VERSION-SPECIFIC: Does it work with the current version?
  Include version information when APIs change between versions.
  # Requires mylib >= 2.0
  from mylib import process_v2

□ ERROR-FREE: No typos, no wrong method names, no missing args?
  Review every example as if you were running it.
  A single error in an example destroys trust in the docs.
```

**Quality dimension 2: Completeness**
```
Include everything needed to understand AND run the example:

MINIMAL COMPLETE EXAMPLE:
  # Required imports
  from datetime import datetime
  from mylib import Scheduler, Task

  # Setup
  scheduler = Scheduler(timezone="UTC")

  # The actual thing being demonstrated
  task = Task(
      name="daily-report",
      schedule="0 9 * * *",  # 9 AM daily
      handler=generate_report,
  )
  scheduler.add_task(task)
  scheduler.start()

INCLUDES:
  ✓ All imports
  ✓ Required setup/configuration
  ✓ The feature being demonstrated
  ✓ Expected output or result

OMITS (intentionally):
  ✗ Unrelated features
  ✗ Production error handling (unless documenting error handling)
  ✗ Authentication boilerplate (unless documenting auth)
```

**Quality dimension 3: Progressive complexity**
```
Build from simple to complex in documentation examples:

EXAMPLE 1 — Minimal (shows it works):
  client = APIClient("https://api.example.com")
  response = client.get("/users")
  print(response.data)

EXAMPLE 2 — Common use case (shows practical usage):
  client = APIClient("https://api.example.com", api_key="...")
  users = client.get("/users", params={"active": True})
  for user in users.data:
      print(f"{user.name}: {user.email}")

EXAMPLE 3 — Advanced (shows edge cases and configuration):
  client = APIClient(
      base_url="https://api.example.com",
      api_key=os.environ["API_KEY"],
      timeout=30,
      retry_count=3,
      retry_backoff=True,
  )
  try:
      users = client.get("/users", params={"active": True})
  except APITimeout:
      logger.warning("API request timed out")
      users = cache.get("users_fallback")

Each example builds on the previous one.
Users stop at the level of complexity they need.
```

**Quality dimension 4: Realistic context**
```
Examples should resemble real-world usage:

BAD (toy example):
  x = foo(42)
  print(x)
  (What is foo? Why 42? What does x represent?)

GOOD (realistic example):
  user_age = calculate_age(birth_date=datetime(1990, 5, 15))
  print(f"User is {user_age} years old")
  (Clear what's happening and why)

BAD (unrealistic simplification):
  db.query("SELECT * FROM users")
  (No one does this in production — missing parameterization,
   error handling, connection management)

GOOD (realistic with focused simplification):
  async with db.connection() as conn:
      users = await conn.fetch(
          "SELECT id, name, email FROM users WHERE active = $1",
          True,
      )
  (Shows real patterns while keeping the example focused)
```

**Self-detection checklist**
```
Before recommending documentation with code examples:

□ Can I mentally execute this example? (correctness)
□ Would it work if copy-pasted into a fresh file? (completeness)
□ Does it show the feature being documented? (relevance)
□ Is there a simpler version that shows the basics? (progressive)
□ Does it look like code someone would actually write? (realistic)
□ Are variable names meaningful? (clarity)
□ Is the output or result shown? (verifiability)
```

**The meta-principle:** Code examples are not illustrations — they are the primary teaching tool. Most developers will copy an example and modify it rather than reading explanatory text. This means every example must be correct, complete, and representative of good practices. A wrong example in documentation will be copied into hundreds of codebases.'''
    ),
    (
        "thinking/auto-autonomous-doc-maintenance",
        r'''How can I autonomously detect when documentation advice I give will lead to documentation that rots over time? What strategies prevent documentation decay?''',
        r'''<think>
Documentation rot is inevitable unless actively prevented. Documentation decays because:
1. Code changes but docs don't get updated
2. New features are added without corresponding docs
3. Outdated sections are never removed
4. Examples break when dependencies update
5. No one owns the documentation

The autonomous detection challenge is identifying advice that WILL lead to rot before it happens, and recommending structures that resist decay.
</think>

**Documentation Rot Prevention Framework**

**Detecting rot-prone documentation patterns**
```
RED FLAG 1: Hard-coded values that will change
  BAD: "Set the version to 3.2.1 in your config"
  GOOD: "Set the version to the latest stable release
  (check releases page for current version)"

RED FLAG 2: Screenshots of UI elements
  Screenshots rot the fastest — any UI change breaks them.
  Prefer: Text descriptions with element identifiers
  If screenshots needed: Include update instructions

RED FLAG 3: Step-by-step guides with many steps
  The more steps, the more likely one will become outdated.
  Prefer: Scripts or automation that can be tested
  "Run ./setup.sh" stays correct when the script is maintained.

RED FLAG 4: Duplicate information
  When the same fact appears in two places, one will be
  updated and the other will become wrong.
  Prefer: Single source of truth with cross-references.

RED FLAG 5: Documentation disconnected from code
  Docs in a wiki or separate repo rot faster than docs
  next to the code they describe.
  Prefer: Documentation in the same repository as the code.
```

**Rot-resistant documentation strategies**
```
STRATEGY 1: Executable documentation
  Write docs that can be tested:
  - README examples as actual test cases
  - API docs generated from code annotations
  - Configuration docs generated from schema definitions

  If the docs are generated or tested, they cannot silently rot.

STRATEGY 2: Documentation ownership
  Every section has an owner:
  - API docs → API team
  - Deployment docs → DevOps team
  - Architecture docs → Tech leads

  Unowned documentation will rot. Every time.

STRATEGY 3: Documentation review triggers
  Documentation should be reviewed when:
  - A feature is changed (code review includes doc review)
  - A major version is released (docs review sprint)
  - A new team member onboards (they find the gaps)
  - A support ticket references docs (the docs were wrong or missing)

STRATEGY 4: Freshness indicators
  Include "last reviewed" dates:
  <!-- Last reviewed: 2025-11-01 by @alice -->
  Pages not reviewed in 6 months get flagged for review.

STRATEGY 5: Automated link and example checking
  - Link checkers catch broken references
  - Example runners verify code examples still work
  - Schema validators catch outdated configuration docs
```

**Self-correction when advising on documentation**
```
Before recommending a documentation approach, check:

□ MAINTAINABILITY: Will this be easy to keep updated?
  If not → Simplify, automate, or generate from code

□ OWNERSHIP: Will someone be responsible for updates?
  If not → Recommend assigning ownership

□ TESTING: Can correctness be verified automatically?
  If not → Recommend executable examples or doc tests

□ COUPLING: Is the documentation coupled to volatile details?
  If yes → Abstract away volatile details or auto-generate

□ SCOPE: Is the documentation trying to cover too much?
  If yes → Split into focused sections with clear ownership
```

**The meta-principle:** The best documentation is documentation that cannot silently become wrong. Generate it from code when possible, test it automatically when you can, and assign human owners when you must rely on manual updates. When advising on documentation, always ask: "Will this still be correct in six months?" If the answer is uncertain, the approach needs more automation or less coupling to volatile details.'''
    ),
    (
        "thinking/auto-autonomous-doc-audience-calibration",
        r'''How can I autonomously calibrate my documentation advice to the right audience level? How do I avoid writing documentation that is too advanced for beginners or too basic for experts?''',
        r'''<think>
Audience calibration is one of the most common documentation failures. The writer's curse of knowledge makes them skip steps that are obvious to them but unknown to the reader. Conversely, experienced readers get frustrated wading through basic explanations to find the advanced details they need.

The solution is:
1. Identify the target audience explicitly
2. Separate content by expertise level
3. Use progressive disclosure
4. Provide escape hatches (skip-to-advanced, back-to-basics)
</think>

**Documentation Audience Calibration Framework**

**Step 1: Identify the audience explicitly**
```
Before writing any documentation, state who it's for:

PRIMARY AUDIENCE: Who will read this most?
  - New users setting up for the first time?
  - Experienced users looking up specific details?
  - Contributors extending the system?
  - Operators running it in production?

SECONDARY AUDIENCE: Who else might read this?
  - Evaluators deciding whether to adopt?
  - Managers reviewing technical decisions?
  - Future maintainers understanding design choices?

The primary audience determines the DEFAULT level.
The secondary audience determines what ADDITIONAL content
to include (in clearly separated sections).
```

**Step 2: Calibrate language and assumptions**
```
BEGINNER AUDIENCE:
  Language: Define technical terms on first use
  Assumptions: They have general programming knowledge
    but not domain-specific knowledge
  Examples: Complete, runnable, heavily commented
  Structure: Step-by-step, sequential

  "A *middleware* is a function that runs before your
   request handler. It can modify the request, check
   authentication, or log information."

INTERMEDIATE AUDIENCE:
  Language: Use standard technical terms without definition
  Assumptions: They understand the domain concepts
    but not this specific tool
  Examples: Focused on the specific feature, less scaffolding
  Structure: Task-oriented, with links to basics

  "Add authentication middleware to your route group.
   The middleware validates the JWT token and attaches
   the user object to the request context."

ADVANCED AUDIENCE:
  Language: Precise technical language
  Assumptions: They understand the tool and want
    optimization, edge cases, or internals
  Examples: Minimal, focused on the specific technique
  Structure: Reference-style, with links to source code

  "The authentication middleware uses RS256 verification
   by default. Override with middleware.Config{Algorithm: 'ES256'}
   for ECDSA. Note: key rotation requires cache invalidation
   (see CacheConfig.KeyRotationInterval)."
```

**Step 3: Structural separation**
```
Do not mix levels in the same section. Separate clearly:

OPTION A: Separate documents
  getting-started.md    → Beginners
  user-guide.md         → Intermediate
  api-reference.md      → Advanced
  architecture.md       → Contributors

OPTION B: Collapsible sections
  ## Setup
  Basic instructions for everyone

  <details><summary>Advanced Configuration</summary>
  Detailed options for experienced users
  </details>

OPTION C: Progressive sections within one document
  ## Quick Start (beginner)
  ## Configuration Guide (intermediate)
  ## Advanced Topics (advanced)
  ## API Reference (reference)
```

**Step 4: Self-detection of miscalibration**
```
SIGN: TOO ADVANCED FOR AUDIENCE
  - Uses jargon without definition
  - Skips setup steps ("obviously, first configure X")
  - Examples require knowledge not yet introduced
  - Reader would need to read other docs to understand this one
  Fix: Add definitions, include all steps, add prerequisites

SIGN: TOO BASIC FOR AUDIENCE
  - Explains things the audience already knows
  - Long preambles before getting to the point
  - Excessive hand-holding in examples
  - Reader skims impatiently to find the actual information
  Fix: Move basics to a separate section, lead with the answer

SIGN: MIXED LEVELS (worst case)
  - Alternates between basic explanations and advanced concepts
  - Reader doesn't know which parts to skip or read carefully
  - Both beginners and experts are frustrated
  Fix: Restructure into clearly separated levels
```

**Calibration checklist**
```
Before finalizing documentation advice:

□ AUDIENCE STATED: Is it clear who this is for?
□ LEVEL CONSISTENT: Does the entire document maintain
  the same expertise level?
□ TERMS DEFINED: Are technical terms defined for the
  stated audience level?
□ PREREQUISITES LISTED: Does the reader know what they
  need before starting?
□ ESCAPE HATCHES: Can advanced readers skip ahead?
  Can beginners find more detailed explanations?
□ EXAMPLES MATCHED: Do code examples match the audience's
  expected skill level?
```

**The meta-principle:** Documentation that tries to serve everyone serves no one. Explicitly identify your audience, calibrate your language and assumptions to their level, and provide clear pathways for readers at different levels. The most common mistake is writing for yourself instead of your reader — always ask "does my READER know this?" not "do I know this?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
