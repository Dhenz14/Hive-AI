"""Phase 4F: Self-Improvement — Quality Assurance (Part 11)

Quality checklists for CI/CD pipeline advice — ensuring
recommendations for continuous integration and deployment
are practical, secure, and maintainable.
"""

PAIRS = [
    (
        "thinking/auto-qa-cicd-pipeline-design",
        r'''What quality checks should I apply when recommending CI/CD pipeline designs? How do I ensure my pipeline advice is practical and not over-engineered?''',
        r'''<think>
CI/CD pipeline advice frequently falls into two traps:
1. Too simple (just "run tests and deploy") which misses critical steps
2. Too complex (enterprise-grade pipeline for a solo developer's project)

The quality check must ensure the pipeline matches the team's needs, includes essential safety gates, and doesn't create a bottleneck that slows down development.

Key dimensions to verify:
- Appropriate complexity for the team size
- Essential safety gates included
- Speed (fast feedback loop)
- Reliability (not flaky)
- Security (secrets handling, dependency scanning)
</think>

**CI/CD Pipeline Design Quality Checklist**

**Before recommending any pipeline design:**

**Step 1: Context assessment**
```
□ TEAM SIZE: How many developers contribute?
  1-3 → Simple pipeline (build, test, deploy)
  4-10 → Standard pipeline (lint, test, build, staging, deploy)
  10+ → Full pipeline (parallel stages, environments, approvals)

□ DEPLOYMENT FREQUENCY: How often do they deploy?
  Multiple times/day → Fully automated, fast pipeline
  Weekly → Automated with manual approval gate
  Monthly → Can tolerate slower pipeline

□ RISK TOLERANCE: What breaks if deployment goes wrong?
  High risk (financial, medical) → Multiple environments, canary
  Medium risk (SaaS) → Staging + automated rollback
  Low risk (internal tools) → Simpler gates, faster deployment

□ EXISTING INFRASTRUCTURE: What do they already have?
  Recommend tools that fit their current ecosystem:
  GitHub → GitHub Actions
  GitLab → GitLab CI
  AWS → CodePipeline or GitHub Actions with AWS
  Self-hosted → Jenkins or GitLab CI
```

**Step 2: Essential pipeline stages**
```
MINIMUM VIABLE PIPELINE (every project needs this):

Stage 1: Lint/Format check
  □ Catches style issues before review
  □ Runs in < 1 minute
  □ Fails fast (first stage to run)

Stage 2: Unit tests
  □ Runs the test suite
  □ Reports coverage (but doesn't gate on coverage percentage)
  □ Target: < 5 minutes

Stage 3: Build
  □ Compiles/packages the application
  □ Verifies the build artifact works
  □ Stores artifact for deployment

Stage 4: Deploy
  □ Deploys to the target environment
  □ Runs smoke tests after deployment
  □ Has rollback capability

ADDITIONAL STAGES (add based on need):
  □ Integration tests (if the project has them)
  □ Security scanning (if handling sensitive data)
  □ Staging deployment (if risk tolerance requires it)
  □ Performance tests (if performance is critical)
  □ Manual approval (if compliance requires it)
```

**Step 3: Speed check**
```
□ TOTAL PIPELINE TIME: Under target?
  Target for PR pipeline: < 10 minutes
  Target for deployment pipeline: < 20 minutes

  If over target:
  - Parallelize independent stages
  - Cache dependencies (node_modules, pip packages)
  - Use incremental builds
  - Run only affected tests on PR, full suite on merge

□ FAST FEEDBACK: Most common failures caught first?
  Order stages by: speed (fastest first) AND failure rate
  Lint fails most often → run first (< 30 seconds)
  Unit tests catch most bugs → run second (< 5 minutes)
  Build issues are less common → run after tests

□ CACHING: Dependencies cached between runs?
  Missing caching adds 2-5 minutes to every run.
  Cache: package manager downloads, build artifacts, Docker layers
```

**Step 4: Reliability check**
```
□ NO FLAKY STEPS: Every step passes consistently?
  Flaky CI is worse than no CI — team learns to ignore failures.
  If a step is flaky → fix it or remove it.

□ IDEMPOTENT: Running the pipeline twice produces the same result?
  No side effects from previous runs.
  No dependency on external state that changes.

□ ISOLATED: Pipeline doesn't depend on other pipelines?
  Each pipeline should be self-contained.
  Shared resources (test databases) need isolation.

□ CLEAR FAILURES: When the pipeline fails, is it obvious why?
  Good: "Test test_login_flow failed: expected 200, got 401"
  Bad: "Pipeline failed" with a 500-line log to search through
```

**Step 5: Security check**
```
□ SECRETS MANAGEMENT: No secrets in code or logs?
  Use pipeline secrets/variables, not hardcoded values
  Mask secrets in log output
  Rotate secrets regularly

□ DEPENDENCY SCANNING: Known vulnerabilities checked?
  npm audit, pip-audit, or Snyk/Dependabot
  Don't block on informational findings (too noisy)
  Block on critical/high severity findings

□ LEAST PRIVILEGE: Pipeline has minimal permissions?
  CI doesn't need admin access to production
  Deploy step has deploy permissions only
  Read-only access where possible

□ ARTIFACT INTEGRITY: Build artifacts are trusted?
  Signed artifacts for production deployments
  Pinned dependency versions (lockfile committed)
  Base images pinned to specific digests, not tags
```

**Anti-patterns to catch**
```
□ NOT A GATEKEEPER: Pipeline enables delivery, not blocks it
  If the pipeline takes 45 minutes, developers will avoid CI.

□ NOT A DUMP: Pipeline has clear stages, not 50 random steps
  Each stage has a clear purpose and exits early on failure.

□ NOT MANUAL: Everything that can be automated IS automated
  If a step requires a human to click something, automate it.
  Exception: Intentional approval gates for compliance.

□ NOT FRAGILE: Pipeline survives infrastructure hiccups
  Network timeouts → retry
  Package registry down → use cached dependencies
  Test flakiness → fix tests, don't add retries
```

**The meta-principle:** A CI/CD pipeline exists to give developers confidence to ship code frequently. If the pipeline is slow, flaky, or confusing, it becomes an obstacle instead of an enabler. Design for fast feedback, clear failures, and appropriate safety — not for theoretical completeness.'''
    ),
    (
        "thinking/auto-qa-cicd-deployment-strategies",
        r'''What quality checks should I apply when recommending deployment strategies? How do I ensure I recommend the right deployment approach for the team's context?''',
        r'''<think>
Deployment strategy advice is highly context-dependent. The right strategy depends on:
- Risk tolerance (what happens if a bad deploy goes out)
- Team size and ops maturity
- Infrastructure capabilities
- Rollback requirements
- Downtime tolerance

Common mistake: recommending blue-green or canary deployments for a team that can barely manage a single deployment target. The complexity of the deployment strategy must match the team's operational capacity.
</think>

**Deployment Strategy Quality Checklist**

**Context-based strategy selection**
```
SOLO/SMALL TEAM + LOW RISK:
  Strategy: Direct deployment with rollback
  Process: Deploy → smoke test → rollback if broken
  Complexity: Low
  Downtime: Brief (seconds to minutes)
  Appropriate for: Internal tools, personal projects, prototypes

SMALL TEAM + MEDIUM RISK:
  Strategy: Blue-green deployment
  Process: Deploy to inactive environment → switch traffic → keep
    old environment as rollback target
  Complexity: Medium (need two environments)
  Downtime: Zero (traffic switch is instant)
  Appropriate for: SaaS products, customer-facing applications

MEDIUM TEAM + HIGH RISK:
  Strategy: Canary deployment
  Process: Deploy to small percentage of traffic → monitor →
    gradually increase → full rollout
  Complexity: High (need traffic splitting, monitoring)
  Downtime: Zero
  Appropriate for: High-traffic applications, financial systems

LARGE TEAM + CRITICAL SYSTEMS:
  Strategy: Progressive delivery with feature flags
  Process: Deploy code → enable features gradually per user segment
    → monitor → full enablement
  Complexity: Very high (feature flag system, monitoring, segments)
  Downtime: Zero
  Appropriate for: Large-scale products, regulated industries
```

**Quality checks for any deployment recommendation**
```
□ ROLLBACK PLAN: Can they undo a bad deployment?
  Every deployment strategy MUST have a rollback plan.
  "Deploy and pray" is not a strategy.

  Questions to answer:
  - How long does rollback take? (Target: < 5 minutes)
  - Is rollback automated or manual?
  - Does rollback require a database migration revert?
  - Who can trigger a rollback?

□ SMOKE TESTS: Is the deployment verified automatically?
  After every deployment:
  - Health check endpoint responds
  - Core user flows work
  - No error rate spike
  - Response times are normal

□ DATABASE MIGRATIONS: Handled correctly?
  This is the hardest part of deployment.
  Rules:
  - Migrations must be backward-compatible
  - Deploy migration BEFORE the code that uses it
  - Never drop columns in the same deploy that removes the code
  - Have a migration rollback plan

□ MONITORING: Can they detect a bad deployment?
  Essential metrics after deployment:
  - Error rate (should not increase)
  - Response time (should not increase significantly)
  - Request volume (should remain normal)
  - Key business metrics (orders, signups — should not drop)
```

**Deployment strategy anti-patterns**
```
□ BIG BANG DEPLOYMENT:
  Deploying everything at once with no rollback plan.
  Fix: Deploy incrementally, always have rollback.

□ FRIDAY DEPLOYMENT:
  Deploying before the team leaves for the weekend.
  Fix: Deploy early in the week when the team is available.

□ SNOWFLAKE DEPLOYMENT:
  Every deployment is a unique manual process.
  Fix: Automate everything. Same process every time.

□ OVER-COMPLEX DEPLOYMENT:
  Canary deployment for an app with 10 users.
  Fix: Match deployment complexity to actual risk and scale.

□ NO VERIFICATION:
  Deploy and assume it works.
  Fix: Automated smoke tests after every deployment.
```

**The meta-principle:** The best deployment strategy is the simplest one that provides adequate safety for the actual risk level. A team that deploys confidently with a simple strategy ships more reliably than a team that struggles with a complex strategy they don't fully understand. Match the strategy to the team's operational maturity, not to industry best practices designed for much larger organizations.'''
    ),
    (
        "thinking/auto-qa-cicd-pipeline-maintenance",
        r'''What quality checks should I apply when advising on CI/CD pipeline maintenance? How do I help teams keep their pipelines healthy over time?''',
        r'''<think>
CI/CD pipeline maintenance is often neglected because pipelines are treated as "set and forget" infrastructure. But pipelines rot just like code — dependencies become outdated, steps become slow, and flaky tests accumulate. The quality check should ensure advice includes maintenance practices, not just initial setup.
</think>

**CI/CD Pipeline Maintenance Quality Checklist**

**Pipeline health metrics**
```
□ PIPELINE DURATION: Is it trending up?
  Track median pipeline duration over time.
  Action if increasing: Profile stages, optimize or parallelize.
  Target: PR pipeline < 10 min, deploy pipeline < 20 min.

□ FAILURE RATE: What percentage of runs fail?
  Healthy: < 10% failure rate (failures are real bugs)
  Concerning: 10-30% (likely has flaky tests or infra issues)
  Unhealthy: > 30% (team ignores CI, pipeline is useless)

□ FLAKY TEST RATE: How often do tests pass on retry?
  Track tests that fail then pass on re-run.
  These are flaky and need fixing.
  Target: < 2% flake rate.

□ QUEUE TIME: How long do jobs wait before running?
  If jobs queue for minutes, developers lose context.
  Fix: Add more runners or optimize resource usage.
```

**Regular maintenance tasks**
```
WEEKLY:
  □ Review failed pipelines — are failures real or flaky?
  □ Check for disabled/skipped steps — are they still needed?
  □ Monitor queue times — are developers waiting?

MONTHLY:
  □ Update CI runner images/tools to latest stable versions
  □ Review and update cached dependencies
  □ Check for unused pipeline stages (added but never useful)
  □ Review secrets — are any expired or rotatable?

QUARTERLY:
  □ Profile pipeline duration — which stages are slowest?
  □ Review the pipeline structure — does it still match the project?
  □ Check dependency scanning results — are findings addressed?
  □ Test the rollback procedure — does it still work?
  □ Review pipeline permissions — still least privilege?
```

**Pipeline dependency management**
```
□ RUNNER IMAGES:
  Pin to specific versions, not "latest."
  Schedule updates rather than getting surprised by breaking changes.
  Example: Use node:20.11-slim, not node:latest

□ ACTION/PLUGIN VERSIONS:
  Pin to specific versions or commit SHAs.
  BAD:  uses: actions/checkout@main (can break any time)
  GOOD: uses: actions/checkout@v4.1.1 (predictable)

□ BUILD TOOL VERSIONS:
  Pin compiler, linter, formatter versions in the pipeline.
  "Works locally but fails in CI" is often a version mismatch.

□ LOCKFILES:
  Commit lockfiles (package-lock.json, poetry.lock, go.sum).
  CI should install from lockfile, not resolve fresh dependencies.
```

**Pipeline simplification over time**
```
Pipelines tend to accumulate steps that were added for a reason
but are no longer needed:

□ AUDIT EACH STEP:
  For every step in the pipeline, ask:
  - What does this step catch? (If nothing in 6 months → remove)
  - How long does this step take? (If > 2 min → optimize)
  - Is this step duplicated elsewhere? (If yes → consolidate)
  - Does the team trust this step? (If ignored → fix or remove)

□ CONSOLIDATE SIMILAR STEPS:
  Multiple lint checks → one comprehensive linter
  Multiple test commands → one test runner with configuration
  Multiple build steps → one build script

□ REMOVE DEAD STEPS:
  Steps that were added for a feature that was removed
  Steps that check for issues that no longer exist
  Steps that always pass (testing nothing meaningful)
```

**Pipeline documentation**
```
□ WHAT EACH STAGE DOES: Not just the name, but why it exists
  "security-scan: Checks dependencies for known CVEs.
   Added after the log4j incident. Blocks on critical severity."

□ HOW TO RUN LOCALLY: Developers should be able to run
  pipeline checks on their machine before pushing.
  "Run ./scripts/ci-check.sh to run all CI checks locally."

□ HOW TO DEBUG FAILURES: Common failure modes and fixes
  "If npm install fails: Delete node_modules and package-lock.json,
   then run npm install again."

□ WHO OWNS IT: Who is responsible for pipeline maintenance?
  Unowned pipelines rot fastest.
```

**The meta-principle:** A CI/CD pipeline is a living system that requires ongoing maintenance. Treat it with the same rigor as production code — monitor its health, update its dependencies, remove dead weight, and ensure someone owns it. A neglected pipeline becomes slow, flaky, and ignored — at which point it provides negative value because it gives false confidence while not actually catching issues.'''
    ),
    (
        "thinking/auto-qa-cicd-environment-management",
        r'''What quality checks should I apply when advising on environment management in CI/CD? How do I help teams manage development, staging, and production environments effectively?''',
        r'''<think>
Environment management is a frequent source of deployment failures. "It works in staging but not in production" is one of the most common and frustrating issues. Good environment management minimizes the differences between environments while acknowledging that some differences are necessary.

Key principles:
1. Environments should be as similar as possible
2. Configuration differences should be explicit and minimal
3. Data differences should be understood and managed
4. Secrets should be environment-specific and properly managed
</think>

**Environment Management Quality Checklist**

**Environment parity**
```
□ SAME CODE: All environments run the same build artifact?
  Don't rebuild for each environment. Build once, deploy everywhere.
  Configuration is external, not baked into the build.

□ SAME DEPENDENCIES: Same versions of services and libraries?
  Production runs PostgreSQL 15? Staging should too.
  Production uses Redis 7? Development should too.
  Docker makes this easy — use the same images everywhere.

□ SAME CONFIGURATION STRUCTURE: Same config keys, different values?
  Every environment should use the same configuration keys.
  Only the VALUES differ (database URL, API keys, feature flags).

  BAD: Production has CACHE_ENABLED, staging doesn't have it at all
  GOOD: Both have CACHE_ENABLED; production=true, staging=false

□ KNOWN DIFFERENCES: Documented and intentional?
  Some differences are necessary:
  - Scale (fewer instances in staging)
  - Data (different database content)
  - External services (sandbox vs production APIs)
  Document every intentional difference.
```

**Configuration management**
```
□ EXTERNALIZED: Configuration is outside the code?
  Use environment variables, config files, or secret managers.
  Never hardcode environment-specific values in source code.

□ VALIDATED: Configuration is checked at startup?
  The application should fail fast if required config is missing.
  Don't let a missing API key cause a runtime error 3 hours later.

  Example:
    def validate_config():
        required = ['DATABASE_URL', 'API_KEY', 'SECRET_KEY']
        missing = [k for k in required if k not in os.environ]
        if missing:
            raise SystemExit(f"Missing config: {', '.join(missing)}")

□ DOCUMENTED: Every config variable is documented?
  Name, type, default, description, example value.
  Developers shouldn't guess what CACHE_TTL means or what
  values are valid.

□ MINIMAL: Only necessary differences between environments?
  If staging and production have the same value for a setting,
  don't make it configurable. Fewer config differences
  mean fewer environment-related bugs.
```

**Secrets management**
```
□ NEVER IN CODE: Secrets are not committed to version control?
  Use pipeline secrets, vault, or cloud secret managers.
  Scan for accidentally committed secrets (git-secrets, trufflehog).

□ ENVIRONMENT-SPECIFIC: Each environment has its own secrets?
  Never share API keys between staging and production.
  If staging is compromised, production should not be affected.

□ ROTATABLE: Secrets can be rotated without code changes?
  If rotating a secret requires a code deploy, the secret
  management is too tightly coupled.

□ AUDITABLE: Who accessed which secrets and when?
  Cloud secret managers provide audit logs.
  Pipeline secret access should be logged.
```

**Data management across environments**
```
□ PRODUCTION DATA NOT IN STAGING:
  Never copy production data directly to staging.
  Use anonymized/synthetic data for testing.
  If you must use production data, scrub PII first.

□ SEED DATA FOR DEVELOPMENT:
  Provide scripts to populate development databases
  with realistic but fake data.
  Developers shouldn't need production access to test.

□ MIGRATION TESTING:
  Test database migrations in staging before production.
  Staging should have similar data volume for migration timing.
  If a migration takes 30 minutes on 1M rows, know that
  before running it on production's 50M rows.
```

**The meta-principle:** Environment management is about controlling differences. The fewer differences between environments, the fewer "works in staging, breaks in production" incidents. Make differences explicit, minimal, and documented. Every undocumented difference is a future production incident waiting to happen.'''
    ),
    (
        "thinking/auto-qa-cicd-rollback-procedures",
        r'''What quality checks should I apply when advising on rollback procedures? How do I ensure rollback advice is practical and actually works when needed?''',
        r'''<think>
Rollback procedures are the safety net of deployment. They're the thing you hope you never need but must have ready. The quality challenge is that rollbacks are rarely tested, and when they're needed, the team is already stressed from a production incident.

Key issues:
1. Rollback procedures that were never tested
2. Database migrations that can't be reversed
3. Rollback steps that are documented but don't work
4. No one knows WHO can trigger a rollback
5. Rollback takes too long (meanwhile, users are affected)
</think>

**Rollback Procedure Quality Checklist**

**Rollback readiness**
```
□ TESTED: Has the rollback procedure been tested recently?
  A rollback procedure that has never been tested is not a procedure.
  It's a hope. Schedule regular rollback drills.

  Test quarterly:
  1. Deploy a known-good version
  2. Deploy a "bad" version (intentionally)
  3. Execute the rollback procedure
  4. Verify the system is back to normal
  5. Measure how long it took

□ DOCUMENTED: Written step-by-step instructions exist?
  The person executing the rollback may not be the person
  who designed the deployment. Write for the person who
  is stressed and tired at 3 AM.

  Include:
  - Exact commands to run
  - Expected output at each step
  - What to do if a step fails
  - Who to contact if the rollback fails

□ AUTHORIZED: Who can trigger a rollback?
  In an incident, waiting for approval costs time.
  Pre-authorize: Any on-call engineer can roll back.
  Require approval only for: rolling FORWARD after a rollback.

□ FAST: How long does the rollback take?
  Target: < 5 minutes from decision to completion
  If longer → the procedure needs optimization
  Common speedup: Keep previous deployment artifact ready
```

**Database rollback considerations**
```
□ BACKWARD-COMPATIBLE MIGRATIONS:
  Every migration should work with both the old and new code.
  This enables rollback without reverting the migration.

  Example of backward-compatible migration:
  Deploy 1: Add new column (nullable, with default)
  Deploy 2: Code writes to both old and new columns
  Deploy 3: Migrate data from old to new column
  Deploy 4: Code reads from new column only
  Deploy 5: Remove old column

  At any point, you can roll back the code without
  reverting the database schema.

□ MIGRATION REVERSAL:
  Can each migration be reversed?
  Adding a column → reversible (drop the column)
  Dropping a column → NOT reversible (data is lost)
  Renaming a column → reversible but risky

  For irreversible migrations:
  - Take a backup before migrating
  - Ensure the migration is tested in staging first
  - Have a restore procedure documented

□ DATA CHANGES:
  Some deployments change data, not just schema.
  "Backfill user emails" → How do you undo a backfill?
  If you can't → ensure the backfill is correct before running
```

**Rollback scenarios to plan for**
```
SCENARIO 1: Code bug detected immediately
  Rollback: Redeploy previous version
  Time: < 5 minutes
  Data impact: None (no data changes yet)

SCENARIO 2: Code bug detected after hours
  Rollback: Redeploy previous version
  Time: < 5 minutes for code, but data may have been modified
  Data impact: Need to assess data changes made by buggy code

SCENARIO 3: Database migration problem
  Rollback: Depends on migration type
  Reversible migration → run reverse migration
  Irreversible migration → restore from backup
  Time: Minutes for reverse, hours for restore

SCENARIO 4: Third-party dependency failure
  Rollback: May not be possible (the dependency is external)
  Alternative: Feature flag to disable the affected feature
  Time: Depends on feature flag readiness

SCENARIO 5: Configuration error
  Rollback: Revert configuration change
  Time: < 1 minute if config is external
  Common issue: Config change + code change deployed together
  Fix: Deploy config changes separately from code changes
```

**Rollback anti-patterns**
```
□ COUPLED ROLLBACK: Rolling back requires coordinating
  multiple services simultaneously.
  Fix: Design services to be independently deployable
  and backward-compatible.

□ NO PREVIOUS ARTIFACT: The previous build artifact
  was deleted or overwritten.
  Fix: Keep at least the last 3 deployment artifacts.

□ ROLLBACK REQUIRES REBUILD: You can't deploy the old
  version without rebuilding it.
  Fix: Store build artifacts, deploy artifacts not source.

□ UNTESTED ROLLBACK: "We have a rollback procedure but
  we've never actually used it."
  Fix: Schedule quarterly rollback drills.
```

**The meta-principle:** A deployment without a tested rollback procedure is a deployment without a safety net. The time to figure out how to roll back is before you need to, not during a production incident at 3 AM. Keep rollback procedures simple, tested, and fast. The confidence to deploy frequently comes from knowing you can undo any deployment quickly.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
