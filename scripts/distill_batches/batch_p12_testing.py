"""
Batch P12 -- Advanced Testing Strategies: property-based testing (Hypothesis deep dive),
contract testing (Pact), mutation testing, load testing (Locust/k6), visual regression testing.
Each pair targets >0.80 quality score with 1200+ word responses.
"""

PAIRS = [
    # --- 1. Property-Based Testing with Hypothesis ---
    (
        "testing/property-based-hypothesis",
        r"""Explain advanced property-based testing with Hypothesis including custom composite strategies, stateful testing with RuleBasedStateMachine, shrinking internals, integration with pytest fixtures and markers, and strategies for testing complex domain objects with invariants.""",
        r"""
# Advanced Property-Based Testing with Hypothesis: Custom Strategies, Stateful Testing, and Shrinking

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
    invariant, initialize, Bundle, consumes, multiple
)
from typing import List, Optional, Dict, Tuple, Set, FrozenSet
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math


@dataclass(frozen=True)
class Money:
    # Immutable value object for monetary amounts
    amount: Decimal
    currency: str

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)


@dataclass
class OrderLine:
    # Single line item in an order
    product_id: str
    quantity: int
    unit_price: Money


@dataclass
class Order:
    # Aggregate root with business invariants
    order_id: str
    lines: List[OrderLine] = field(default_factory=list)
    status: str = "draft"

    @property
    def total(self) -> Money:
        if not self.lines:
            return Money(Decimal("0.00"), "USD")
        result = Money(Decimal("0.00"), self.lines[0].unit_price.currency)
        for line in self.lines:
            line_total = Money(
                line.unit_price.amount * line.quantity,
                line.unit_price.currency,
            )
            result = result + line_total
        return result

    def add_line(self, line: OrderLine) -> None:
        if self.status != "draft":
            raise ValueError("Cannot modify a confirmed order")
        self.lines.append(line)

    def confirm(self) -> None:
        if not self.lines:
            raise ValueError("Cannot confirm empty order")
        self.status = "confirmed"


# Composite strategy: builds Money with constrained amounts
@st.composite
def money_strategy(
    draw: st.DrawFn,
    currency: str = "USD",
    min_amount: str = "0.01",
    max_amount: str = "99999.99",
) -> Money:
    # Generate monetary values with exactly two decimal places
    cents = draw(st.integers(
        min_value=int(Decimal(min_amount) * 100),
        max_value=int(Decimal(max_amount) * 100),
    ))
    return Money(amount=Decimal(cents) / Decimal(100), currency=currency)


# Composite strategy: builds internally consistent OrderLine objects
@st.composite
def order_line_strategy(draw: st.DrawFn, currency: str = "USD") -> OrderLine:
    product_id = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=3, max_size=20,
    ))
    quantity = draw(st.integers(min_value=1, max_value=1000))
    unit_price = draw(money_strategy(currency=currency))
    return OrderLine(product_id=product_id, quantity=quantity, unit_price=unit_price)


# Property: order total equals sum of line totals
@given(lines=st.lists(order_line_strategy(), min_size=1, max_size=20))
@settings(max_examples=500, deadline=None)
def test_order_total_is_sum_of_line_totals(lines: List[OrderLine]) -> None:
    order = Order(order_id="test-001")
    for line in lines:
        order.add_line(line)
    expected = sum(
        (line.unit_price.amount * line.quantity for line in lines),
        Decimal("0.00"),
    )
    assert order.total.amount == expected


# Property: confirming then modifying raises error
@given(line=order_line_strategy())
def test_confirmed_order_is_immutable(line: OrderLine) -> None:
    order = Order(order_id="test-002")
    order.add_line(line)
    order.confirm()
    try:
        order.add_line(line)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # expected -- confirmed orders reject modifications
```

## Stateful Testing with RuleBasedStateMachine

While `@given` tests single operations, **stateful testing** explores sequences of operations. Hypothesis generates chains of method calls and checks invariants after each step. This is extraordinarily powerful **because** most bugs hide in specific *sequences* of operations, not individual calls.

```python
# Stateful test for a simplified in-memory key-value cache with TTL
import time
from collections import OrderedDict


class LRUCache:
    # Least-recently-used cache with maximum capacity
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._store: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> Optional[str]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: str, value: str) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def size(self) -> int:
        return len(self._store)


class LRUCacheStateMachine(RuleBasedStateMachine):
    # Model-based test: compare LRU cache against a simple dict reference model

    keys = Bundle("keys")

    def __init__(self) -> None:
        super().__init__()
        self.capacity = 5
        self.cache = LRUCache(self.capacity)
        self.model: Dict[str, str] = {}  # reference model
        self.access_order: List[str] = []  # track LRU ordering

    @rule(target=keys, key=st.text(min_size=1, max_size=10))
    def add_key(self, key: str) -> str:
        return key

    @rule(key=keys, value=st.text(min_size=1, max_size=50))
    def put_item(self, key: str, value: str) -> None:
        self.cache.put(key, value)
        self.model[key] = value
        # Track access order for LRU eviction modeling
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        # Evict LRU items from model if over capacity
        while len(self.model) > self.capacity:
            evicted = self.access_order.pop(0)
            del self.model[evicted]

    @rule(key=keys)
    def get_item(self, key: str) -> None:
        result = self.cache.get(key)
        if key in self.model:
            assert result == self.model[key], (
                f"Cache returned {result!r} but model has {self.model[key]!r}"
            )
            # Update access order in model
            self.access_order.remove(key)
            self.access_order.append(key)
        else:
            assert result is None

    @rule(key=keys)
    def delete_item(self, key: str) -> None:
        existed = self.cache.delete(key)
        if key in self.model:
            assert existed is True
            del self.model[key]
            self.access_order.remove(key)
        else:
            assert existed is False

    @invariant()
    def size_matches_model(self) -> None:
        assert self.cache.size() == len(self.model)

    @invariant()
    def capacity_never_exceeded(self) -> None:
        assert self.cache.size() <= self.capacity


# This creates a standard pytest test class from the state machine
TestLRUCache = LRUCacheStateMachine.TestCase
```

## Understanding Shrinking Internals

When Hypothesis finds a failing input, it does not stop. It **shrinks** the input toward the simplest possible failing case. This is invaluable **because** a failing test with a 500-element list is nearly impossible to debug, but the same failure reproduced with 2 elements is immediately obvious.

Shrinking works by trying smaller variants of the failing input and keeping any variant that still fails. For integers, it tries values closer to zero. For lists, it tries shorter lists and smaller elements. For composite strategies, it shrinks each component independently. **However**, the trade-off is that aggressive shrinking increases test runtime. Use `@settings(max_examples=200)` for fast CI runs and higher counts for nightly deep exploration.

**Best practice**: always provide `@example(...)` decorators for known edge cases. These run deterministically on every invocation, guaranteeing that previously discovered bugs remain covered even if the random exploration changes. **Pitfall**: using `assume()` too aggressively can make Hypothesis discard most generated inputs, leading to `Unsatisfied` errors. **Therefore**, encode constraints directly into your strategies rather than filtering with `assume()`.

## Pytest Integration Patterns

```python
import pytest
from hypothesis import given, settings, HealthCheck, Verbosity
from hypothesis import strategies as st


# Fixture-based configuration for different environments
@pytest.fixture
def hypothesis_profile(request) -> None:
    # Allow CI to run fewer examples via marker
    marker = request.node.get_closest_marker("slow_hypothesis")
    if marker is not None:
        settings(max_examples=1000, deadline=None).load_profile("ci-thorough")


# Custom marker for property tests that need more examples
# Register in conftest.py: pytest.ini or pyproject.toml
@pytest.mark.slow_hypothesis
@given(data=st.data())
@settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=timedelta(seconds=5),
)
def test_roundtrip_serialization(data: st.DataObject) -> None:
    # Draw from strategy interactively for dependent generation
    format_type = data.draw(st.sampled_from(["json", "msgpack", "csv"]))
    if format_type == "json":
        value = data.draw(st.recursive(
            st.none() | st.booleans() | st.integers() | st.text(max_size=50),
            lambda children: st.lists(children, max_size=5)
            | st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5),
            max_leaves=15,
        ))
    else:
        value = data.draw(st.lists(
            st.fixed_dictionaries({"id": st.integers(), "name": st.text(max_size=30)}),
            max_size=20,
        ))
    # Test that serialize -> deserialize is identity
    serialized = serialize(value, format_type)
    assert deserialize(serialized, format_type) == value
```

## Summary and Key Takeaways

- **Custom composite strategies** let you generate domain objects that satisfy complex invariants; build them by composing `draw()` calls inside `@st.composite` decorated functions
- **Stateful testing with RuleBasedStateMachine** finds bugs in operation sequences that example-based tests cannot reach; always pair the system under test with a simple reference model
- **Shrinking** automatically reduces failing inputs to minimal reproducible cases, **therefore** always inspect the shrunk output rather than the original failure
- **Best practice**: start with three to five properties per function, covering roundtrip identity, invariant preservation, and oracle comparison against a reference implementation
- **Pitfall**: property tests that are too weak provide false confidence; **because** `sort(xs) returns a list` is technically a valid property but catches almost nothing
- **Trade-off**: more `max_examples` means better coverage but slower CI; use profiles to run 100 examples on PRs and 10,000 on nightly builds
- **Integration with pytest** is seamless -- use `@given` as a decorator, `conftest.py` for shared strategies, and `@settings` for environment-specific configuration
- **Common mistake**: generating invalid inputs and filtering with `assume()` instead of building validity into the strategy itself
""",
    ),
    # --- 2. Contract Testing with Pact ---
    (
        "testing/contract-testing-pact",
        r"""Describe consumer-driven contract testing with Pact including provider verification workflows, contract broker configuration, bi-directional contract testing patterns, versioning strategies, and integrating Pact into CI/CD pipelines for microservices architectures.""",
        r"""
# Consumer-Driven Contract Testing with Pact: Ensuring Microservice Compatibility

## Why Contract Testing Exists

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
        self.session.headers.update({
            "Accept": "application/json",
            "X-Api-Version": "2",
        })

    def get_user(self, user_id: int) -> Optional[UserProfile]:
        resp = self.session.get(f"{self.base_url}/api/users/{user_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return UserProfile(
            user_id=data["id"],
            username=data["username"],
            email=data["email"],
            roles=data.get("roles", []),
        )

    def list_users(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        resp = self.session.get(
            f"{self.base_url}/api/users",
            params={"page": page, "per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json()

    def create_user(self, username: str, email: str) -> UserProfile:
        resp = self.session.post(
            f"{self.base_url}/api/users",
            json={"username": username, "email": email},
        )
        resp.raise_for_status()
        data = resp.json()
        return UserProfile(
            user_id=data["id"],
            username=data["username"],
            email=data["email"],
            roles=data.get("roles", []),
        )


# Set up the Pact mock for consumer tests
@pytest.fixture(scope="session")
def pact():
    pact = Consumer("OrderService").has_pact_with(
        Provider("UserService"),
        pact_dir=str(PACT_DIR),
        log_dir=str(PACT_DIR / "logs"),
    )
    pact.start_service()
    yield pact
    pact.stop_service()
    # After tests, pact file is written to PACT_DIR


@pytest.fixture
def user_client(pact) -> UserServiceClient:
    return UserServiceClient(base_url=pact.uri)


def test_get_existing_user(pact, user_client: UserServiceClient) -> None:
    # Define the expected interaction
    expected_body = {
        "id": 42,
        "username": Like("alice"),  # matches any string
        "email": Term(r".+@.+\..+", "alice@example.com"),  # regex match
        "roles": EachLike("admin"),  # array with at least one string element
    }
    (
        pact
        .given("user 42 exists")
        .upon_receiving("a request for user 42")
        .with_request("GET", "/api/users/42", headers={"Accept": "application/json"})
        .will_respond_with(200, body=expected_body)
    )
    with pact:
        user = user_client.get_user(42)
        assert user is not None
        assert user.user_id == 42
        assert "@" in user.email


def test_get_nonexistent_user(pact, user_client: UserServiceClient) -> None:
    (
        pact
        .given("user 9999 does not exist")
        .upon_receiving("a request for a nonexistent user")
        .with_request("GET", "/api/users/9999")
        .will_respond_with(404)
    )
    with pact:
        user = user_client.get_user(9999)
        assert user is None


def test_create_user(pact, user_client: UserServiceClient) -> None:
    (
        pact
        .given("the user database is available")
        .upon_receiving("a request to create a new user")
        .with_request(
            "POST", "/api/users",
            headers={"Content-Type": "application/json"},
            body={"username": "newuser", "email": "new@example.com"},
        )
        .will_respond_with(
            201,
            body={
                "id": Like(1),
                "username": "newuser",
                "email": "new@example.com",
                "roles": [],
            },
        )
    )
    with pact:
        user = user_client.create_user("newuser", "new@example.com")
        assert user.username == "newuser"
```

## Provider Verification

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
        provider_base_url=provider_base_url,
    )

    # Verify against contracts stored in the Pact Broker
    output, logs = verifier.verify_with_broker(
        broker_url=broker_url,
        broker_username=os.environ.get("PACT_BROKER_USERNAME", ""),
        broker_password=os.environ.get("PACT_BROKER_PASSWORD", ""),
        publish_version=os.environ.get("GIT_COMMIT", "unknown"),
        publish_verification_results=publish_results,
        provider_states_setup_url=f"{provider_base_url}/_pact/provider-states",
        enable_pending=True,  # new contracts start as pending
        include_wip_pacts_since="2024-01-01",
    )
    return output == 0


# Provider states handler (Flask example)
def setup_provider_states_endpoint(app, db_session) -> None:
    # Register a route that Pact calls to set up state before each interaction
    state_handlers: Dict[str, Callable[[], None]] = {
        "user 42 exists": lambda: db_session.execute(
            "INSERT INTO users (id, username, email) "
            "VALUES (42, 'alice', 'alice@example.com') "
            "ON CONFLICT DO NOTHING"
        ),
        "user 9999 does not exist": lambda: db_session.execute(
            "DELETE FROM users WHERE id = 9999"
        ),
        "the user database is available": lambda: None,  # no-op, default state
    }

    @app.route("/_pact/provider-states", methods=["POST"])
    def handle_provider_state():
        state = request.json.get("state", "")
        handler = state_handlers.get(state)
        if handler:
            handler()
            db_session.commit()
            return {"status": "ok"}, 200
        return {"error": f"Unknown state: {state}"}, 400
```

## Pact Broker and CI/CD Integration

The **Pact Broker** is the central registry for contracts. It stores pacts, tracks verification results, and provides the `can-i-deploy` tool that gates deployments. **Best practice**: never deploy a service without first checking `can-i-deploy`, **because** a provider that passes its own tests might still break a consumer contract.

**Bi-directional contract testing** is a newer pattern where both consumer and provider independently publish their API specifications (OpenAPI schemas, for instance), and the broker compares them for compatibility. This reduces the coupling between teams **because** providers do not need to run consumer-generated pacts -- they just publish their schema. **However**, the trade-off is less precision: schema compatibility does not guarantee behavioral correctness.

## Versioning and the Contract Matrix

Pact tracks a **verification matrix** -- which consumer versions are compatible with which provider versions. Use **tags** or **branches** to label versions (e.g., `main`, `production`, `feat/new-auth`). The `can-i-deploy` check queries this matrix: "Can OrderService version abc123 deploy to production given the current production version of UserService?"

**Pitfall**: forgetting to publish verification results from CI. Without results, `can-i-deploy` has no data and defaults to blocking deployment. **Therefore**, always pass `--publish-verification-results` in your provider CI pipeline.

## Summary and Key Takeaways

- **Consumer-driven contracts** shift API ownership toward consumers, ensuring providers never break the interactions their clients actually use
- **Pact matchers** (`Like`, `Term`, `EachLike`) allow flexible matching that validates structure without brittle value assertions
- **Provider states** set up test data for each interaction scenario; implement a dedicated endpoint in your provider that the verification framework calls
- **The Pact Broker** acts as a single source of truth for all contracts; integrate `can-i-deploy` as a mandatory gate before any deployment
- **Best practice**: tag your pacts with branch names and environments, enabling targeted verification -- "verify against contracts from consumers currently in production"
- **Bi-directional testing** trades precision for reduced coordination overhead; use it when teams cannot run each other's test suites, **however** be aware it only checks structural compatibility
- **Common mistake**: treating contract tests as a replacement for all integration tests; they verify interface compatibility but not end-to-end business logic
- **Trade-off**: consumer-driven contracts require cross-team coordination to maintain provider states; invest in shared tooling and clear ownership models
- **Pitfall**: allowing contracts to drift by not running verification in CI; **therefore** make provider verification a blocking step in every provider pipeline
""",
    ),
    # --- 3. Mutation Testing ---
    (
        "testing/mutation-testing",
        r"""Explain mutation testing concepts and tooling including mutmut and cosmic-ray for Python, mutation operators and their categories, detecting equivalent mutants, measuring test suite quality with mutation scores, and strategies for efficiently integrating mutation testing into development workflows.""",
        r"""
# Mutation Testing: Measuring the True Quality of Your Test Suite

## What Mutation Testing Reveals That Coverage Cannot

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
        sys.executable, "-m", "mutmut", "run",
        "--paths-to-mutate", source_path,
        "--no-progress",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse the results cache
    jit_result = subprocess.run(
        [sys.executable, "-m", "mutmut", "junitxml"],
        capture_output=True, text=True,
    )

    # Alternative: parse the mutmut cache database directly
    cache_path = Path(".mutmut-cache")
    report = parse_mutmut_cache(cache_path)

    if report.mutation_score < min_score:
        print(
            f"Mutation score {report.mutation_score:.1%} is below "
            f"threshold {min_score:.1%}"
        )
        print(f"Surviving mutants need attention: {report.survived}")
        sys.exit(1)

    return report


def parse_mutmut_cache(cache_path: Path) -> MutationReport:
    # Parse the SQLite cache that mutmut maintains
    import sqlite3
    conn = sqlite3.connect(str(cache_path))
    cursor = conn.execute(
        "SELECT status, COUNT(*) FROM mutant GROUP BY status"
    )
    counts = dict(cursor.fetchall())
    conn.close()
    return MutationReport(
        total_mutants=sum(counts.values()),
        killed=counts.get("killed", 0),
        survived=counts.get("survived", 0),
        timeout=counts.get("timeout", 0),
        suspicious=counts.get("suspicious", 0),
    )
```

## The Equivalent Mutant Problem

An **equivalent mutant** produces behavior identical to the original code despite the syntactic change. For example, changing `x >= 0` to `x > -1` for integer `x` is functionally equivalent. No test can kill this mutant **because** no input distinguishes the two versions. Equivalent mutants inflate the denominator of your mutation score, making it appear lower than it truly is.

**Best practice**: when investigating surviving mutants, first check if they are equivalent before writing new tests. Tools like **cosmic-ray** provide a `--timeout` mechanism and heuristics to flag likely equivalent mutants. **However**, the trade-off is that detecting equivalence is undecidable in the general case (it reduces to the halting problem), so some manual review is always necessary.

## Cosmic-Ray: An Alternative Framework

```python
# cosmic-ray uses a different workflow:
# 1. Initialize: cosmic-ray init config.toml session.sqlite
# 2. Execute:    cosmic-ray exec session.sqlite
# 3. Report:     cosmic-ray report session.sqlite

# config.toml for cosmic-ray
# [cosmic-ray]
# module-path = "src/discount.py"
# timeout = 30.0
# test-command = "python -m pytest tests/ -x -q"
# excluded-modules = []
#
# [cosmic-ray.distributor]
# name = "local"  # or "celery" for distributed execution
```

**Therefore**, choose between mutmut and cosmic-ray based on your needs: mutmut is simpler and has better pytest integration, while cosmic-ray supports distributed execution for large codebases and has more extensible operator sets.

## Strategies for CI Integration

Mutation testing is computationally expensive -- running the full test suite for each mutant can take hours on large projects. **Best practice**: use **incremental mutation testing** -- only mutate files changed in the current pull request. This keeps feedback loops fast while still catching weak tests for new code.

**Pitfall**: running mutation testing on the entire codebase in every CI pipeline. **Therefore**, structure your mutation testing in tiers: (1) incremental on every PR targeting changed files, (2) full module-level testing nightly, and (3) comprehensive whole-project testing weekly.

## Summary and Key Takeaways

- **Mutation testing measures fault-detection capability**, not mere line execution; it is the gold standard for test suite quality assessment
- **Mutation operators** systematically introduce faults: arithmetic replacement, relational replacement, statement deletion, constant modification, and return value changes
- **The mutation score** (killed / total) should target 80%+ for critical business logic; **because** achieving 90%+ often requires disproportionate effort due to equivalent mutants
- **Equivalent mutants** are syntactically different but semantically identical to the original; they require manual review and cannot be killed by any test
- **Best practice**: integrate mutation testing incrementally -- mutate only changed files on PRs, full modules nightly
- **Common mistake**: treating surviving mutants as bugs in your code; they are gaps in your **tests**, not your implementation
- **Trade-off**: mutation testing is expensive; balance thoroughness against CI time by using tiered execution strategies
- **Tools**: mutmut for simplicity and pytest integration, cosmic-ray for distributed execution and extensibility
- **Pitfall**: ignoring timeout mutants -- they often indicate infinite loops introduced by mutations, which can stall your CI pipeline; **therefore** always set aggressive timeouts
""",
    ),
    # --- 4. Load Testing ---
    (
        "testing/load-testing",
        r"""Describe advanced load testing patterns using Locust and k6 including realistic user simulation with weighted scenarios, distributed load generation across multiple workers, analyzing results with percentile metrics, setting performance budgets, and correlating load test results with application metrics for capacity planning.""",
        r"""
# Advanced Load Testing: Realistic Simulation, Distributed Execution, and Performance Budgets

## Why Load Testing Requires Scientific Rigor

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
        self.client.headers.update({
            "X-Session-Id": self.session_id,
            "Accept": "application/json",
        })

    @task(10)  # relative weight: most common action
    def browse_catalog(self) -> None:
        page = random.randint(1, 50)
        with self.client.get(
            f"/api/products?page={page}&per_page=20",
            name="/api/products?page=[n]",  # aggregate in reports
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Capture product IDs for subsequent requests
                self.product_ids = [p["id"] for p in data.get("products", [])]
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
            name="/api/products/[id]",
        )

    @task(2)
    def search_products(self) -> None:
        queries = ["laptop", "headphones", "keyboard", "monitor", "mouse"]
        query = random.choice(queries)
        self.client.get(
            f"/api/search?q={query}&limit=20",
            name="/api/search?q=[query]",
        )


class PurchasingUser(HttpUser):
    # 25% of traffic: users who complete purchases
    weight = 25
    wait_time = between(1, 5)
    host = "https://api.example.com"

    def on_start(self) -> None:
        # Authenticate on session start
        resp = self.client.post("/api/auth/login", json={
            "username": f"loadtest_{random.randint(1, 10000)}",
            "password": "test_password",
        })
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            self.client.headers["Authorization"] = f"Bearer {token}"

    @task(3)
    def add_to_cart(self) -> None:
        product_id = random.randint(1, 1000)
        self.client.post("/api/cart/items", json={
            "product_id": product_id,
            "quantity": random.randint(1, 3),
        })

    @task(1)
    def checkout(self) -> None:
        with self.client.post(
            "/api/checkout",
            json={"payment_method": "test_card"},
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                response.success()
            elif response.status_code == 422:
                response.success()  # empty cart is expected sometimes
            else:
                response.failure(f"Checkout failed: {response.status_code}")


class AdminUser(HttpUser):
    # 5% of traffic: admin operations (heavy queries)
    weight = 5
    wait_time = between(5, 15)
    host = "https://api.example.com"

    @task
    def generate_report(self) -> None:
        self.client.get(
            "/api/admin/reports/daily-summary",
            timeout=30,  # admin reports are slow
        )
```

## k6: JavaScript-Based Load Testing with Performance Budgets

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
""",
    ),
    # --- 5. Visual Regression Testing ---
    (
        "testing/visual-regression",
        r"""Explain visual regression testing including screenshot comparison techniques, Playwright visual testing APIs, perceptual diffing algorithms, component isolation strategies for deterministic snapshots, handling dynamic content, and integrating visual tests into CI pipelines with approval workflows.""",
        r"""
# Visual Regression Testing: Screenshot Comparison, Perceptual Diffing, and CI Integration

## Why Visual Regression Testing Matters

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
    return {
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "color_scheme": "light",
        "device_scale_factor": 1,  # consistent pixel density
        "reduced_motion": "reduce",  # disable animations
    }


@pytest.fixture
def authenticated_page(page: Page, base_url: str) -> Page:
    # Set up authentication state for protected pages
    page.goto(f"{base_url}/login")
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
            max_diff_pixels=100,  # allow minor anti-aliasing differences
        )

    def test_dashboard_sidebar_collapsed(self, authenticated_page: Page) -> None:
        page = authenticated_page
        page.click("[data-testid='sidebar-toggle']")
        page.wait_for_timeout(300)  # wait for collapse animation
        expect(page).to_have_screenshot(
            "dashboard-sidebar-collapsed.png",
            max_diff_pixel_ratio=0.01,  # 1% pixel difference allowed
        )

    def test_chart_component_isolated(self, authenticated_page: Page) -> None:
        page = authenticated_page
        # Isolate a specific component for focused comparison
        chart = page.locator("[data-testid='revenue-chart']")
        chart.wait_for(state="visible")
        # Mask dynamic tooltip content
        expect(chart).to_have_screenshot(
            "revenue-chart.png",
            mask=[page.locator("[data-testid='chart-tooltip']")],
            animations="disabled",
        )

    def test_responsive_mobile_layout(self, browser: Browser) -> None:
        # Test mobile viewport separately
        context = browser.new_context(
            viewport={"width": 375, "height": 812},
            device_scale_factor=3,  # retina
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        page.goto("/dashboard")
        page.wait_for_load_state("networkidle")
        expect(page).to_have_screenshot(
            "dashboard-mobile.png",
            full_page=True,
            max_diff_pixels=50,
        )
        context.close()

    def test_dark_mode_theme(self, browser: Browser) -> None:
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            color_scheme="dark",
        )
        page = context.new_page()
        page.goto("/dashboard")
        page.wait_for_load_state("networkidle")
        expect(page).to_have_screenshot("dashboard-dark-mode.png")
        context.close()
```

## Perceptual Diffing Algorithms

Pixel-by-pixel comparison is too brittle for real-world use. Sub-pixel rendering differences between operating systems, anti-aliasing variations, and font hinting changes produce false positives that drown out real regressions. **Perceptual diffing** algorithms solve this by comparing images the way the human visual system perceives them.

```python
# Perceptual diff implementation using structural similarity
from dataclasses import dataclass
from typing import Tuple
from pathlib import Path
import numpy as np


@dataclass
class DiffResult:
    # Result of comparing two screenshots
    is_match: bool
    similarity_score: float  # 0.0 = completely different, 1.0 = identical
    diff_pixel_count: int
    diff_percentage: float
    diff_image_path: Optional[Path] = None

    @property
    def summary(self) -> str:
        status = "PASS" if self.is_match else "FAIL"
        return (
            f"[{status}] Similarity: {self.similarity_score:.4f}, "
            f"Diff pixels: {self.diff_pixel_count} ({self.diff_percentage:.2f}%)"
        )


def compute_perceptual_diff(
    baseline_path: Path,
    actual_path: Path,
    threshold: float = 0.995,
    output_diff_path: Optional[Path] = None,
) -> DiffResult:
    # Compare two images using SSIM (Structural Similarity Index)
    # SSIM considers luminance, contrast, and structure -- matching
    # human visual perception better than raw pixel comparison

    # In production, use scikit-image or Pillow
    # from skimage.metrics import structural_similarity as ssim
    # Here we show the algorithm conceptually

    baseline = load_image_as_array(baseline_path)
    actual = load_image_as_array(actual_path)

    if baseline.shape != actual.shape:
        return DiffResult(
            is_match=False,
            similarity_score=0.0,
            diff_pixel_count=max(baseline.size, actual.size),
            diff_percentage=100.0,
        )

    # Per-pixel difference with perceptual weighting
    # Weight channels by human perception: green > red > blue
    weights = np.array([0.2989, 0.5870, 0.1140])
    baseline_gray = np.dot(baseline[..., :3], weights)
    actual_gray = np.dot(actual[..., :3], weights)

    # Compute SSIM components
    mu_base = uniform_filter(baseline_gray, size=11)
    mu_actual = uniform_filter(actual_gray, size=11)
    sigma_base_sq = uniform_filter(baseline_gray ** 2, size=11) - mu_base ** 2
    sigma_actual_sq = uniform_filter(actual_gray ** 2, size=11) - mu_actual ** 2
    sigma_cross = (
        uniform_filter(baseline_gray * actual_gray, size=11) - mu_base * mu_actual
    )

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    ssim_map = (
        (2 * mu_base * mu_actual + C1) * (2 * sigma_cross + C2)
    ) / (
        (mu_base ** 2 + mu_actual ** 2 + C1) * (sigma_base_sq + sigma_actual_sq + C2)
    )
    similarity = float(np.mean(ssim_map))

    # Count significantly different pixels
    pixel_diff = np.abs(baseline_gray - actual_gray)
    diff_mask = pixel_diff > 10  # threshold for "noticeable" difference
    diff_count = int(np.sum(diff_mask))
    total_pixels = baseline_gray.size
    diff_pct = (diff_count / total_pixels) * 100

    if output_diff_path is not None:
        generate_diff_visualization(baseline, actual, diff_mask, output_diff_path)

    return DiffResult(
        is_match=similarity >= threshold,
        similarity_score=similarity,
        diff_pixel_count=diff_count,
        diff_percentage=diff_pct,
        diff_image_path=output_diff_path,
    )


def load_image_as_array(path: Path) -> np.ndarray:
    # Load image and normalize to float32 [0, 255]
    from PIL import Image
    img = Image.open(path).convert("RGB")
    return np.array(img, dtype=np.float32)


def uniform_filter(arr: np.ndarray, size: int) -> np.ndarray:
    # Simple uniform box filter for SSIM computation
    from scipy.ndimage import uniform_filter as scipy_uniform_filter
    return scipy_uniform_filter(arr, size=size, mode="reflect")


def generate_diff_visualization(
    baseline: np.ndarray,
    actual: np.ndarray,
    diff_mask: np.ndarray,
    output_path: Path,
) -> None:
    # Create a visual diff highlighting changed regions in red
    from PIL import Image
    diff_visual = actual.copy()
    diff_visual[diff_mask] = [255, 0, 0]  # highlight diffs in red
    Image.fromarray(diff_visual.astype(np.uint8)).save(output_path)
```

## Component Isolation for Deterministic Snapshots

The biggest challenge in visual testing is **determinism**. Dynamic content, animations, loading spinners, relative timestamps, and randomized content all produce false diffs. **Best practice**: isolate components in a controlled environment.

**Therefore**, use Storybook or similar component catalogs to render components in isolation with fixed props, mocked data, and disabled animations. This eliminates environmental variance. For full-page tests, use Playwright's ability to mock network requests and freeze time.

**Pitfall**: forgetting to wait for web fonts to load before capturing screenshots. Font fallback rendering looks dramatically different from the intended design. **Because** font loading is asynchronous, always use `page.wait_for_load_state("networkidle")` and verify font availability via `document.fonts.ready`.

## CI Integration with Approval Workflows

Visual test failures require human judgment -- a diff might be an intentional redesign or an unexpected regression. **Best practice**: integrate visual testing with an approval workflow.

```python
# CI pipeline configuration for visual regression testing
# This integrates with GitHub Actions and stores baselines in the repo

# conftest.py -- configure Playwright snapshot paths
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
DIFF_OUTPUT_DIR = Path(__file__).parent / "snapshot-diffs"


def pytest_configure(config) -> None:
    # Ensure diff output directory exists for CI artifact upload
    DIFF_OUTPUT_DIR.mkdir(exist_ok=True)
    # Set Playwright snapshot update mode from environment
    import os
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        config.option.update_snapshots = True


# GitHub Actions workflow excerpt (as Python dict for illustration):
ci_workflow = {
    "visual-regression": {
        "runs-on": "ubuntu-latest",
        "container": "mcr.microsoft.com/playwright/python:v1.40.0",
        "steps": [
            {"name": "Run visual tests", "run": "pytest tests/visual/ --browser chromium"},
            {
                "name": "Upload diff artifacts",
                "if": "failure()",
                "uses": "actions/upload-artifact@v4",
                "with": {
                    "name": "visual-diffs",
                    "path": "tests/visual/snapshot-diffs/",
                    "retention-days": 30,
                },
            },
        ],
    }
}
```

When visual tests fail in CI, the diff images are uploaded as build artifacts. Reviewers inspect the diffs and either approve the changes (updating baselines by running `pytest --update-snapshots` and committing) or flag them as regressions. **However**, the trade-off is that this adds a manual step to the review process. Teams must decide whether visual test failures block merging or are advisory.

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
""",
    ),
]
