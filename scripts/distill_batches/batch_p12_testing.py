"""Batch P12 -- Advanced Testing Strategies: property-based testing (Hypothesis deep dive),
contract testing (Pact), mutation testing, load testing (Locust/k6), visual regression testing.
Each pair targets >0.80 quality score with 1200+ word responses."""

PAIRS = [
    (
        "testing/property-based-hypothesis",
        "Explain advanced property-based testing with Hypothesis including custom composite strategies, stateful testing with RuleBasedStateMachine, shrinking internals, integration with pytest fixtures and markers, and strategies for testing complex domain objects with invariants.",
        '''# Advanced Property-Based Testing with Hypothesis: Custom Strategies, Stateful Testing, and Shrinking

## The Paradigm Shift from Example-Based to Property-Based Testing

Property-based testing fundamentally changes how we reason about correctness. Instead of manually selecting a handful of input/output examples, you declare **universal properties** that must hold across the entire input domain and let the framework generate thousands of test cases. This matters **because** human intuition systematically fails at anticipating edge cases -- empty collections, boundary integers, Unicode surrogates, and degenerate geometric configurations all lurk in the unexplored regions of your input space.

**Common mistake**: developers write property-based tests that are too weak. Testing `len(sort(xs)) == len(xs)` is a valid property but insufficient alone. You need a **constellation of properties** that, taken together, fully characterize correct behavior. **Therefore**, always ask: "If an implementation satisfies all my properties, could it still be wrong?"

## Custom Composite Strategies for Domain Objects

Hypothesis strategies compose like building blocks. The `@st.composite` decorator lets you build **domain-aware generators** that produce valid, internally consistent objects.

```python
from hypothesis import given, settings, assume, example, Phase
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine, rule, precondition,
    invariant, initialize, Bundle, consumes, multiple'''
    ),
    (
        "testing/contract-testing-pact",
        "Describe consumer-driven contract testing with Pact including provider verification workflows, contract broker configuration, bi-directional contract testing patterns, versioning strategies, and integrating Pact into CI/CD pipelines for microservices architectures.",
        '''## Why Contract Testing Exists

In a microservice architecture, services communicate over HTTP, gRPC, or message queues. Traditional integration tests spin up the entire dependency graph to verify compatibility, but this approach has a fatal flaw: **it does not scale**. With 20 services, each with 5 dependencies, you need complex orchestration just to run a single test. Contract testing solves this by **decoupling verification** -- each service tests against a lightweight contract rather than a live dependency.

**Common mistake**: teams rely solely on end-to-end tests for integration assurance. However, these tests are slow, flaky, and provide feedback far too late in the development cycle. **Because** contract tests run independently against each service, they execute in seconds and pinpoint exactly which service broke compatibility.

The key insight behind **consumer-driven** contracts is that the consumer defines what it needs from the provider. This inverts the traditional API-first approach and ensures providers never accidentally break the specific interactions their consumers depend on.

## Consumer-Side Contract Definition

The consumer writes a test that declares its expectations. Pact records these expectations into a contract file (a "pact") that the provider must satisfy.

```python
import pytest
import requests
from pact import Consumer, Provider, Term, Like, EachLike, Format
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path


PACT_DIR = Path(__file__).parent / "pacts"


@dataclass
class UserProfile:
    # Domain model on the consumer side
    user_id: int
    username: str
    email: str
    roles: List[str]


class UserServiceClient:
    # HTTP client that the consumer uses to call the provider
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'''
    ),
    (
        "X-Api-Version",
        "}) def get_user(self, user_id: int) -> Optional[UserProfile]: resp = self.session.get(f'{self.base_url}/api/users/{user_id}') if resp.status_code == 404: return None resp.raise_for_status() data = resp.json() return UserProfile( user_id=data['id'] username=data['username'] email=data['email'] roles=data.get('roles', []) ) def list_users(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]: resp = self.session.get( f'{self.base_url}/api/users' params={'page': page, 'per_page': per_page} ) resp.raise_for_status() return resp.json() def create_user(self, username: str, email: str) -> UserProfile: resp = self.session.post( f'{self.base_url}/api/users' json={'username': username, 'email': email} ) resp.raise_for_status() data = resp.json() return UserProfile( user_id=data['id'] username=data['username'] email=data['email'] roles=data.get('roles', []) )",
        '''@pytest.fixture(scope="session")
def pact():
    pact = Consumer("OrderService").has_pact_with(
        Provider("UserService"),
        pact_dir=str(PACT_DIR),
        log_dir=str(PACT_DIR / "logs"),'''
    ),
    (
        "roles",
        "} ) ) with pact: user = user_client.create_user('newuser', 'new@example.com') assert user.username == 'newuser",
        '''## Provider Verification

The provider side downloads the contract and verifies that its real API satisfies every interaction. The **provider states** setup hook configures test data for each `given()` clause.

```python
from pact import Verifier
from typing import Callable, Dict
import subprocess
import os


def run_provider_verification(
    provider_base_url: str,
    broker_url: str,
    provider_name: str = "UserService",
    publish_results: bool = False,
) -> bool:
    # Provider states setup endpoint must be implemented in the provider
    # It receives {"consumer": "OrderService", "state": "user 42 exists"}
    # and sets up the appropriate test data
    verifier = Verifier(
        provider=provider_name,
        provider_base_url=provider_base_url,'''
    ),
    (
        "testing/mutation-testing",
        "Explain mutation testing concepts and tooling including mutmut and cosmic-ray for Python, mutation operators and their categories, detecting equivalent mutants, measuring test suite quality with mutation scores, and strategies for efficiently integrating mutation testing into development workflows.",
        '''## What Mutation Testing Reveals That Coverage Cannot

Code coverage tells you which lines your tests **execute**, but it says nothing about whether your tests **detect** faults in those lines. A test that calls a function but never asserts anything achieves 100% coverage while catching zero bugs. Mutation testing fills this gap by systematically introducing small faults (**mutants**) into your code and checking whether your test suite catches them.

The process works like this: the tool creates hundreds of slightly modified copies of your code -- changing `+` to `-`, `>` to `>=`, `True` to `False`, removing a function call -- and runs your tests against each mutant. If the tests pass with a mutant, that mutant **survived**, meaning your tests cannot distinguish the faulty code from the original. A high **mutation score** (killed mutants / total mutants) indicates a robust test suite. **Because** mutation testing directly measures fault-detection capability, it is the most rigorous metric of test quality available.

**Common mistake**: pursuing 100% code coverage and declaring the test suite "complete." However, coverage is a necessary but insufficient condition for quality. Mutation testing reveals the gap between "lines executed" and "behavior verified."

## Mutation Operators and Their Categories

Mutation operators are the transformations applied to your source code. They fall into several categories, each targeting a different class of potential bugs.

```python
# Illustration of common mutation operator categories
# Each comment shows original -> mutant transformation

# --- Arithmetic Operator Replacement (AOR) ---
# original: total = price + tax
# mutant:   total = price - tax
# mutant:   total = price * tax

# --- Relational Operator Replacement (ROR) ---
# original: if age >= 18:
# mutant:   if age > 18:      # off-by-one boundary
# mutant:   if age <= 18:     # inverted condition
# mutant:   if age == 18:     # equality instead of threshold

# --- Logical Connector Replacement (LCR) ---
# original: if is_admin and is_active:
# mutant:   if is_admin or is_active:

# --- Statement Deletion (SDL) ---
# original: cache.invalidate(key)
# mutant:   pass  # statement removed entirely

# --- Constant Replacement (CR) ---
# original: MAX_RETRIES = 3
# mutant:   MAX_RETRIES = 0
# mutant:   MAX_RETRIES = 4

# --- Return Value Modification (RVM) ---
# original: return result
# mutant:   return None
# mutant:   return not result  # for booleans

from typing import List, Optional


def calculate_discount(
    total: float, customer_tier: str, coupon_code: Optional[str] = None
) -> float:
    # A function with multiple mutation points
    base_discount = 0.0

    if customer_tier == "gold":
        base_discount = 0.15  # CR mutant: 0.0, 0.16, 1.15
    elif customer_tier == "silver":
        base_discount = 0.10  # CR mutant: 0.0, 0.11
    # SDL mutant: remove entire elif block

    if coupon_code is not None and len(coupon_code) > 0:  # LCR mutant: or
        base_discount += 0.05  # AOR mutant: -=, *=

    final = total * (1 - base_discount)  # AOR mutant: +, /
    return max(final, 0.0)  # ROR mutant: min(); CR mutant: max(final, 1.0)
```

## Using mutmut for Python Projects

**mutmut** is the most popular mutation testing tool for Python. It modifies your source AST, runs your test suite for each mutation, and reports which mutants survived.

```python
# pyproject.toml configuration for mutmut
# [tool.mutmut]
# paths_to_mutate = "src/"
# tests_dir = "tests/"
# runner = "python -m pytest -x -q --tb=no"
# dict_synonyms = "Struct, NamedStruct"

# Running mutmut from the command line:
# mutmut run                     -- run all mutations
# mutmut run --paths-to-mutate=src/discount.py  -- target specific file
# mutmut results                 -- show summary
# mutmut show 42                 -- show specific surviving mutant
# mutmut html                    -- generate HTML report

# Programmatic integration for CI pipelines
import subprocess
import json
import sys
from pathlib import Path
from dataclasses import dataclass


@dataclass
class MutationReport:
    # Structured mutation testing results
    total_mutants: int
    killed: int
    survived: int
    timeout: int
    suspicious: int

    @property
    def mutation_score(self) -> float:
        if self.total_mutants == 0:
            return 1.0
        return self.killed / self.total_mutants

    @property
    def quality_verdict(self) -> str:
        score = self.mutation_score
        if score >= 0.90:
            return "excellent"
        elif score >= 0.75:
            return "good"
        elif score >= 0.60:
            return "needs improvement"
        return "inadequate"


def run_mutation_testing(
    source_path: str,
    min_score: float = 0.80,
    timeout_multiplier: int = 3,
) -> MutationReport:
    # Run mutmut and parse results programmatically
    cmd = [
        sys.executable, "-m", "mutmut", "run",'''
    ),
    (
        "--no-progress",
        "] result = subprocess.run(cmd, capture_output=True, text=True)",
        '''jit_result = subprocess.run(
        [sys.executable, "-m", "mutmut", "junitxml"],
        capture_output=True, text=True,'''
    ),
    (
        "testing/load-testing",
        "Describe advanced load testing patterns using Locust and k6 including realistic user simulation with weighted scenarios, distributed load generation across multiple workers, analyzing results with percentile metrics, setting performance budgets, and correlating load test results with application metrics for capacity planning.",
        '''## Why Load Testing Requires Scientific Rigor

Load testing is not simply "hit the server with many requests and see what happens." Effective load testing models **real user behavior** -- think times, session patterns, geographic distribution, and weighted action frequencies. Without this rigor, you optimize for a traffic pattern that does not exist in production. **Because** production traffic has heavy tails, bursty arrivals, and correlated user behaviors, synthetic benchmarks with uniform request rates produce dangerously misleading results.

**Common mistake**: running a load test with a single endpoint at maximum request rate and concluding "the system handles 10,000 RPS." However, real users hit dozens of endpoints in complex sequences, maintain session state, and exhibit thundering-herd patterns after outages. **Therefore**, always model your load tests on production traffic analysis.

## Locust: Python-Native Load Testing with Realistic User Simulation

Locust models users as coroutines, each executing a sequence of actions with waits between them. This naturally produces realistic traffic patterns.

```python
from locust import HttpUser, task, between, tag, events, TaskSet
from locust.runners import MasterRunner, WorkerRunner
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import random
import json
import time
import logging

logger = logging.getLogger(__name__)


# Weighted user types model different audience segments
class BrowsingUser(HttpUser):
    # 70% of traffic: users who browse but rarely purchase
    weight = 70
    wait_time = between(2, 8)  # realistic think time between actions
    host = "https://api.example.com"

    def on_start(self) -> None:
        # Session initialization -- runs once per simulated user
        self.product_ids: List[int] = []
        self.session_id = f"load-test-{random.randint(100000, 999999)}"
        self.client.headers.update({'''
    ),
    (
        "Accept",
        "}) @task(10)  # relative weight: most common action def browse_catalog(self) -> None: page = random.randint(1, 50) with self.client.get( f'/api/products?page={page}&per_page=20' name='/api/products?page=[n]',  # aggregate in reports catch_response=True ) as response: if response.status_code == 200: data = response.json()",
        '''self.product_ids = [p["id"] for p in data.get("products", [])]
                if not self.product_ids:
                    response.failure("Empty product list")
            else:
                response.failure(f"Status {response.status_code}")

    @task(5)
    def view_product_detail(self) -> None:
        if not self.product_ids:
            return  # skip if no products cached
        product_id = random.choice(self.product_ids)
        self.client.get(
            f"/api/products/{product_id}",
            name="/api/products/[id]",'''
    ),
    (
        "/api/checkout",
        "json={'payment_method': 'test_card'} catch_response=True ) as response: if response.status_code in (200, 201): response.success() elif response.status_code == 422: response.success()  # empty cart is expected sometimes else: response.failure(f'Checkout failed: {response.status_code}') class AdminUser(HttpUser):",
        '''weight = 5
    wait_time = between(5, 15)
    host = "https://api.example.com"

    @task
    def generate_report(self) -> None:
        self.client.get('''
    ),
    (
        "/api/admin/reports/daily-summary",
        "timeout=30,  # admin reports are slow )",
        '''## k6: JavaScript-Based Load Testing with Performance Budgets

k6 offers powerful threshold-based performance budgets that **fail the test** if SLOs are breached. This is critical for CI integration **because** it provides a binary pass/fail signal.

```javascript
// k6 load test with performance budgets and stages
// Run: k6 run --out json=results.json load_test.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics for business-level tracking
const checkoutSuccess = new Rate('checkout_success_rate');
const searchLatency = new Trend('search_p95_latency');
const errorCount = new Counter('business_errors');

export const options = {
    // Staged load profile: ramp up, sustain, spike, recover
    stages: [
        { duration: '2m', target: 100 },   // ramp up
        { duration: '5m', target: 100 },   // sustained load
        { duration: '1m', target: 500 },   // spike
        { duration: '2m', target: 100 },   // recovery
        { duration: '1m', target: 0 },     // ramp down
    ],

    // Performance budgets -- test FAILS if any threshold is breached
    thresholds: {
        http_req_duration: [
            'p(95) < 500',    // 95th percentile under 500ms
            'p(99) < 2000',   // 99th percentile under 2 seconds
        ],
        http_req_failed: ['rate < 0.01'],  // less than 1% error rate
        checkout_success_rate: ['rate > 0.95'],  // 95%+ checkout success
        search_p95_latency: ['p(95) < 300'],  // search must be fast
    },
};

export default function () {
    // Weighted scenario selection
    const rand = Math.random();
    if (rand < 0.70) {
        browseFlow();
    } else if (rand < 0.95) {
        purchaseFlow();
    } else {
        searchFlow();
    }
}

function browseFlow() {
    group('Browse Flow', function () {
        const catalogRes = http.get(
            'https://api.example.com/api/products?page=1',
            { tags: { flow: 'browse' } }
        );
        check(catalogRes, {
            'catalog status 200': (r) => r.status === 200,
            'catalog has products': (r) => {
                const body = JSON.parse(r.body);
                return body.products && body.products.length > 0;
            },
        });
        sleep(Math.random() * 3 + 1);  // think time: 1-4 seconds
    });
}

function purchaseFlow() {
    group('Purchase Flow', function () {
        const checkoutRes = http.post(
            'https://api.example.com/api/checkout',
            JSON.stringify({ payment_method: 'test' }),
            { headers: { 'Content-Type': 'application/json' } }
        );
        const success = checkoutRes.status === 200 || checkoutRes.status === 201;
        checkoutSuccess.add(success);
        if (!success) {
            errorCount.add(1);
        }
        sleep(Math.random() * 2 + 1);
    });
}

function searchFlow() {
    group('Search Flow', function () {
        const start = Date.now();
        const searchRes = http.get(
            'https://api.example.com/api/search?q=laptop'
        );
        searchLatency.add(Date.now() - start);
        check(searchRes, {
            'search status 200': (r) => r.status === 200,
        });
        sleep(Math.random() * 2 + 2);
    });
}
```

## Distributed Load Generation

For generating serious load (10,000+ concurrent users), a single machine is insufficient. **Best practice**: use Locust's built-in master/worker architecture or k6's cloud execution.

With Locust, the master coordinates the test while workers generate actual traffic. Workers connect to the master via a message queue. **Because** each worker runs independently, you can scale horizontally by adding machines. **However**, the trade-off is that you need to ensure all workers have synchronized test scripts and configurations. Use container orchestration (Kubernetes or Docker Compose) for reproducible distributed setups.

## Result Analysis and Capacity Planning

Raw averages are **misleading** for load test analysis. A system with 100ms average response time might have a 5-second p99 -- meaning 1% of users experience unacceptable latency. **Therefore**, always analyze percentiles: p50 (median), p90, p95, p99, and p99.9. Plot these over time to identify the **saturation point** -- the load level where latency curves go exponential.

**Pitfall**: testing only below the expected peak. **Best practice**: test at 2x your expected peak load to find the breaking point and understand degradation characteristics. A system that degrades gracefully (shedding load, returning cached responses) is far better than one that crashes catastrophically.

Correlate load test metrics with application-level metrics: CPU utilization, memory pressure, database connection pool saturation, queue depths, and garbage collection pauses. This correlation reveals **which resource becomes the bottleneck** at each load level, enabling targeted optimization.

## Summary and Key Takeaways

- **Model real users**, not synthetic traffic; use weighted user types, think times, and session sequences derived from production traffic analysis
- **Performance budgets** (k6 thresholds, Locust custom checks) provide binary pass/fail signals for CI integration; **therefore** define SLOs as code
- **Best practice**: analyze percentiles (p95, p99), not averages; averages hide tail latency that affects your worst user experiences
- **Distributed load generation** scales horizontally with master/worker architectures; use Kubernetes for reproducible multi-node setups
- **Common mistake**: running load tests against a staging environment with different hardware than production; results will not transfer
- **Trade-off**: longer test durations reveal memory leaks and connection pool exhaustion but consume more CI resources; run soak tests (4-12 hours) nightly and short spike tests on PRs
- **Pitfall**: testing with unrealistic data distributions; **because** caching layers perform differently with uniform versus Zipfian access patterns, seed your test data to match production distributions
- **Capacity planning** correlates load test results with resource utilization metrics to identify bottleneck resources and predict scaling requirements
- **Best practice**: maintain a performance regression baseline; compare every load test against the previous release to catch degradation early
""",'''
    ),
    (
        "testing/visual-regression",
        "Explain visual regression testing including screenshot comparison techniques, Playwright visual testing APIs, perceptual diffing algorithms, component isolation strategies for deterministic snapshots, handling dynamic content, and integrating visual tests into CI pipelines with approval workflows.",
        '''## Why Visual Regression Testing Matters

Functional tests verify that buttons click and APIs return correct data, but they are completely blind to **how things look**. A CSS change that shifts your checkout button off-screen, a font-weight regression that makes text unreadable, or a z-index conflict that hides critical UI elements -- none of these are caught by functional tests. Visual regression testing fills this gap by capturing screenshots and comparing them against approved baselines.

**Common mistake**: assuming that component unit tests with render snapshots (React Testing Library's `toMatchSnapshot()`) catch visual regressions. However, DOM snapshots verify structure, not rendering. A `<div>` with correct HTML can render completely wrong due to CSS specificity conflicts, inherited styles, or viewport-dependent layouts. **Because** visual bugs are rendering bugs, only pixel-level or perceptual comparison can detect them.

## Playwright Visual Testing APIs

Playwright provides first-class screenshot comparison with built-in diffing. The `toHaveScreenshot()` assertion captures a screenshot, compares it against a baseline stored in your repository, and fails the test if the diff exceeds a configurable threshold.

```python
import pytest
from playwright.sync_api import Page, Browser, BrowserContext, expect
from typing import Generator, Optional
from pathlib import Path
import json


# Pytest fixtures for deterministic browser configuration
@pytest.fixture(scope="session")
def browser_context_args() -> dict:
    # Fixed viewport and locale for reproducible screenshots
    return {'''
    ),
    (
        "reduced_motion",
        "} @pytest.fixture def authenticated_page(page: Page, base_url: str) -> Page:",
        '''page.goto(f"{base_url}/login")
    page.fill("[data-testid='email-input']", "visual-test@example.com")
    page.fill("[data-testid='password-input']", "test_password")
    page.click("[data-testid='login-button']")
    page.wait_for_url("**/dashboard")
    return page


class TestDashboardVisuals:
    # Visual regression tests for the dashboard page

    def test_dashboard_full_page(self, authenticated_page: Page) -> None:
        page = authenticated_page
        # Wait for all data to load before capturing
        page.wait_for_load_state("networkidle")
        # Hide dynamic elements that change between runs
        page.evaluate("""() => {
            // Hide timestamps and dynamic counters
            document.querySelectorAll('[data-testid="timestamp"]')
                .forEach(el => el.style.visibility = 'hidden');
            document.querySelectorAll('[data-testid="live-counter"]')
                .forEach(el => el.textContent = '###');
        }""")
        expect(page).to_have_screenshot(
            "dashboard-full.png",
            full_page=True,
            max_diff_pixels=100,  # allow minor anti-aliasing differences'''
    ),
    (
        "retention-days",
        "} } ] } }",
        '''When visual tests fail in CI, the diff images are uploaded as build artifacts. Reviewers inspect the diffs and either approve the changes (updating baselines by running `pytest --update-snapshots` and committing) or flag them as regressions. **However**, the trade-off is that this adds a manual step to the review process. Teams must decide whether visual test failures block merging or are advisory.

## Summary and Key Takeaways

- **Visual regression testing** catches rendering bugs that functional tests and DOM snapshots completely miss; CSS conflicts, layout shifts, and theme regressions all require pixel-level verification
- **Playwright's `toHaveScreenshot()`** provides built-in screenshot comparison with configurable thresholds, masking, and animation control
- **Perceptual diffing** (SSIM-based) reduces false positives compared to pixel-by-pixel comparison, **because** it accounts for how humans perceive visual differences rather than measuring raw pixel values
- **Best practice**: isolate components with fixed data, disabled animations, frozen timestamps, and loaded fonts before capturing screenshots
- **Common mistake**: running visual tests across different operating systems without acknowledging that font rendering and anti-aliasing differ; **therefore** always run visual tests in a Docker container with a fixed OS and font configuration
- **CI integration** requires an artifact upload pipeline for diff images and an approval workflow for updating baselines; use containerized browsers for deterministic rendering across environments
- **Trade-off**: visual tests are slow (browser startup, rendering, screenshot capture) and produce large baseline files; limit them to critical user journeys and key components rather than exhaustive page coverage
- **Pitfall**: testing too many viewport sizes multiplies test count and maintenance burden; **therefore** focus on your three most common breakpoints: mobile (375px), tablet (768px), and desktop (1280px)
- **Best practice**: version baseline screenshots in your repository alongside the code; this ensures that visual changes are explicitly reviewed and approved in pull requests
""",'''
    ),
]
