"""Phase 4F: Self-Improvement — Quality Assurance (Part 7)

Quality checklists for testing strategy advice — ensuring testing
recommendations are practical, well-prioritized, and maintainable.
"""

PAIRS = [
    (
        "thinking/auto-qa-testing-strategy-completeness",
        r'''What quality checks should I apply when recommending a testing strategy to ensure it's complete and practical, not just theoretical?''',
        r'''<think>
Testing strategy advice often fails because it's either too theoretical ("follow the testing pyramid") or too prescriptive ("achieve 100% coverage"). Good testing strategy advice must be:

1. Prioritized (what to test first based on risk)
2. Practical (can be implemented with the team's current tools and skills)
3. Maintainable (tests don't become a burden)
4. Proportional (testing effort matches the risk)
5. Specific to the type of application

**Common failure modes:**
- Recommending too many test types without prioritization
- Focusing on coverage percentage instead of covering critical paths
- Ignoring test maintenance cost
- Not considering the team's testing maturity
</think>

**Testing Strategy Quality Checklist**

**Before recommending any testing strategy:**

**Step 1: Context assessment**
```
□ APPLICATION TYPE: What kind of application?
  - Web API → Focus on integration tests, contract tests
  - UI application → Focus on component tests, E2E for critical flows
  - Library/SDK → Focus on unit tests, compatibility tests
  - Data pipeline → Focus on data validation, integration tests
  - CLI tool → Focus on integration tests, snapshot tests

□ TEAM MATURITY: What's their current testing practice?
  No tests → Start with integration tests for critical paths
  Some unit tests → Add integration tests, fill gaps
  Good test suite → Optimize, add E2E, improve speed

□ RISK PROFILE: What breaks most often? What's most costly to break?
  Payment processing → Heavy testing
  Marketing landing page → Light testing
  Authentication → Heavy testing
  Admin dashboard → Moderate testing
```

**Step 2: Prioritized recommendation**
```
□ TESTING PRIORITY ORDER (most impactful first):

  Priority 1: Critical path tests
    Test the paths where bugs cause the most damage:
    - Authentication/authorization
    - Payment/billing
    - Data integrity (writes, deletes)
    - Core business logic

  Priority 2: Integration tests
    Test that components work together:
    - API endpoints with database
    - Service-to-service calls
    - External API integrations

  Priority 3: Unit tests for complex logic
    Test algorithms and business rules in isolation:
    - Calculation functions
    - Validation logic
    - State machines
    - Edge cases in parsing/formatting

  Priority 4: E2E tests for key user flows
    Test complete user journeys:
    - Sign up → use feature → outcome
    - Purchase flow
    - Most common user paths

  Priority 5: Edge cases and regression tests
    Add tests as bugs are found:
    - Every bug fix gets a test
    - Edge cases discovered in production
```

**Step 3: Practical implementation check**
```
□ TOOL RECOMMENDATIONS: Matched to their stack?
  Python: pytest (not unittest — pytest is simpler)
  JavaScript: Vitest or Jest (not Mocha — less setup needed)
  E2E: Playwright (not Selenium — more reliable)
  API: httpx/supertest (not manual curl commands)

□ EXAMPLE PROVIDED: Can they start immediately?
  Don't just say "write integration tests."
  Show a concrete example for their specific stack.

□ CI INTEGRATION: Tests run automatically?
  Tests that don't run in CI are tests that get skipped.

□ SPEED CONSIDERATION: Test suite runs in <10 minutes?
  Slow tests get bypassed. Keep the feedback loop fast.
```

**Step 4: Anti-pattern check**
```
□ NOT CHASING COVERAGE: Coverage is a metric, not a goal?
  80% coverage with meaningful tests > 100% coverage
  with trivial assertions.

□ NOT OVER-MOCKING: Tests verify real behavior?
  If everything is mocked, you're testing your mocks,
  not your code.

□ NOT TESTING IMPLEMENTATION: Tests verify behavior?
  BAD: Assert that function calls mock exactly 3 times
  GOOD: Assert that the output is correct

□ NOT BRITTLE: Tests don't break on irrelevant changes?
  If renaming a CSS class breaks 50 tests,
  those tests are too tightly coupled to implementation.
```

**The meta-principle:** The best testing strategy is the one the team will actually follow. A comprehensive strategy that gets ignored is worse than a minimal strategy that gets executed. Start with the highest-risk, lowest-effort tests and expand from there.'''
    ),
    (
        "thinking/auto-qa-testing-unit-test-quality",
        r'''What quality checks should I apply when reviewing or advising on unit tests? How do I distinguish good unit tests from tests that just pad coverage numbers?''',
        r'''<think>
Unit test quality is about whether the tests actually catch bugs and help developers work confidently. Low-quality tests create a false sense of security and add maintenance burden without catching real bugs.

**Signs of low-quality unit tests:**
1. Testing trivial code (getters/setters)
2. Testing implementation instead of behavior
3. Over-mocking (the test is testing the mocks)
4. No meaningful assertions (just "doesn't throw")
5. Tightly coupled to implementation details
6. No edge case coverage
7. Hard to read and understand what they're testing
</think>

**Unit Test Quality Checklist**

**For every unit test or test recommendation:**

**1. Testing the right things**
```
□ TESTS BEHAVIOR, NOT IMPLEMENTATION:
  BAD:
    def test_uses_hashmap_internally():
        service = UserService()
        assert isinstance(service._cache, dict)
    (Tests internal data structure — breaks on refactor)

  GOOD:
    def test_returns_cached_user_on_second_call():
        service = UserService(db=mock_db)
        service.get_user(1)
        service.get_user(1)
        assert mock_db.query.call_count == 1  # only one DB call
    (Tests behavior — cache works regardless of implementation)

□ TESTS MEANINGFUL LOGIC:
  DON'T test:
    - Getters and setters (no logic)
    - Framework code (let the framework test itself)
    - Simple data transformations with no branching

  DO test:
    - Business rules with conditions
    - Edge cases (null, empty, boundary values)
    - Error handling paths
    - Complex calculations
```

**2. Test structure quality**
```
□ ARRANGE-ACT-ASSERT (AAA) pattern:
  def test_discount_applied_for_premium_users():
      # Arrange
      user = User(tier="premium")
      cart = Cart(items=[Item(price=100)])

      # Act
      total = calculate_total(cart, user)

      # Assert
      assert total == 90  # 10% premium discount

□ ONE BEHAVIOR PER TEST:
  BAD: test_user_creation (tests creation, validation,
       notification, and database write all in one test)
  GOOD: Separate tests for each behavior

□ DESCRIPTIVE TEST NAMES:
  BAD: test_calculate, test_user_1, test_edge_case
  GOOD: test_returns_zero_for_empty_cart,
        test_raises_error_for_negative_quantity,
        test_applies_bulk_discount_above_10_items
```

**3. Assertion quality**
```
□ SPECIFIC ASSERTIONS:
  BAD:  assert result is not None  (too vague)
  GOOD: assert result.total == 42.50

  BAD:  assert len(errors) > 0  (doesn't check which errors)
  GOOD: assert errors == ["Email is required", "Name is required"]

□ FAILURE MESSAGE IS HELPFUL:
  When the test fails, does the output tell you what's wrong?
  assert calculate_tax(100, "CA") == 7.25, \
      f"CA tax on $100 should be $7.25"
```

**4. Edge case coverage**
```
□ BOUNDARY VALUES:
  - Zero, one, max value
  - Empty string, None, empty list
  - Exact boundary (if limit is 100, test 99, 100, 101)

□ ERROR CASES:
  - Invalid input types
  - Missing required fields
  - Network/database failures (mocked)
  - Concurrent access (if applicable)

□ REGRESSION TESTS:
  - Every bug fix has a test that would have caught it
  - "This test exists because bug #1234 happened"
```

**5. Maintenance considerations**
```
□ NOT BRITTLE:
  Tests should survive refactoring.
  If changing implementation (not behavior) breaks tests,
  the tests are testing implementation.

□ NOT SLOW:
  Unit tests should run in milliseconds, not seconds.
  If tests are slow → likely doing I/O (database, network).
  Mock external dependencies for unit tests.

□ NOT FLAKY:
  Tests should pass 100% of the time or fail 100% of the time.
  Flaky tests: tests that depend on timing, randomness,
  external state, or test execution order.
```

**The meta-principle:** A good unit test answers the question "does this behavior work correctly?" If you can't state the behavior being tested in plain English, the test probably isn't testing the right thing. Tests should be documentation — reading the test names should tell you what the system does.'''
    ),
    (
        "thinking/auto-qa-testing-integration-test-advice",
        r'''What quality checks should I apply when advising on integration tests? How do I help users write integration tests that are reliable and valuable?''',
        r'''<think>
Integration tests verify that components work together correctly. They're more valuable than unit tests for catching real bugs but harder to write and maintain well.

**Common integration test problems:**
1. Too slow (hitting real databases, external APIs)
2. Flaky (depend on external state, timing, or order)
3. Too broad (testing everything, hard to diagnose failures)
4. Too narrow (basically unit tests with more setup)
5. Hard to set up (complex test fixtures, test data)
6. Not testing the integration (mocking the boundaries)
</think>

**Integration Test Quality Checklist**

**Before advising on integration tests:**

**1. What to actually integrate**
```
□ TEST REAL BOUNDARIES:
  Integration tests should test the CONNECTIONS between components:
  - Application code ↔ Database (real queries, not mocked)
  - API endpoint ↔ Service layer (real HTTP, not function call)
  - Service A ↔ Service B (real API call, not mocked)

  If everything is mocked, it's a unit test with extra setup.

□ EXTERNAL SERVICES: Mock external APIs, not internal components
  - Your database → use a REAL test database
  - Your cache → use a REAL test Redis
  - Third-party APIs (Stripe, AWS) → MOCK these
  - Other internal services → depends on test scope
```

**2. Test database management**
```
□ ISOLATED TEST DATABASE:
  Tests use a separate database instance (not production!)
  Options:
  - Docker container per test run (reliable, clean)
  - In-memory SQLite (fast, but SQL differences)
  - Dedicated test schema in development DB

□ CLEAN STATE PER TEST:
  Each test starts with a known state.
  Options:
  - Transaction rollback (wrap each test in a transaction)
  - Truncate tables before each test
  - Recreate schema before test suite

  Recommended: Transaction rollback (fastest, cleanest)

□ TEST DATA FACTORIES:
  Use factories instead of fixtures:
    user = create_user(name="Test User", role="admin")
  Not:
    INSERT INTO users VALUES (1, 'Test User', 'admin');
  Factories are readable, composable, and maintainable.
```

**3. Reliability checks**
```
□ NO TIMING DEPENDENCIES:
  BAD:  time.sleep(1); assert cache.get(key) is not None
  GOOD: Retry with timeout, or wait for explicit signal

□ NO ORDER DEPENDENCIES:
  Each test can run independently, in any order.
  If test B fails only when test A runs first → shared state bug.

□ NO EXTERNAL DEPENDENCIES:
  Tests don't fail because a third-party API is down.
  Mock external boundaries.

□ DETERMINISTIC:
  No random data in assertions (unless seeded).
  No reliance on current time (use freezegun or similar).
```

**4. Speed and organization**
```
□ FAST ENOUGH TO RUN IN CI:
  Integration test suite should complete in <5 minutes.
  If longer → parallelize or reduce scope.

□ CATEGORIZED:
  Tag tests by type so you can run subsets:
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.requires_db

□ GOOD ERROR MESSAGES:
  When an integration test fails, you should know:
  - Which integration broke
  - What the expected vs. actual behavior was
  - What state the system was in
```

**5. What integration tests should cover**
```
□ HAPPY PATHS: Core workflows end-to-end
  - Create a user → verify it's in the database
  - Submit an order → verify order and payment created
  - Upload a file → verify it's stored and retrievable

□ ERROR PATHS: Failures at integration boundaries
  - Database connection fails → graceful error response
  - External API returns 500 → appropriate handling
  - Invalid data reaches the database → constraint violation handled

□ DATA INTEGRITY:
  - Foreign key relationships maintained
  - Unique constraints enforced
  - Cascading deletes work correctly
```

**Example of a good integration test:**
```python
@pytest.mark.integration
async def test_create_order_persists_with_line_items(db_session, client):
    # Arrange: Create a product in the real database
    product = await create_product(db_session, name="Widget", price=9.99)

    # Act: Hit the real API endpoint
    response = await client.post("/orders", json={
        "items": [{"product_id": product.id, "quantity": 3}]
    })

    # Assert: Check the API response
    assert response.status_code == 201
    order = response.json()
    assert order["total"] == 29.97

    # Assert: Verify data is actually in the database
    db_order = await db_session.get(Order, order["id"])
    assert db_order is not None
    assert len(db_order.line_items) == 1
    assert db_order.line_items[0].quantity == 3
```

**The meta-principle:** Integration tests exist to catch the bugs that unit tests can't — the ones that happen at the boundaries between components. If your integration tests don't test real boundaries, they're expensive unit tests. If they test too many boundaries at once, they're flaky E2E tests in disguise. Find the middle ground: one integration boundary per test.'''
    ),
    (
        "thinking/auto-qa-testing-e2e-recommendations",
        r'''What quality checks should I apply when recommending end-to-end tests? How do I help users write E2E tests that aren't flaky and slow?''',
        r'''<think>
E2E tests are the most valuable for verifying that the entire system works from a user's perspective, but they're also the most expensive, slowest, and most flaky. The quality challenge is keeping them valuable without them becoming a maintenance burden.

**Common E2E test problems:**
1. Too many E2E tests (should be a small number of critical flows)
2. Flaky due to timing issues
3. Slow (running real browser, real network, real database)
4. Hard to debug when they fail
5. Testing UI details instead of user outcomes
6. Not running in CI because they're too unreliable
</think>

**End-to-End Test Quality Checklist**

**Before recommending E2E tests:**

**1. Scope management (most critical)**
```
□ MINIMAL COUNT: As few E2E tests as possible?
  The testing pyramid is real:
  - Many unit tests (fast, cheap)
  - Some integration tests (medium)
  - FEW E2E tests (slow, expensive)

  Target: 5-15 E2E tests for most applications.
  Each one tests a CRITICAL USER JOURNEY, not a feature.

□ CRITICAL PATHS ONLY:
  E2E tests for:
  ✓ Sign up / Sign in
  ✓ Core purchase/conversion flow
  ✓ Main user workflow (the thing users come for)
  ✓ Payment processing (if applicable)

  NOT for:
  ✗ Settings page layout
  ✗ Tooltip text
  ✗ Admin features
  ✗ Every form validation
  (Use unit/integration tests for these)

□ USER PERSPECTIVE: Tests describe user outcomes?
  GOOD: "User can sign up, create a project, and invite a team member"
  BAD: "Button click triggers API call to /api/projects"
```

**2. Reliability engineering**
```
□ NO HARD WAITS:
  BAD:  await page.waitForTimeout(3000)
  GOOD: await page.waitForSelector('[data-testid="dashboard"]')

  Wait for CONDITIONS, not TIME. Time-based waits are the
  #1 cause of flaky E2E tests.

□ STABLE SELECTORS:
  BAD:  page.click('.btn.btn-primary.mt-3')  (CSS class changes break this)
  GOOD: page.click('[data-testid="submit-order"]')  (stable test ID)

□ INDEPENDENT TEST DATA:
  Each E2E test creates its own data.
  Don't share test users between tests.
  Don't depend on seed data that might change.

  Example:
    const user = await createTestUser()  // unique per test
    await signIn(user.email, user.password)
    // ... test continues with this user

□ RETRY STRATEGY:
  Flaky tests should be retried once (not infinite retries).
  If a test fails consistently after retry → it's a real failure.
  Track flaky test rate and fix tests above 2% flake rate.
```

**3. Speed optimization**
```
□ PARALLEL EXECUTION:
  E2E tests should run in parallel (different browsers/sessions).
  Playwright supports this natively with workers.

□ API SHORTCUTS:
  Don't use the UI for test setup.
  BAD:  Navigate to sign up → fill form → submit → wait → continue
  GOOD: Call API directly to create user, set auth cookie, start test

  Only use the UI for the behavior being tested.

□ TARGETED SCOPE:
  Don't test the entire flow every time.
  If testing "add to cart," start with a logged-in user
  on the product page, not from the homepage.
```

**4. Debugging support**
```
□ SCREENSHOTS ON FAILURE:
  Automatically capture a screenshot when an E2E test fails.
  Most frameworks (Playwright, Cypress) support this natively.

□ TRACE/VIDEO ON FAILURE:
  Record a video or execution trace for failed tests.
  Playwright trace viewer shows every step with DOM snapshots.

□ CLEAR TEST NAMES:
  test("user can complete checkout with credit card")
  Not: test("e2e-3")
```

**5. CI integration**
```
□ RUNS IN CI ON EVERY PR: Not just locally?
□ USES CONTAINERS: Consistent environment?
   Docker Compose with app + database + test runner
□ TIMEOUT: Reasonable timeout (5 minutes per test, 30 total)?
□ BLOCKING: PR can't merge if E2E fails?
```

**The E2E test template:**
```javascript
test('user can sign up and create their first project', async ({ page }) => {
  // Use API shortcut for setup (not testing sign-up here)
  const user = await createTestUser({ plan: 'free' })

  // The actual behavior being tested
  await page.goto('/login')
  await page.fill('[data-testid="email"]', user.email)
  await page.fill('[data-testid="password"]', user.password)
  await page.click('[data-testid="login-button"]')

  await page.waitForSelector('[data-testid="dashboard"]')
  await page.click('[data-testid="create-project"]')
  await page.fill('[data-testid="project-name"]', 'My First Project')
  await page.click('[data-testid="submit"]')

  // Verify the outcome (user perspective)
  await expect(page.locator('[data-testid="project-title"]'))
    .toHaveText('My First Project')
})
```

**The meta-principle:** E2E tests should answer the question "can a user accomplish their goal?" Not "does every component work?" Keep them few, stable, and focused on critical paths. Every E2E test you add increases maintenance cost — make sure each one justifies its existence by protecting a high-value user flow.'''
    ),
    (
        "thinking/auto-qa-testing-test-maintenance",
        r'''What quality checks should I apply when advising on test maintenance? How do I help users keep their test suite healthy over time instead of letting it rot?''',
        r'''<think>
Test suite rot is one of the biggest problems in long-lived projects. Tests become flaky, slow, outdated, or irrelevant, and eventually the team either ignores test failures or deletes the test suite entirely.

**Common test rot symptoms:**
1. Flaky tests that are "just re-run" (nobody fixes them)
2. Tests that take 30+ minutes (people skip them)
3. Disabled tests that nobody re-enables
4. Tests testing old behavior that's changed
5. Tests that pass but don't actually verify anything meaningful
6. Massive test fixtures that nobody understands
</think>

**Test Maintenance Quality Checklist**

**For any testing strategy advice, include maintenance guidance:**

**1. Flaky test management**
```
□ FLAKY TEST POLICY: Zero tolerance or managed tolerance?

  Recommended approach:
  - Auto-retry failed tests once in CI
  - Track tests that needed retry (flaky test report)
  - Any test that flakes >2% of runs → fix within 1 week
  - Any test that flakes >5% → quarantine immediately

  Quarantine process:
  1. Move to @quarantined tag (still runs, doesn't block CI)
  2. Create a ticket to fix it
  3. Fix or delete within 2 weeks
  4. If can't fix → delete and replace with a better test

□ ROOT CAUSE ANALYSIS:
  Common flaky test causes and fixes:
  - Timing: Replace sleep() with explicit waits
  - Order: Ensure test isolation (each test cleans up)
  - Shared state: Each test creates its own data
  - External deps: Mock external services
  - Randomness: Seed random generators in tests
```

**2. Test suite speed**
```
□ SPEED BUDGET:
  Unit tests: <30 seconds total
  Integration tests: <5 minutes total
  E2E tests: <15 minutes total
  Full suite: <20 minutes total

  If over budget → profile and optimize:
  - Slow unit tests → probably doing I/O (mock it)
  - Slow integration tests → parallelize, optimize setup
  - Slow E2E tests → use API shortcuts, reduce count

□ PARALLELIZATION:
  Tests should run in parallel by default.
  Tests that can't run in parallel need isolation fixes.

□ SELECTIVE RUNNING:
  Only run tests affected by changed files:
  - pytest with --co to check collection time
  - nx affected for monorepos
  - Jest with --changedSince
```

**3. Test cleanup**
```
□ QUARTERLY REVIEW:
  Every 3 months:
  - Delete tests for removed features
  - Fix or delete all quarantined tests
  - Review coverage for new code (is it tested?)
  - Check that test names still describe actual behavior

□ DELETE DEAD TESTS:
  Signs a test should be deleted:
  - Tests code that no longer exists
  - Tests exact implementation that has changed
  - Tests trivial behavior (getter returns value)
  - Permanently disabled (@skip with no plan to fix)

  Better to have 500 meaningful tests than 2000 with 500 dead.

□ REFACTOR TEST UTILITIES:
  Test helpers and factories need maintenance too:
  - Remove helpers for deleted features
  - Update factories when models change
  - Keep test utilities as clean as production code
```

**4. Test culture**
```
□ TESTS REQUIRED FOR MERGE:
  CI must pass before merge. No exceptions.
  If CI is flaky → fix CI, don't bypass it.

□ BUG → TEST RULE:
  Every bug fix includes a regression test.
  The test should fail BEFORE the fix and pass AFTER.

□ TEST REVIEW IN CODE REVIEW:
  Review tests with the same rigor as production code.
  Check: Are the tests testing the right things?
  Check: Will these tests be maintainable?

□ NO TEST DEBT:
  Treat broken/flaky/disabled tests as bugs.
  Track them in the same system as production bugs.
  Schedule time to fix them regularly.
```

**Anti-patterns to warn about:**
```
- "Skip this test for now" (it's never re-enabled)
- "Re-run CI, it's just flaky" (flakiness is a bug)
- "We'll add tests later" (tech debt accumulates fast)
- "100% coverage required" (encourages meaningless tests)
- "@skip @todo @fixme" annotations with no associated ticket
```

**The meta-principle:** A test suite is a living system that requires ongoing maintenance. Like production code, tests need refactoring, cleanup, and care. An unmaintained test suite is worse than no test suite because it provides false confidence. Budget 10-15% of development time for test maintenance, and treat test health as a first-class metric alongside code quality.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
