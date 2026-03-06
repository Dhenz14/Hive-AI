"""Phase 4C: Self-Improvement -- Curriculum Design (Part 7)

Designing testing and QA curriculum for progressive skill development.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-testing-fundamentals",
        r'''Design a comprehensive testing/QA curriculum for developers who have never written tests. What should they learn, in what order, and how should mastery be assessed at each stage?''',
        r'''<think>
Testing curriculum needs careful sequencing:
1. Start with WHY testing matters (motivation)
2. Basic assertions and test structure (mechanics)
3. Test design principles (what to test, what not to test)
4. Advanced patterns (mocks, fixtures, parameterization)
5. Integration and end-to-end testing
6. Testing culture and CI integration

Common mistake: jumping to mocking before understanding basic assertions. Learners must understand what they are testing before learning testing techniques.
</think>

**Testing/QA Curriculum: From Zero to Production-Ready**

**Module 1: Why Testing Matters (2 hours)**

```
Learning objectives:
- Understand the cost of bugs found at different stages
- See how tests enable confident refactoring
- Recognize that untested code is untrustworthy code

Content:
1. The cost curve: bug found in development ($1) vs production ($100)
2. Live demo: refactoring code with tests vs without tests
3. Real-world example: a simple bug that caused a major outage

Exercise:
  Given a function with no tests, make a small change.
  Did you break anything? How would you know?

Assessment:
  "Explain in your own words why automated tests are valuable.
   Give one example of a bug that tests would have caught."
  Pass criteria: articulates value beyond "tests find bugs"
```

**Module 2: First Tests -- Assertions and Structure (4 hours)**

```
Prerequisites: Module 1, basic Python

Learning objectives:
- Write a test function using pytest
- Use assert statements effectively
- Understand test naming conventions
- Run tests and interpret results

Content:
1. Anatomy of a test: Arrange, Act, Assert
2. pytest discovery and conventions
3. Assertion patterns: equality, truthiness, exceptions

Exercises:
  1. Write tests for a calculator function (add, subtract, multiply, divide)
  2. Write tests that verify error handling (divide by zero)
  3. Given a buggy function, write a test that fails, then fix the function

Example:
  # Arrange
  calculator = Calculator()

  # Act
  result = calculator.add(2, 3)

  # Assert
  assert result == 5

Assessment:
  "Write tests for this function that checks if a string is a valid email.
   Cover: valid emails, invalid emails, edge cases (empty string, None)."
  Pass criteria: at least 5 test cases including edge cases
```

**Module 3: What to Test (3 hours)**

```
Prerequisites: Module 2

Learning objectives:
- Distinguish between testing behavior vs implementation
- Identify high-value test targets
- Avoid testing trivial code
- Write test descriptions that document behavior

Content:
1. Test behavior, not implementation
2. The testing priority pyramid: business logic > integration > UI
3. What NOT to test: getters/setters, framework code, constants
4. Writing test names as specifications

Exercises:
  1. Given a shopping cart class, identify which methods need tests
     and which do not. Justify each decision.
  2. Rewrite vague test names as behavior specifications:
     BAD: test_user_function
     GOOD: test_create_user_with_valid_email_returns_user_object

Assessment:
  "Here is a class with 10 methods. Rank them by testing priority
   and explain your reasoning. Write tests for the top 3."
  Pass criteria: correctly identifies high-value targets, ignores trivial code
```

**Module 4: Test Design Patterns (4 hours)**

```
Prerequisites: Module 3

Learning objectives:
- Use fixtures to set up test data
- Use parameterized tests for multiple inputs
- Understand test isolation
- Use setup and teardown properly

Content:
1. pytest fixtures: scope, sharing, teardown
2. @pytest.mark.parametrize for data-driven tests
3. Test isolation: each test is independent
4. Factory patterns for test data

Exercises:
  1. Refactor duplicate test setup into fixtures
  2. Convert 5 similar tests into 1 parameterized test
  3. Find and fix a test that depends on execution order

Assessment:
  "Given a user registration function, write a test suite using
   fixtures for database setup, parameterized tests for validation
   rules, and proper teardown."
  Pass criteria: uses fixtures correctly, tests are independent,
                 parameterization covers edge cases
```

**Module 5: Testing External Dependencies (4 hours)**

```
Prerequisites: Module 4

Learning objectives:
- Understand when and why to mock
- Use unittest.mock and pytest-mock
- Know the difference between mocks, stubs, and fakes
- Test code that depends on databases, APIs, and file systems

Content:
1. The mocking spectrum: real -> fake -> stub -> mock
2. When to mock vs when to use real dependencies
3. Mocking HTTP calls with responses library
4. Using test databases vs mocking the database

Exercises:
  1. Test a function that calls an external weather API (mock the API)
  2. Test a function that reads a config file (use tempfile)
  3. Test a function that writes to a database (use test database)
  4. Identify an over-mocked test and rewrite it with fewer mocks

Assessment:
  "Build a service that fetches user data from an API and stores it
   in a database. Write tests that mock the API but use a real test
   database. Explain why you mocked the API but not the database."
  Pass criteria: correct mock usage, understands mock vs real trade-offs
```

**Mastery Progression:**
```
Module 1: Can explain WHY tests matter
Module 2: Can WRITE basic tests
Module 3: Can CHOOSE what to test
Module 4: Can DESIGN efficient test suites
Module 5: Can HANDLE external dependencies

Final assessment: Given a small application (100-200 lines), write a
comprehensive test suite. Must include:
- At least 15 test cases
- Fixtures for setup
- At least one parameterized test
- At least one mock
- A clear testing strategy document explaining choices
```'''
    ),
    (
        "thinking/auto-curriculum-testing-advanced",
        r'''Design the advanced portion of a testing curriculum, covering integration testing, end-to-end testing, performance testing, and testing in CI/CD pipelines.''',
        r'''<think>
Advanced testing curriculum builds on fundamentals:
1. Integration testing -- testing components together
2. End-to-end testing -- testing full user workflows
3. Performance testing -- load, stress, and benchmark
4. CI/CD integration -- automated test execution
5. Testing culture -- code review, TDD, test maintenance

Key challenge: advanced testing requires infrastructure (test databases, CI servers, load testing tools). The curriculum must teach both the concepts and the tooling.
</think>

**Advanced Testing Curriculum**

**Module 6: Integration Testing (5 hours)**

```
Prerequisites: Modules 1-5

Learning objectives:
- Test API endpoints with real HTTP requests
- Test database operations with real databases
- Test service interactions
- Handle test data lifecycle (setup, use, cleanup)

Content:
1. Testing Flask/Django endpoints with test client
2. Test database strategies: transactions, fixtures, factories
3. Testing multi-component interactions
4. Contract testing between services

Exercises:
  1. Write integration tests for a REST API:
     - Test each endpoint (GET, POST, PUT, DELETE)
     - Verify response codes, response body, and database state
     - Test authentication and authorization

  2. Test database operations:
     ```python
     def test_create_order_reduces_inventory(db):
         product = create_product(db, stock=10)
         create_order(db, product_id=product.id, quantity=3)

         updated_product = get_product(db, product.id)
         assert updated_product.stock == 7
     ```

  3. Test error scenarios:
     - What happens when the database is unavailable?
     - What happens with invalid foreign keys?
     - What happens with concurrent modifications?

Assessment:
  "Given a booking API with 5 endpoints, write integration tests
   that cover happy paths, error paths, and edge cases.
   Tests must use a real test database and clean up after themselves."
  Pass criteria: all endpoints tested, proper cleanup, error cases covered
```

**Module 7: End-to-End Testing (4 hours)**

```
Prerequisites: Module 6

Learning objectives:
- Write browser-based tests with Playwright or Selenium
- Test critical user workflows end-to-end
- Handle asynchronous UI elements (waits, retries)
- Balance E2E coverage with test maintenance cost

Content:
1. When to write E2E tests (critical user journeys only)
2. Playwright basics: navigation, interaction, assertions
3. Page Object pattern for maintainable E2E tests
4. Handling flakiness in E2E tests

Exercises:
  1. Write E2E test for user registration flow:
     - Navigate to registration page
     - Fill in form fields
     - Submit and verify success message
     - Verify user can log in with new credentials

  2. Write E2E test for checkout flow:
     - Add item to cart
     - Go to checkout
     - Enter payment information
     - Verify order confirmation

  3. Refactor raw E2E tests into Page Objects:
     ```python
     # Before: fragile, hard to maintain
     page.click('#login-button')
     page.fill('#email', 'test@example.com')

     # After: maintainable Page Object
     login_page = LoginPage(page)
     login_page.login('test@example.com', 'password')
     ```

Assessment:
  "Write E2E tests for the 3 most critical user journeys in the
   application. Use Page Objects. Tests must be reliable
   (pass 10/10 runs)."
  Pass criteria: critical paths covered, Page Objects used,
                 no flaky tests
```

**Module 8: Performance and Load Testing (4 hours)**

```
Prerequisites: Module 6

Learning objectives:
- Write load tests with Locust or k6
- Identify performance bottlenecks through testing
- Set performance budgets and enforce them
- Understand performance testing types: load, stress, soak

Content:
1. Load testing vs stress testing vs soak testing
2. Locust/k6 basics: defining user scenarios
3. Interpreting results: throughput, latency percentiles, error rates
4. Performance budgets in CI

Exercises:
  1. Write a Locust test for an API:
     ```python
     from locust import HttpUser, task

     class APIUser(HttpUser):
         @task(3)
         def list_products(self):
             self.client.get('/api/products')

         @task(1)
         def create_order(self):
             self.client.post('/api/orders', json={...})
     ```

  2. Run with increasing load: 10, 50, 100, 500 users
     Record: response time p50, p95, p99, error rate
     Find: at what load does performance degrade?

  3. Set a performance budget:
     "API responses must be under 200ms at p95 with 100 concurrent users"
     Write a CI check that enforces this budget

Assessment:
  "Load test the application. Find the breaking point.
   Identify the bottleneck (database? CPU? memory?).
   Propose and implement a fix. Verify the fix with another load test."
  Pass criteria: correctly identifies breaking point and bottleneck,
                 fix improves performance measurably
```

**Module 9: CI/CD Integration (3 hours)**

```
Prerequisites: Modules 6-8

Learning objectives:
- Configure tests to run automatically in CI
- Optimize test execution time in CI
- Set up test reporting and coverage tracking
- Implement quality gates

Content:
1. GitHub Actions / GitLab CI test configuration
2. Parallelizing tests for speed
3. Test coverage thresholds
4. Quality gates: what must pass before merging

Exercises:
  1. Create a CI pipeline that:
     - Runs linting (ruff/flake8)
     - Runs unit tests
     - Runs integration tests (with test database)
     - Reports coverage
     - Fails if coverage drops below 70%

  2. Optimize the pipeline:
     - Cache dependencies
     - Run test types in parallel
     - Only run affected tests on PRs

  3. Add a quality gate:
     - All tests must pass
     - Coverage must not decrease
     - No linting errors
     - No security vulnerabilities (pip-audit)

Assessment:
  "Set up a complete CI pipeline for the project. It must run all
   test types, report coverage, and enforce quality gates.
   Build time must be under 5 minutes."
  Pass criteria: pipeline runs all checks, reports clearly,
                 blocks merging on failures
```

**Module 10: Testing Culture and Maintenance (3 hours)**

```
Prerequisites: All previous modules

Learning objectives:
- Review tests in code review
- Practice TDD (test-driven development) workflow
- Maintain and refactor test suites
- Handle flaky tests systematically

Content:
1. What to look for when reviewing tests
2. TDD workflow: red -> green -> refactor
3. When tests become a maintenance burden
4. Systematic flaky test management

Exercises:
  1. TDD exercise: build a feature test-first
     - Write a failing test
     - Write minimum code to pass
     - Refactor while keeping tests green
     - Repeat for next requirement

  2. Review a pull request with tests:
     - Are the right things being tested?
     - Are the tests testing behavior or implementation?
     - Are there missing test cases?
     - Are the test names clear?

  3. Refactor an overgrown test file:
     - Split into logical groups
     - Extract common fixtures
     - Remove redundant tests
     - Improve test names

Final assessment:
  "Using TDD, build a URL shortener service with full test coverage.
   Include unit, integration, and one E2E test. Set up CI.
   Present your testing strategy and justify your choices."
```'''
    ),
    (
        "thinking/auto-curriculum-testing-specialization",
        r'''Design specialized testing curriculum modules for security testing, accessibility testing, and API contract testing. These should be optional advanced modules for developers who want to specialize.''',
        r'''<think>
Specialized testing modules should:
1. Be self-contained (can be taken in any order after fundamentals)
2. Focus on practical skills, not theory
3. Include tools and automation
4. Connect to real-world requirements (compliance, legal)

These are "elective" modules for developers with specific interests or team needs.
</think>

**Specialized Testing Modules (Electives)**

**Elective A: Security Testing (6 hours)**

```
Prerequisites: Modules 1-6 (fundamentals + integration testing)

Learning objectives:
- Identify common security vulnerabilities through testing
- Write tests for OWASP Top 10 vulnerabilities
- Use automated security scanning tools
- Integrate security testing into CI

Unit A1: SQL Injection Testing (1.5 hours)
  Content:
  - How SQL injection works
  - Writing tests that verify parameterized queries
  - Using sqlmap for automated detection

  Exercise:
  ```python
  # Write tests that verify these inputs do NOT cause injection:
  malicious_inputs = [
      "'; DROP TABLE users; --",
      "' OR '1'='1",
      "1; UPDATE users SET role='admin' WHERE id=1",
  ]

  def test_search_is_injection_safe(client, db):
      for payload in malicious_inputs:
          response = client.get(f'/api/search?q={payload}')
          assert response.status_code in (200, 400)
          # Verify database is unchanged:
          assert db.query("SELECT count(*) FROM users").scalar() == original_count
  ```

Unit A2: Authentication and Authorization Testing (1.5 hours)
  Content:
  - Testing authentication flows (login, logout, session)
  - Testing authorization (role-based access)
  - Testing token handling (JWT expiry, rotation)

  Exercise:
  ```python
  def test_unauthorized_access_returns_401(client):
      response = client.get('/api/admin/users')
      assert response.status_code == 401

  def test_regular_user_cannot_access_admin(client, user_token):
      response = client.get('/api/admin/users',
                           headers={'Authorization': f'Bearer {user_token}'})
      assert response.status_code == 403

  def test_expired_token_returns_401(client, expired_token):
      response = client.get('/api/profile',
                           headers={'Authorization': f'Bearer {expired_token}'})
      assert response.status_code == 401
  ```

Unit A3: Input Validation Testing (1.5 hours)
  Content:
  - Boundary testing for numeric inputs
  - Testing string length limits
  - Testing file upload restrictions
  - XSS prevention testing

  Exercise:
  Write tests for a user registration endpoint that verify:
  - Email format validation (valid and invalid patterns)
  - Password strength requirements
  - Username length limits
  - HTML/script tags are rejected or sanitized

Unit A4: Automated Security Scanning in CI (1.5 hours)
  Content:
  - Dependency vulnerability scanning (pip-audit, npm audit)
  - Static analysis for security (bandit for Python)
  - Container image scanning (trivy)
  - Setting up security gates in CI

  Exercise:
  Add security scanning to CI pipeline:
  ```yaml
  security:
    steps:
      - run: pip-audit --strict         # Known CVEs in dependencies
      - run: bandit -r src/             # Python security lints
      - run: docker scout cves myapp    # Container vulnerabilities
  ```

Assessment:
  "Audit the application for security vulnerabilities. Write tests
   that verify each vulnerability is properly prevented. Add automated
   security scanning to the CI pipeline."
  Pass criteria: identifies at least 3 vulnerability categories,
                 writes preventive tests, CI integration works
```

**Elective B: Accessibility Testing (4 hours)**

```
Prerequisites: Module 7 (E2E testing)

Learning objectives:
- Understand WCAG 2.1 accessibility requirements
- Write automated accessibility tests
- Use axe-core for accessibility scanning
- Test keyboard navigation and screen reader compatibility

Unit B1: Automated Accessibility Scanning (2 hours)
  Content:
  - WCAG levels (A, AA, AAA)
  - axe-core integration with Playwright
  - Common accessibility violations

  Exercise:
  ```python
  from playwright.sync_api import sync_playwright
  from axe_playwright_python import Axe

  def test_homepage_accessibility():
      with sync_playwright() as p:
          browser = p.chromium.launch()
          page = browser.new_page()
          page.goto('http://localhost:8000')

          axe = Axe()
          results = axe.run(page)

          violations = results['violations']
          assert len(violations) == 0, (
              f"Found {len(violations)} accessibility violations:\n"
              + "\n".join(f"- {v['description']} ({v['impact']})"
                        for v in violations)
          )
  ```

Unit B2: Manual Accessibility Testing (2 hours)
  Content:
  - Keyboard-only navigation testing
  - Screen reader testing (NVDA, VoiceOver)
  - Color contrast verification
  - Form label and ARIA attribute checking

  Exercise:
  Create an accessibility test checklist and manually test
  the application's 3 most important pages:
  - Can you complete every action using only the keyboard?
  - Does every image have meaningful alt text?
  - Are form fields properly labeled?
  - Is the color contrast sufficient (4.5:1 for normal text)?

Assessment:
  "Run automated accessibility scans on every page. Fix all
   critical and serious violations. Verify that a keyboard-only
   user can complete the primary user journey."
  Pass criteria: zero critical violations, primary journey
                 works with keyboard only
```

**Elective C: API Contract Testing (4 hours)**

```
Prerequisites: Module 6 (integration testing)

Learning objectives:
- Understand consumer-driven contract testing
- Write contract tests with Pact
- Test API backward compatibility
- Prevent breaking changes automatically

Unit C1: Contract Testing Concepts (1 hour)
  Content:
  - What is a contract test?
  - Provider vs consumer contracts
  - Why integration tests are not enough for APIs

Unit C2: Writing Consumer-Driven Contracts (1.5 hours)
  Content:
  - Pact framework setup
  - Defining consumer expectations
  - Generating and sharing pact files

  Exercise:
  ```python
  # Consumer side: define what you expect from the API
  def test_get_user_contract(pact):
      pact.given('user 42 exists')
      pact.upon_receiving('a request for user 42')
      pact.with_request('GET', '/api/users/42')
      pact.will_respond_with(200, body={
          'id': 42,
          'name': Like('Alice'),  # Any string
          'email': Like('alice@example.com'),  # Any string matching email pattern
      })

      # Pact verifies the provider actually returns this shape
  ```

Unit C3: Verifying Contracts and CI Integration (1.5 hours)
  Content:
  - Provider verification against consumer contracts
  - Running contract tests in CI
  - Versioning contracts
  - Can-I-Deploy checks

  Exercise:
  Set up a CI pipeline that:
  1. Consumer generates pact file on every PR
  2. Provider verifies pact on every PR
  3. Deployment is blocked if contracts are broken
  4. New contract versions are published to a pact broker

Assessment:
  "Set up contract testing between two services. Add a breaking
   change to the provider API. Demonstrate that contract tests
   catch the break before deployment."
  Pass criteria: contract tests fail on breaking change,
                 CI blocks deployment, contract broker is configured
```'''
    ),
    (
        "thinking/auto-curriculum-testing-qa-process",
        r'''Design a curriculum module that teaches QA processes and test planning for teams, not just individual test writing. Cover test plans, bug triage, release testing, and test strategy documents.''',
        r'''<think>
QA process curriculum is different from test writing curriculum:
1. It is about team practices, not individual skills
2. It covers planning, communication, and decision-making
3. It connects testing to business goals
4. It requires collaboration and coordination skills

This is often missing from developer education -- they learn to write tests but not to plan testing strategy or coordinate QA across a team.
</think>

**QA Process and Test Planning Curriculum**

**Module: Test Planning and QA Processes (6 hours)**

**Unit 1: Writing a Test Strategy Document (1.5 hours)**

```
Learning objectives:
- Define testing goals based on business risk
- Choose appropriate testing types for the project
- Document testing scope and out-of-scope items
- Set quality metrics and acceptance criteria

Content:
A test strategy document answers:
  1. WHAT are we testing? (scope)
  2. WHY are we testing it? (risk and business impact)
  3. HOW will we test? (types, tools, approaches)
  4. WHEN will we test? (in the development lifecycle)
  5. WHO is responsible? (roles and ownership)
  6. HOW MUCH is enough? (exit criteria)

Template:
  ## Test Strategy: [Feature/Release Name]

  ### Scope
  In scope: user registration, login, password reset
  Out of scope: admin panel, third-party integrations

  ### Risk Analysis
  | Feature | Business impact if broken | Likelihood of bugs | Test priority |
  |---------|-------------------------|-------------------|--------------|
  | Payment | Critical (revenue loss) | Medium | P1 |
  | Login | Critical (users locked out) | Low | P1 |
  | Profile page | Low (cosmetic) | Low | P3 |

  ### Testing Approach
  - Unit tests: business logic, validation rules
  - Integration tests: API endpoints, database operations
  - E2E tests: payment flow, registration flow
  - Manual testing: UI/UX review, accessibility

  ### Exit Criteria
  - All P1 tests pass
  - Code coverage >= 75%
  - No open P1 or P2 bugs
  - Performance: p95 response time < 500ms

Exercise:
  Write a test strategy for a new feature: "Add subscription billing."
  Include risk analysis, testing approach, and exit criteria.

Assessment:
  Pass criteria: strategy covers all 6 questions, risk analysis
  is realistic, exit criteria are measurable.
```

**Unit 2: Bug Triage and Prioritization (1.5 hours)**

```
Learning objectives:
- Classify bugs by severity and priority
- Write effective bug reports
- Run a bug triage meeting
- Make ship/no-ship decisions based on bug inventory

Content:
Severity (how bad is it?):
  S1 - Critical: data loss, security breach, system down
  S2 - Major: feature broken, no workaround
  S3 - Minor: feature broken, workaround exists
  S4 - Cosmetic: visual glitch, typo

Priority (how urgently should we fix it?):
  P1 - Fix immediately (blocks release)
  P2 - Fix this sprint
  P3 - Fix next sprint
  P4 - Fix when convenient

Note: Severity != Priority
  An S1 bug in an unused feature might be P3.
  An S4 bug on the landing page might be P1 (brand impact).

Bug report template:
  Title: [Short description]
  Severity: S1/S2/S3/S4
  Priority: P1/P2/P3/P4
  Steps to reproduce:
    1. Go to ...
    2. Click ...
    3. Enter ...
  Expected: What should happen
  Actual: What happens instead
  Environment: Browser, OS, version
  Evidence: Screenshot or video

Exercise:
  Given 10 bug reports, assign severity and priority to each.
  Run a mock triage meeting: decide which bugs block the release.

Assessment:
  Pass criteria: severity and priority are correctly distinguished,
  triage decisions are justified based on business impact.
```

**Unit 3: Release Testing Process (1.5 hours)**

```
Learning objectives:
- Design a release testing checklist
- Perform smoke testing vs regression testing
- Make go/no-go release decisions
- Handle hotfix testing under pressure

Content:
Release testing workflow:
  1. Feature freeze (no new features after this point)
  2. Run full automated test suite
  3. Smoke test critical paths manually
  4. Regression test areas affected by changes
  5. Performance test if load-sensitive changes were made
  6. Review open bugs -- any release blockers?
  7. Go/no-go decision
  8. Deploy to staging, verify
  9. Deploy to production, monitor

Smoke test checklist example:
  [ ] Can users register?
  [ ] Can users log in?
  [ ] Can users browse products?
  [ ] Can users add items to cart?
  [ ] Can users complete checkout?
  [ ] Can users view order history?
  [ ] Do admin functions work?
  [ ] Are emails being sent?

Exercise:
  Create a release testing checklist for the application.
  Perform a mock release with:
  - 3 open bugs (decide which block release)
  - 1 flaky test (decide if it is a real issue)
  - 1 performance regression (decide severity)

Assessment:
  Pass criteria: checklist covers critical paths, go/no-go
  decision is justified, bug assessment is reasonable.
```

**Unit 4: Test Metrics and Reporting (1.5 hours)**

```
Learning objectives:
- Track meaningful test metrics
- Create test reports for stakeholders
- Identify testing gaps from metrics
- Avoid vanity metrics

Content:
Meaningful metrics:
  - Bug escape rate: bugs found in production / total bugs
  - Time to detect: average time from bug introduction to test failure
  - Test execution time: how long does the full suite take?
  - Flaky test rate: % of tests that are inconsistent
  - Coverage delta: did coverage increase or decrease this sprint?

Vanity metrics (avoid):
  - Total number of tests (more tests != better quality)
  - Total code coverage (high coverage != well tested)
  - Number of bugs found (finding bugs is not the goal; preventing them is)

Reporting template:
  ## Test Report: Sprint 14

  ### Summary
  - Tests run: 342 (327 passed, 12 skipped, 3 failed)
  - Coverage: 78% (+2% from last sprint)
  - New bugs found: 5 (3 fixed, 2 triaged for next sprint)
  - Production bugs this sprint: 1 (P3, fixed in 2 hours)

  ### Risk Areas
  - Payment module: coverage dropped 5% due to new refund feature
  - Search: no integration tests for new filter options

  ### Recommendations
  - Add integration tests for refund flow
  - Investigate flaky test in test_user_session (failed 2/10 runs)

Exercise:
  Generate a test report from actual test run data.
  Identify the highest-risk area and propose additional testing.

Assessment:
  Pass criteria: report uses meaningful metrics, risk assessment
  is accurate, recommendations are actionable.
```'''
    ),
    (
        "thinking/auto-curriculum-testing-practical-project",
        r'''Design a capstone project for the testing/QA curriculum that integrates all skills learned across the modules. The project should simulate real-world testing challenges.''',
        r'''<think>
A capstone project should:
1. Integrate skills from all modules (unit, integration, E2E, CI)
2. Simulate realistic constraints (time pressure, incomplete requirements)
3. Require decision-making (what to test, what to skip)
4. Produce artifacts that demonstrate mastery (test code, strategy doc, report)

The project should be substantial enough to be meaningful but completable in 1-2 weeks.
</think>

**Capstone Project: Test an E-Commerce Application**

**Project Overview**

```
You are joining a team that has built an e-commerce application with:
- User registration and authentication
- Product catalog with search and filters
- Shopping cart and checkout
- Order history and tracking
- Admin panel for product management

The application has ZERO tests. Your job is to create a comprehensive
test strategy and implement it. You have 2 weeks.

The application intentionally contains 5 hidden bugs that your tests
should discover.
```

**Week 1: Strategy and Unit/Integration Tests**

```
Day 1-2: Analysis and Strategy
  Deliverable: Test Strategy Document

  Tasks:
  1. Review the codebase and identify:
     - Business-critical paths (payment, authentication)
     - Complex logic (pricing rules, discount calculations)
     - Integration points (database, external APIs)
     - Areas with high bug risk (complex conditions, edge cases)

  2. Write a test strategy document covering:
     - Scope and priorities (what to test first)
     - Testing types and tools
     - Risk analysis with priority matrix
     - Exit criteria for "ready to ship"
     - Timeline for test implementation

Day 3-4: Unit Tests
  Deliverable: Unit test suite for business logic

  Tasks:
  1. Write unit tests for:
     - Price calculation (with taxes, discounts, bulk pricing)
     - Input validation (user registration, product creation)
     - Business rules (minimum order amount, stock checks)
     - Error handling (what happens with invalid data?)

  2. Use:
     - pytest fixtures for test data
     - Parameterized tests for validation rules
     - Proper assertion messages

  Target: 30+ unit tests covering core business logic

Day 5: Integration Tests
  Deliverable: Integration test suite for API endpoints

  Tasks:
  1. Write integration tests for:
     - All REST API endpoints (CRUD operations)
     - Authentication flow (register, login, logout, token refresh)
     - Authorization (admin vs regular user access)
     - Database operations (order creation, inventory updates)

  2. Use:
     - Test database with fixtures
     - HTTP test client
     - Transaction rollback for cleanup

  Target: 20+ integration tests covering all endpoints
```

**Week 2: E2E Tests, CI, and Reporting**

```
Day 6-7: End-to-End Tests
  Deliverable: E2E test suite for critical user journeys

  Tasks:
  1. Write E2E tests for:
     - User registration and first login
     - Product search and filtering
     - Add to cart and checkout flow
     - Order history viewing

  2. Use:
     - Playwright with Page Objects
     - Reliable selectors (data-testid attributes)
     - Proper waits (not sleep)

  Target: 5-8 E2E tests covering critical paths

Day 8: Performance Testing
  Deliverable: Performance test results and analysis

  Tasks:
  1. Write load tests for key endpoints
  2. Run with increasing concurrency (10, 50, 100 users)
  3. Identify the performance bottleneck
  4. Recommend a fix

Day 9: CI/CD Pipeline
  Deliverable: Working CI pipeline

  Tasks:
  1. Create GitHub Actions workflow that:
     - Runs linting
     - Runs unit tests
     - Runs integration tests (with test database)
     - Reports coverage
     - Fails if coverage < 70%
     - Runs security scan (pip-audit)

  2. Optimize for speed:
     - Cache dependencies
     - Parallelize where possible
     - Target < 5 minute build time

Day 10: Bug Report and Final Presentation
  Deliverable: Bug reports + test report + presentation

  Tasks:
  1. Document all bugs found with proper bug reports
  2. Generate a comprehensive test report:
     - Coverage statistics
     - Test pass/fail summary
     - Risk areas still untested
     - Performance results

  3. Present to the team:
     - What was your testing strategy and why?
     - What bugs did you find?
     - What areas are still at risk?
     - What would you do with another week?
```

**Grading Rubric**

```
Test Strategy Document (20%)
  - Risk analysis is accurate and prioritized
  - Testing approach matches the application type
  - Exit criteria are measurable

Unit Tests (20%)
  - Business logic is thoroughly tested
  - Edge cases are covered
  - Tests are well-organized with clear names
  - Fixtures and parameterization are used appropriately

Integration Tests (20%)
  - All API endpoints are tested
  - Both happy and error paths are covered
  - Database state is verified
  - Authentication/authorization is tested

E2E and Performance Tests (15%)
  - Critical user journeys are covered
  - Page Objects are used
  - Tests are reliable (no flakiness)
  - Performance bottleneck is identified

CI/CD Pipeline (10%)
  - Pipeline runs all test types
  - Coverage is reported
  - Quality gates are enforced
  - Build time is reasonable

Bug Discovery (15%)
  - Bugs are found through testing (not manual exploration)
  - Bug reports are well-written with reproduction steps
  - Severity and priority are correctly assigned

Bonus points:
  - Finding all 5 hidden bugs
  - Security testing
  - Accessibility testing
  - Contract testing
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
