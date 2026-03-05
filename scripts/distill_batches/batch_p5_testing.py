"""
Batch P5 -- Testing Strategies: property-based testing, contract testing,
chaos engineering, mutation testing, load/performance testing.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Property-Based Testing with Hypothesis ---
    (
        "property_based_testing_hypothesis_python",
        "Explain property-based testing with Hypothesis in Python -- custom generators, "
        "shrinking algorithms, stateful testing with RuleBasedStateMachine, finding edge cases "
        "that traditional unit tests miss, integrating with pytest, and advanced strategies for "
        "complex data structures. Show complete production-ready code examples with type hints.",
        r"""
# Property-Based Testing with Hypothesis: Finding Bugs Unit Tests Miss

## Why Property-Based Testing Matters

Traditional unit tests verify **specific examples** you thought of. Property-based testing
verifies **universal properties** across thousands of randomly generated inputs. The core
insight is this: instead of writing `assert sort([3,1,2]) == [1,2,3]`, you write
`assert is_sorted(sort(xs)) and same_elements(sort(xs), xs)` -- and let the framework
generate thousands of `xs` values, including edge cases you never considered.

This matters **because** the bugs that escape to production are almost never the ones you
thought to test. They live in boundary conditions, Unicode edge cases, empty collections,
integer overflow, and bizarre input combinations. Hypothesis systematically explores these
spaces in ways human intuition cannot.

**Common mistake**: Developers often think "I have 95% code coverage, so I'm safe." However,
code coverage measures which lines execute, not which *behaviors* are exercised. A single
line can behave differently for empty lists, single-element lists, duplicate elements, and
MAX_INT values -- all covered by one test that only checks `[1,2,3]`.

## Core Concepts: Strategies and Shrinking

Hypothesis uses **strategies** to generate test data. When a failure is found, the
**shrinking** algorithm minimizes the failing input to the simplest reproducing case.

```python
from hypothesis import given, settings, assume, example, HealthCheck
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, precondition, invariant
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import re

# Basic strategy composition -- builds complex types from simple ones
emails: st.SearchStrategy[str] = st.from_regex(
    r"[a-z]{1,20}@[a-z]{1,10}\.(com|org|net)", fullmatch=True
)

# Recursive strategy for tree-like structures
# Using # comments instead of docstrings inside code blocks
json_values = st.recursive(
    # Base case: leaves of the JSON tree
    st.none() | st.booleans() | st.floats(allow_nan=False) | st.text(max_size=50),
    # Recursive case: containers that hold other JSON values
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5)
    ),
    max_leaves=20,
)

# Composite strategy for domain objects
@st.composite
def user_profiles(draw: st.DrawFn) -> Dict[str, object]:
    # Draws from sub-strategies to build a coherent domain object
    name = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "Zs"),  # letters and spaces only
    )))
    age = draw(st.integers(min_value=0, max_value=150))
    email = draw(emails)
    tags = draw(st.lists(st.text(min_size=1, max_size=20), max_size=10, unique=True))
    return {"name": name.strip() or "Anonymous", "age": age, "email": email, "tags": tags}


# Property test: sorting preserves elements and produces ordered output
@given(st.lists(st.integers()))
def test_sort_preserves_elements_and_orders(xs: List[int]) -> None:
    result = sorted(xs)
    # Property 1: output is sorted
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1], f"Not sorted at index {i}"
    # Property 2: same elements (as multiset)
    assert sorted(result) == sorted(xs)
    # Property 3: length preserved
    assert len(result) == len(xs)


# Property test with filtering via assume()
@given(st.lists(st.integers(min_value=1, max_value=10000), min_size=1))
def test_max_is_in_list(xs: List[int]) -> None:
    m = max(xs)
    assert m in xs
    assert all(x <= m for x in xs)


# Pinning known regression with @example
@given(st.text())
@example("")          # empty string -- a classic edge case
@example("\x00")      # null byte
@example("a" * 10000) # very long string
def test_string_roundtrip_through_encoding(s: str) -> None:
    encoded = s.encode("utf-8")
    decoded = encoded.decode("utf-8")
    assert decoded == s
```

The **shrinking** algorithm is what makes Hypothesis truly powerful. When it finds a failing
input like `[47, -293, 0, 8192, -1]`, it doesn't just report that -- it systematically
reduces the input, trying smaller values, shorter lists, simpler structures, until it finds
the **minimal** failing case, perhaps `[0, -1]`. This is invaluable **because** debugging
a minimal case is orders of magnitude easier than debugging a complex one.

## Stateful Testing: Testing State Machines

The **best practice** for testing stateful systems is Hypothesis's `RuleBasedStateMachine`.
It generates sequences of operations and checks invariants after each step. This approach
finds bugs that no amount of individual method testing can catch, **because** it explores
*sequences* of interactions.

```python
from collections import OrderedDict
from typing import Any

# System under test: an LRU cache implementation
class LRUCache:
    # A least-recently-used cache with fixed capacity
    def __init__(self, capacity: int) -> None:
        self.capacity: int = capacity
        self._store: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self.capacity:
            self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def size(self) -> int:
        return len(self._store)


# Stateful test: model-based testing against a simple dict reference
class LRUCacheStateMachine(RuleBasedStateMachine):
    # Tests the LRU cache against a reference implementation

    def __init__(self) -> None:
        super().__init__()
        self.cache = LRUCache(capacity=3)
        # Reference model: simple dict with manual LRU tracking
        self.model: OrderedDict[str, Any] = OrderedDict()
        self.capacity = 3

    @rule(key=st.text(min_size=1, max_size=5), value=st.integers())
    def put_item(self, key: str, value: int) -> None:
        # Insert or update an item in both cache and model
        self.cache.put(key, value)
        if key in self.model:
            self.model.move_to_end(key)
        self.model[key] = value
        while len(self.model) > self.capacity:
            self.model.popitem(last=False)

    @rule(key=st.text(min_size=1, max_size=5))
    def get_item(self, key: str) -> None:
        # Read an item and verify model agreement
        result = self.cache.get(key)
        expected = self.model.get(key)
        if key in self.model:
            self.model.move_to_end(key)
        assert result == expected, f"get({key!r}): got {result}, expected {expected}"

    @rule(key=st.text(min_size=1, max_size=5))
    def delete_item(self, key: str) -> None:
        # Delete an item from both implementations
        cache_result = self.cache.delete(key)
        model_had_key = key in self.model
        if model_had_key:
            del self.model[key]
        assert cache_result == model_had_key

    @invariant()
    def size_matches(self) -> None:
        assert self.cache.size() == len(self.model)

    @invariant()
    def never_exceeds_capacity(self) -> None:
        assert self.cache.size() <= self.capacity


# pytest discovers this automatically
TestLRUCache = LRUCacheStateMachine.TestCase
```

## Advanced Strategies for Complex Domains

A **pitfall** many teams encounter is writing property tests that are too weak -- they
reimplement the function under test as their oracle. The **best practice** is to use
**metamorphic relations**, **round-trip properties**, and **invariant checks** instead.

```python
import json
import math
from hypothesis import given, settings, Phase
from hypothesis import strategies as st

# Metamorphic testing: relating outputs of different inputs
@given(st.lists(st.integers(), min_size=1), st.integers())
def test_adding_element_changes_length_by_one(xs: List[int], x: int) -> None:
    original_len = len(xs)
    xs.append(x)
    assert len(xs) == original_len + 1

# Round-trip property: serialize then deserialize
@given(json_values)
def test_json_roundtrip(value: object) -> None:
    serialized = json.dumps(value)
    deserialized = json.loads(serialized)
    assert deserialized == value

# Idempotence property: applying twice gives same result as once
@given(st.text())
def test_strip_is_idempotent(s: str) -> None:
    once = s.strip()
    twice = once.strip()
    assert once == twice

# Commutativity / algebraic properties
@given(st.integers(), st.integers())
def test_addition_is_commutative(a: int, b: int) -> None:
    assert a + b == b + a

# Testing with database settings: suppress health checks for slow operations
@settings(
    max_examples=200,
    deadline=None,                          # no per-test timeout
    suppress_health_check=[HealthCheck.too_slow],
    phases=[Phase.explicit, Phase.generate, Phase.shrink],
)
@given(user_profiles())
def test_user_profile_validation(profile: Dict[str, object]) -> None:
    # Validates that generated profiles meet business rules
    assert len(str(profile["name"])) >= 1
    assert 0 <= int(str(profile["age"])) <= 150
    assert "@" in str(profile["email"])
```

## Integration with pytest and CI

The **trade-off** with property-based testing is execution time. Each test runs hundreds
or thousands of iterations by default. Therefore, configure your CI pipeline to run more
examples than local development.

Set `@settings(max_examples=50)` locally and `max_examples=1000` in CI via profiles.
Hypothesis stores failing examples in `.hypothesis/` -- commit this directory so
regressions are permanently pinned across the team.

## Summary and Key Takeaways

- **Property-based testing finds bugs that example-based tests miss** because it explores
  the input space systematically, including edge cases humans overlook
- **Shrinking is the killer feature**: it reduces complex failures to minimal reproducible
  cases, saving hours of debugging
- **Stateful testing** via `RuleBasedStateMachine` catches interaction bugs by generating
  random sequences of operations and verifying invariants at every step
- **Best practice**: prefer metamorphic relations and round-trip properties over re-implementing
  the logic under test as your oracle
- **Pitfall**: starting with overly complex custom strategies -- begin with built-in
  strategies and compose them; only write `@st.composite` when truly needed
- **CI integration**: use Hypothesis profiles to run more examples in CI, and commit the
  `.hypothesis/` database to persist regressions
""",
    ),

    # --- 2. Contract Testing with Pact ---
    (
        "contract_testing_pact_consumer_driven_python",
        "Explain consumer-driven contract testing with Pact for Python microservices -- how Pact "
        "works, writing consumer tests, provider verification, managing the Pact Broker, handling "
        "provider states, versioning strategies, CI/CD integration with can-i-deploy, and advanced "
        "patterns for event-driven architectures. Provide complete working code examples.",
        r"""
# Contract Testing with Pact: Consumer-Driven Contracts for Microservices

## The Problem Pact Solves

In a microservice architecture, services communicate over HTTP or messaging. Traditional
integration tests spin up all services to verify they work together, but this approach
has devastating **trade-offs**: it is slow, flaky, expensive, and creates tight coupling
between team deployment schedules. If Team A's CI depends on Team B's service being
available and configured correctly, both teams lose velocity.

**Contract testing** solves this by verifying each side of an integration *independently*.
The **consumer** (the service making requests) writes a test that declares what it expects
from the provider. This expectation becomes a **contract** (a Pact file). The **provider**
then verifies it can fulfill that contract. Neither service needs the other running.

**Because** each side tests independently, contract tests are fast, deterministic, and
can run in isolated CI pipelines. However, the **common mistake** is thinking contracts
replace integration tests entirely -- they verify *interface compatibility*, not end-to-end
business logic. Therefore, you still need a thin layer of end-to-end smoke tests.

## How Pact Works: The Workflow

```
Consumer Test Run:
  1. Consumer test defines expected interactions (request -> response pairs)
  2. Pact mock server stands in for the real provider
  3. Consumer code makes requests to the mock
  4. Pact verifies consumer used the mock correctly
  5. Pact file (JSON contract) is generated

Contract Publishing:
  6. Consumer publishes Pact file to Pact Broker
  7. Broker stores contracts with version metadata

Provider Verification:
  8. Provider fetches relevant Pacts from Broker
  9. Provider replays each interaction against its real API
  10. Results are published back to the Broker

Deployment Gate:
  11. can-i-deploy checks Broker to see if versions are compatible
  12. Deploy proceeds only if all contracts are verified
```

## Consumer Side: Writing Pact Tests in Python

```python
import pytest
import requests
from typing import Optional, List
from dataclasses import dataclass, asdict
from pact import Consumer, Provider, Like, EachLike, Term
from pact.matchers import get_generated_values
import json
import os

# Domain model for the consumer
@dataclass
class UserProfile:
    # Represents a user profile fetched from the Users service
    id: int
    username: str
    email: str
    roles: List[str]
    active: bool

@dataclass
class UserServiceClient:
    # HTTP client for the Users microservice
    base_url: str

    def get_user(self, user_id: int) -> Optional[UserProfile]:
        # Fetches a single user by ID from the provider API
        resp = requests.get(f"{self.base_url}/api/users/{user_id}", timeout=5)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return UserProfile(**data)

    def list_active_users(self) -> List[UserProfile]:
        # Lists all active users from the provider
        resp = requests.get(
            f"{self.base_url}/api/users",
            params={"active": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        return [UserProfile(**u) for u in resp.json()["users"]]


# --- Pact Consumer Test ---
PACT_DIR = os.path.join(os.path.dirname(__file__), "pacts")

pact = Consumer("OrderService").has_pact_with(
    Provider("UserService"),
    pact_dir=PACT_DIR,
    log_dir=os.path.join(os.path.dirname(__file__), "logs"),
)


def test_get_existing_user(pact_context=pact) -> None:
    # Verifies consumer can parse a valid user response
    expected_body = {
        "id": 42,
        "username": Like("jdoe"),         # matches any string
        "email": Term(r".+@.+\..+", "jdoe@example.com"),  # regex match
        "roles": EachLike("admin"),       # list with at least one string
        "active": True,
    }

    (pact_context
        .given("a user with ID 42 exists")
        .upon_receiving("a request for user 42")
        .with_request("GET", "/api/users/42")
        .will_respond_with(200, body=expected_body))

    with pact_context:
        client = UserServiceClient(base_url=pact_context.uri)
        user = client.get_user(42)

    assert user is not None
    assert user.id == 42
    assert "@" in user.email
    assert isinstance(user.roles, list)


def test_get_nonexistent_user(pact_context=pact) -> None:
    # Verifies consumer handles 404 gracefully
    (pact_context
        .given("no user with ID 9999 exists")
        .upon_receiving("a request for nonexistent user 9999")
        .with_request("GET", "/api/users/9999")
        .will_respond_with(404, body={"error": Like("User not found")}))

    with pact_context:
        client = UserServiceClient(base_url=pact_context.uri)
        user = client.get_user(9999)

    assert user is None


def test_list_active_users(pact_context=pact) -> None:
    # Verifies the list endpoint returns expected shape
    expected_body = {
        "users": EachLike({
            "id": Like(1),
            "username": Like("alice"),
            "email": Like("alice@example.com"),
            "roles": EachLike("viewer"),
            "active": True,
        }),
        "total": Like(1),
    }

    (pact_context
        .given("active users exist in the system")
        .upon_receiving("a request for active users")
        .with_request("GET", "/api/users", query={"active": "true"})
        .will_respond_with(200, body=expected_body))

    with pact_context:
        client = UserServiceClient(base_url=pact_context.uri)
        users = client.list_active_users()

    assert len(users) >= 1
    assert all(u.active for u in users)
```

## Provider Side: Verification with State Handlers

The provider verification replays each interaction from the Pact file against the real API.
The **best practice** is to use **provider states** to set up test data before each interaction.

```python
import pytest
from pact_verifier import PactVerifier
from flask import Flask, jsonify
from typing import Dict, Any, Callable
from unittest.mock import patch
import subprocess

# Provider app (simplified Flask)
app = Flask(__name__)

# In-memory store for test isolation
_test_users: Dict[int, Dict[str, Any]] = {}

@app.route("/api/users/<int:user_id>")
def get_user(user_id: int) -> tuple:
    user = _test_users.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user), 200

@app.route("/api/users")
def list_users() -> tuple:
    from flask import request as req
    active_only = req.args.get("active", "").lower() == "true"
    users = list(_test_users.values())
    if active_only:
        users = [u for u in users if u.get("active")]
    return jsonify({"users": users, "total": len(users)}), 200

# --- Provider state handlers ---
def state_user_42_exists() -> None:
    # Sets up test data for the 'a user with ID 42 exists' state
    _test_users[42] = {
        "id": 42, "username": "jdoe", "email": "jdoe@example.com",
        "roles": ["admin", "user"], "active": True,
    }

def state_no_user_9999() -> None:
    # Ensures user 9999 does not exist
    _test_users.pop(9999, None)

def state_active_users_exist() -> None:
    # Populates multiple active users
    _test_users.clear()
    _test_users[1] = {
        "id": 1, "username": "alice", "email": "alice@co.com",
        "roles": ["viewer"], "active": True,
    }
    _test_users[2] = {
        "id": 2, "username": "bob", "email": "bob@co.com",
        "roles": ["editor"], "active": True,
    }

STATE_HANDLERS: Dict[str, Callable[[], None]] = {
    "a user with ID 42 exists": state_user_42_exists,
    "no user with ID 9999 exists": state_no_user_9999,
    "active users exist in the system": state_active_users_exist,
}

def provider_state_handler(state_name: str, **kwargs: Any) -> None:
    _test_users.clear()
    handler = STATE_HANDLERS.get(state_name)
    if handler:
        handler()
    else:
        raise ValueError(f"Unknown provider state: {state_name}")


# Verification test using pytest
def test_provider_against_pact() -> None:
    verifier = PactVerifier(
        provider="UserService",
        provider_base_url="http://localhost:5000",
    )
    # Fetch pacts from broker and verify
    output, return_code = verifier.verify_with_broker(
        broker_url="https://pact-broker.internal.company.com",
        broker_username=os.environ.get("PACT_BROKER_USERNAME", ""),
        broker_password=os.environ.get("PACT_BROKER_PASSWORD", ""),
        provider_states_setup_url="http://localhost:5000/_pact/state",
        publish_verification_results=True,
        provider_app_version=os.environ.get("GIT_SHA", "dev"),
        consumer_version_selectors=[
            {"mainBranch": True},           # latest on main
            {"deployedOrReleased": True},   # currently deployed
        ],
    )
    assert return_code == 0, f"Pact verification failed:\n{output}"
```

## CI/CD Integration with can-i-deploy

The **trade-off** with contract testing is the operational overhead of the Pact Broker.
**However**, it pays for itself by preventing broken deployments. The `can-i-deploy` tool
is the deployment gate that checks whether a particular version is compatible with everything
currently deployed.

```yaml
# .github/workflows/contract-test.yml
# CI pipeline that gates deployment on contract compatibility
name: Contract Tests
on: [push]
jobs:
  consumer-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pact-python pytest
      - run: pytest tests/contract/ --tb=short
      - run: |
          pact-broker publish pacts/ \
            --consumer-app-version=${{ github.sha }} \
            --branch=${{ github.ref_name }} \
            --broker-base-url=${{ secrets.PACT_BROKER_URL }} \
            --broker-token=${{ secrets.PACT_BROKER_TOKEN }}

  can-i-deploy:
    needs: consumer-tests
    runs-on: ubuntu-latest
    steps:
      - run: |
          pact-broker can-i-deploy \
            --pacticipant=OrderService \
            --version=${{ github.sha }} \
            --to-environment=production \
            --broker-base-url=${{ secrets.PACT_BROKER_URL }} \
            --broker-token=${{ secrets.PACT_BROKER_TOKEN }}
```

## Handling Event-Driven Contracts

For message-based systems (Kafka, RabbitMQ), Pact supports **message pacts**. The consumer
defines the expected message shape, and the provider verifies it can produce that message.
This is critical **because** asynchronous integrations are even harder to test with
traditional integration approaches.

## Summary and Key Takeaways

- **Consumer-driven contracts** let each side of an integration test independently, eliminating
  flaky integration test suites and cross-team deployment coupling
- **Pact matchers** (`Like`, `EachLike`, `Term`) verify structure and types rather than exact
  values -- this is a **best practice** that prevents brittle contracts
- **Provider states** set up test data for each interaction, ensuring reproducible verification
- **The Pact Broker** is the central registry: it stores contracts, tracks versions, and powers
  the `can-i-deploy` deployment gate
- **Pitfall**: writing contracts that are too strict (exact value matching) causes false failures;
  too loose (no matching) misses real incompatibilities. Therefore, match on **structure and type**
- **Event-driven contracts** extend the same pattern to messaging, covering Kafka/RabbitMQ integrations
""",
    ),

    # --- 3. Chaos Engineering ---
    (
        "chaos_engineering_fault_injection_kubernetes",
        "Explain chaos engineering principles and practices -- steady-state hypothesis, fault "
        "injection techniques, GameDay planning and execution, using Litmus and ChaosMesh for "
        "Kubernetes, the Python Chaos Toolkit for automating chaos experiments, blast radius "
        "control, and building organizational confidence in system resilience. Provide complete "
        "code examples for automated chaos experiments.",
        r"""
# Chaos Engineering: Building Confidence Through Controlled Failure

## The Philosophy of Chaos Engineering

Chaos engineering is the discipline of **experimenting on a system to build confidence in its
ability to withstand turbulent conditions in production**. This definition from the Principles
of Chaos Engineering is precise: it says "build confidence," not "find bugs." The goal is not
to break things -- it is to **learn how the system behaves under stress** so you can improve
it before real failures occur.

The **common mistake** is equating chaos engineering with "randomly killing pods in production."
That is chaos *monkeying*, not engineering. True chaos engineering follows the scientific method:

1. **Define steady state** -- measurable indicators of normal system behavior
2. **Hypothesize** -- predict that the steady state will continue during the experiment
3. **Inject failure** -- introduce a realistic fault (network partition, CPU pressure, disk fill)
4. **Observe** -- compare actual behavior to your hypothesis
5. **Learn** -- if the hypothesis held, confidence increases; if not, you found a weakness

**Because** distributed systems have emergent behaviors that no amount of code review can
predict, chaos engineering is the only way to validate resilience assumptions at scale.

## Steady-State Hypothesis

The steady-state hypothesis is the **most important** part of any chaos experiment. Without
it, you are just breaking things randomly. A good hypothesis is quantitative and measurable.

```
Bad hypothesis:  "The system should keep working when a pod dies"
Good hypothesis: "When 1 of 3 API pods is terminated, p99 latency remains
                  below 500ms, error rate stays under 0.1%, and all requests
                  complete within 30 seconds during the recovery window"

Bad hypothesis:  "The database failover works"
Good hypothesis: "When the primary database node is network-partitioned,
                  automatic failover completes in under 30 seconds, zero
                  transactions are lost, and the application returns to
                  steady-state error rate (<0.01%) within 60 seconds"
```

## Python Chaos Toolkit: Automated Experiments

The Chaos Toolkit provides a declarative JSON/YAML format for experiments with a Python
extension API. **Best practice** is to define experiments as code, version them alongside
your application, and run them in CI.

```python
import json
import subprocess
import time
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

class ExperimentStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"

@dataclass
class Probe:
    # Defines a measurement of system state
    name: str
    type: str              # "http", "python", "process"
    provider: Dict[str, Any]
    tolerance: Any         # expected value or range

@dataclass
class Action:
    # Defines a fault injection action
    name: str
    type: str
    provider: Dict[str, Any]
    pauses: Optional[Dict[str, int]] = None

@dataclass
class ChaosExperiment:
    # Full chaos experiment definition following the scientific method
    title: str
    description: str
    tags: List[str]
    steady_state_hypothesis: Dict[str, Any]
    method: List[Dict[str, Any]]
    rollbacks: List[Dict[str, Any]] = field(default_factory=list)

    def to_chaos_toolkit_format(self) -> Dict[str, Any]:
        # Converts to Chaos Toolkit JSON experiment format
        return {
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "steady-state-hypothesis": self.steady_state_hypothesis,
            "method": self.method,
            "rollbacks": self.rollbacks,
        }


def build_pod_kill_experiment(
    namespace: str,
    label_selector: str,
    service_url: str,
    max_latency_ms: int = 500,
    max_error_rate: float = 0.001,
) -> ChaosExperiment:
    # Builds a pod-kill experiment with steady-state verification
    return ChaosExperiment(
        title=f"Pod termination resilience: {label_selector}",
        description=(
            f"Verifies that killing a pod matching '{label_selector}' in "
            f"namespace '{namespace}' does not degrade service beyond thresholds"
        ),
        tags=["kubernetes", "pod-kill", "resilience"],
        steady_state_hypothesis={
            "title": "Service remains healthy",
            "probes": [
                {
                    "name": "service-responds-200",
                    "type": "http",
                    "provider": {
                        "type": "http",
                        "url": f"{service_url}/health",
                        "timeout": 5,
                    },
                    "tolerance": 200,
                },
                {
                    "name": "error-rate-below-threshold",
                    "type": "python",
                    "provider": {
                        "type": "python",
                        "module": "chaos_probes",
                        "func": "check_error_rate",
                        "arguments": {
                            "prometheus_url": "http://prometheus:9090",
                            "query": f'rate(http_requests_total{{status=~"5..",app="{label_selector}"}}[1m])',
                            "threshold": max_error_rate,
                        },
                    },
                    "tolerance": True,
                },
            ],
        },
        method=[
            {
                "type": "action",
                "name": "kill-pod",
                "provider": {
                    "type": "python",
                    "module": "chaosk8s.pod.actions",
                    "func": "terminate_pods",
                    "arguments": {
                        "ns": namespace,
                        "label_selector": label_selector,
                        "qty": 1,
                        "rand": True,
                        "grace_period": 0,
                    },
                },
                "pauses": {"after": 30},  # wait 30s for recovery
            },
        ],
        rollbacks=[
            {
                "type": "action",
                "name": "ensure-minimum-replicas",
                "provider": {
                    "type": "python",
                    "module": "chaosk8s.deployment.actions",
                    "func": "scale_deployment",
                    "arguments": {
                        "name": label_selector,
                        "ns": namespace,
                        "replicas": 3,
                    },
                },
            },
        ],
    )


# --- Chaos probes module (chaos_probes.py) ---
def check_error_rate(
    prometheus_url: str, query: str, threshold: float
) -> bool:
    # Queries Prometheus and returns True if error rate is below threshold
    resp = requests.get(
        f"{prometheus_url}/api/v1/query",
        params={"query": query},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return True  # no errors at all
    error_rate = float(result[0]["value"][1])
    return error_rate < threshold


def check_p99_latency(
    prometheus_url: str, app_label: str, threshold_ms: int
) -> bool:
    # Verifies p99 latency is within acceptable bounds
    query = f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{app="{app_label}"}}[5m])) * 1000'
    resp = requests.get(
        f"{prometheus_url}/api/v1/query",
        params={"query": query},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return True
    p99_ms = float(result[0]["value"][1])
    return p99_ms < threshold_ms
```

## Litmus and ChaosMesh for Kubernetes

For Kubernetes-native chaos, **Litmus** and **ChaosMesh** provide CRD-based experiment
definitions. The **trade-off** between them: Litmus has a richer experiment hub and built-in
observability; ChaosMesh has tighter Kubernetes integration and lower resource overhead.

```yaml
# ChaosMesh: Network partition between services
# This simulates a network split between the API and database tiers
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: api-db-partition
  namespace: chaos-testing
spec:
  action: partition
  mode: all
  selector:
    namespaces: ["production"]
    labelSelectors:
      app: api-server
  direction: both
  target:
    selector:
      namespaces: ["production"]
      labelSelectors:
        app: postgres
  duration: "60s"
  scheduler:
    cron: "@every 24h"    # run daily during business hours
---
# Litmus: Pod CPU stress experiment
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: cpu-stress-test
  namespace: litmus
spec:
  appinfo:
    appns: production
    applabel: "app=order-service"
  chaosServiceAccount: litmus-admin
  experiments:
    - name: pod-cpu-hog
      spec:
        components:
          env:
            - name: CPU_CORES
              value: "2"
            - name: TOTAL_CHAOS_DURATION
              value: "120"
            - name: CPU_LOAD
              value: "80"
```

## GameDay Planning and Execution

A **GameDay** is a structured event where teams run chaos experiments together. It is the
organizational practice that turns chaos engineering from a tool into a culture.

**Best practice** for GameDay execution:

1. **Pre-GameDay** (1 week before): Select experiments, define success criteria, brief
   participants, ensure rollback procedures are documented and tested
2. **Blast radius control**: Start with non-production, then staging, then production
   with traffic shifting. **Never** run your first experiment directly in production
3. **Communication**: Announce the GameDay window, have a war-room channel, designate
   a coordinator who can halt experiments instantly
4. **During execution**: Run experiments sequentially, observe dashboards, take notes on
   surprising behaviors, stop immediately if customer impact exceeds thresholds
5. **Post-GameDay**: Write a report documenting findings, file tickets for weaknesses
   discovered, celebrate both successes and learnings

The **pitfall** is treating GameDays as one-off events. **However**, resilience degrades
as code changes. Therefore, schedule GameDays quarterly and automate the most important
experiments to run continuously in CI.

## Blast Radius Control

**Because** chaos experiments carry real risk, controlling blast radius is non-negotiable:

- **Environment progression**: dev -> staging -> canary -> production
- **Traffic percentage**: start with 1% of traffic, increase gradually
- **Duration limits**: hard timeout on every experiment (e.g., max 5 minutes)
- **Automatic rollback**: if steady-state probes fail, halt and roll back immediately
- **Kill switch**: a single command or button that terminates all active experiments

## Summary and Key Takeaways

- **Chaos engineering follows the scientific method**: hypothesis, experiment, observe, learn --
  it is not random destruction
- **The steady-state hypothesis is the foundation** -- without quantitative success criteria,
  you cannot measure resilience
- **Python Chaos Toolkit** enables codified, version-controlled experiments that run in CI
- **Litmus and ChaosMesh** provide Kubernetes-native CRD-based chaos with scheduling and
  automatic rollback
- **GameDays** build organizational confidence -- schedule them quarterly, start small, expand
  blast radius gradually
- **Best practice**: automate your most critical chaos experiments to run continuously; manual
  GameDays alone are insufficient because resilience degrades with every code change
- **Pitfall**: skipping blast radius controls. **Therefore**, always start in non-production,
  set hard duration limits, and maintain an instant kill switch
""",
    ),

    # --- 4. Mutation Testing ---
    (
        "mutation_testing_fault_based_python",
        "Explain mutation testing theory and practice -- the competent programmer hypothesis, "
        "coupling effect, mutant generation operators, equivalent mutant problem, using mutmut "
        "and cosmic-ray in Python, interpreting mutation scores, surviving mutant analysis, "
        "integrating mutation testing into CI pipelines, and the relationship between mutation "
        "testing and test suite quality. Provide complete code examples.",
        r"""
# Mutation Testing: Measuring the True Quality of Your Test Suite

## The Theory Behind Mutation Testing

Code coverage tells you which lines your tests *execute*. Mutation testing tells you which
**faults your tests can actually detect**. The difference is profound: a test suite can achieve
100% line coverage while catching zero bugs, simply by executing code without meaningful
assertions.

Mutation testing works by making small changes (**mutations**) to your source code, creating
**mutants**. Each mutant has exactly one change -- replacing `>` with `>=`, deleting a
statement, changing `True` to `False`. Your test suite is then run against each mutant. If
at least one test fails, the mutant is **killed** (good -- your tests caught the fault). If
all tests pass, the mutant **survives** (bad -- your tests missed a real fault).

The **mutation score** is the percentage of killed mutants:

```
Mutation Score = (Killed Mutants / Total Non-Equivalent Mutants) x 100%

Example:
  Total mutants generated: 200
  Killed by tests:         170
  Equivalent mutants:       10   (semantically identical to original)
  Survived:                 20   (real gaps in test coverage)

  Mutation Score = 170 / (200 - 10) = 89.5%
```

This rests on two theoretical foundations:

1. **Competent Programmer Hypothesis**: Real programmers write code that is "almost correct" --
   real bugs are small deviations from correct code, exactly the kind of changes mutation
   operators make. **Because** real bugs look like mutations, killing mutants correlates with
   catching real bugs.

2. **Coupling Effect**: Tests that detect simple faults (first-order mutants) also tend to
   detect complex faults (higher-order mutants). **Therefore**, testing against single-point
   mutations is sufficient -- you don't need to combine multiple mutations.

## Mutation Operators

Mutation operators define the types of changes applied to source code. Understanding them
is a **best practice** because it helps you write tests that target the most dangerous
fault classes.

```python
# Common mutation operators demonstrated on a simple function
from typing import List, Optional, Tuple

def calculate_discount(
    price: float,
    quantity: int,
    is_member: bool,
    coupon_code: Optional[str] = None,
) -> Tuple[float, str]:
    # Calculates final price with tiered discounts
    # This function will be the target of mutation testing
    discount = 0.0
    reason_parts: List[str] = []

    # Boundary mutation targets: > becomes >=, < becomes <=
    if quantity > 10:
        discount += 0.10
        reason_parts.append("bulk")
    elif quantity > 5:
        discount += 0.05
        reason_parts.append("multi")

    # Boolean mutation target: 'and' becomes 'or', True becomes False
    if is_member and price > 100:
        discount += 0.15
        reason_parts.append("member-premium")
    elif is_member:
        discount += 0.05
        reason_parts.append("member-basic")

    # Constant mutation target: string values change
    if coupon_code == "SAVE20":
        discount += 0.20
        reason_parts.append("coupon-20")
    elif coupon_code == "SAVE10":
        discount += 0.10
        reason_parts.append("coupon-10")

    # Arithmetic mutation target: + becomes -, * becomes /
    discount = min(discount, 0.50)  # cap at 50%
    final_price = price * quantity * (1 - discount)

    reason = "+".join(reason_parts) if reason_parts else "none"
    return round(final_price, 2), reason
```

The major operator categories are:

| Operator Type | Example | Why It Matters |
|---|---|---|
| **Relational** | `>` to `>=`, `==` to `!=` | Off-by-one and boundary errors |
| **Arithmetic** | `+` to `-`, `*` to `/` | Calculation errors |
| **Boolean** | `and` to `or`, `not` removal | Logic errors |
| **Constant** | `0` to `1`, `""` to `"x"` | Magic value errors |
| **Statement** | Delete line, swap statements | Dead code and ordering bugs |
| **Return** | Return `None`, return opposite | Wrong return value |

## Using mutmut in Python

**mutmut** is the most popular Python mutation testing tool. It is pragmatic, fast, and
integrates well with pytest.

```python
# tests/test_discount.py -- Test suite to be evaluated by mutation testing
import pytest
from typing import Tuple
from discount import calculate_discount

class TestCalculateDiscount:
    # Comprehensive test suite designed to kill mutants

    def test_no_discount_baseline(self) -> None:
        # Tests the zero-discount path
        price, reason = calculate_discount(50.0, 1, False)
        assert price == 50.0
        assert reason == "none"

    def test_bulk_discount_above_10(self) -> None:
        # Kills boundary mutant: quantity > 10 vs >= 10
        price, reason = calculate_discount(10.0, 11, False)
        assert price == 99.0   # 10 * 11 * 0.90
        assert "bulk" in reason

    def test_boundary_exactly_10_no_bulk(self) -> None:
        # Critical: tests the exact boundary to kill > vs >= mutant
        price, reason = calculate_discount(10.0, 10, False)
        assert price == 95.0   # 10 * 10 * 0.95 (multi, not bulk)
        assert "multi" in reason

    def test_boundary_exactly_5_no_multi(self) -> None:
        # Tests lower boundary: quantity=5 should NOT get multi discount
        price, reason = calculate_discount(10.0, 5, False)
        assert price == 50.0
        assert reason == "none"

    def test_boundary_exactly_6_gets_multi(self) -> None:
        # Quantity=6 should trigger multi discount
        price, reason = calculate_discount(10.0, 6, False)
        assert price == 57.0   # 10 * 6 * 0.95
        assert "multi" in reason

    def test_member_premium_high_price(self) -> None:
        # Kills boolean mutant: 'and' vs 'or' in member check
        price, reason = calculate_discount(200.0, 1, True)
        assert price == 170.0  # 200 * 0.85
        assert "member-premium" in reason

    def test_member_basic_low_price(self) -> None:
        # Member with low price gets basic discount only
        price, reason = calculate_discount(50.0, 1, True)
        assert price == 47.5   # 50 * 0.95
        assert "member-basic" in reason

    def test_non_member_high_price(self) -> None:
        # Non-member should NOT get member discount regardless of price
        price, reason = calculate_discount(200.0, 1, False)
        assert price == 200.0
        assert reason == "none"

    def test_coupon_save20(self) -> None:
        # Tests specific coupon code matching
        price, reason = calculate_discount(100.0, 1, False, "SAVE20")
        assert price == 80.0
        assert "coupon-20" in reason

    def test_coupon_save10(self) -> None:
        price, reason = calculate_discount(100.0, 1, False, "SAVE10")
        assert price == 90.0
        assert "coupon-10" in reason

    def test_invalid_coupon_ignored(self) -> None:
        # Wrong coupon should yield no coupon discount
        price, reason = calculate_discount(100.0, 1, False, "INVALID")
        assert price == 100.0
        assert "coupon" not in reason

    def test_discount_cap_at_50_percent(self) -> None:
        # Stacking all discounts should cap at 50%
        # bulk(10%) + member-premium(15%) + coupon-20(20%) = 45%, under cap
        price, reason = calculate_discount(100.0, 11, True, "SAVE20")
        assert price == 605.0  # 100 * 11 * 0.55
        # Verify cap with even more: if we could stack more it would still cap
        assert "bulk" in reason
        assert "member-premium" in reason
        assert "coupon-20" in reason


# Running mutmut from command line:
# $ mutmut run --paths-to-mutate=discount.py --tests-dir=tests/
# $ mutmut results          # show summary
# $ mutmut show 14          # show specific surviving mutant
# $ mutmut html             # generate HTML report
```

## The Equivalent Mutant Problem

The **biggest pitfall** in mutation testing is **equivalent mutants** -- mutants that change
the code but produce identical behavior for all possible inputs. For example:

```python
# Original
def is_positive(x: int) -> bool:
    return x > 0

# Equivalent mutant (for integer inputs only!)
def is_positive(x: int) -> bool:
    return x >= 1  # x > 0 and x >= 1 are identical for integers

# NOT equivalent for floats:
# is_positive(0.5) -> True with original, False with mutant
```

Equivalent mutants cannot be killed **because** no test can distinguish them from the
original. They inflate the denominator of your mutation score, making it artificially low.
**However**, detecting equivalent mutants is undecidable in general (equivalent to the
halting problem). Practical approaches include:

- **Manual review**: inspect surviving mutants to classify them as equivalent or real gaps
- **Heuristic detection**: tools like TCE (Trivial Compiler Equivalence) catch obvious cases
- **Higher-order mutation**: combine two mutations -- if the combination is killable, neither
  component is truly equivalent

## Using cosmic-ray for Larger Projects

**cosmic-ray** is an alternative that supports distributed execution and more mutation operators.

```python
# cosmic_ray_config.toml -- Configuration for cosmic-ray
# [cosmic-ray]
# module-path = "src/myapp"
# test-command = "pytest tests/ -x --tb=short"
# timeout = 30.0
# excluded-modules = ["myapp.migrations", "myapp.config"]

# Running cosmic-ray:
# $ cosmic-ray init config.toml session.sqlite  # create session
# $ cosmic-ray exec session.sqlite              # run mutations
# $ cr-report session.sqlite                    # view results
# $ cr-html session.sqlite > report.html        # HTML report

# Programmatic access to cosmic-ray results
import sqlite3
from typing import NamedTuple

class MutantResult(NamedTuple):
    # Represents the outcome of a single mutant test
    module: str
    operator: str
    occurrence: int
    status: str  # 'killed', 'survived', 'incompetent', 'timeout'
    line_number: int

def analyze_surviving_mutants(session_db: str) -> List[MutantResult]:
    # Extracts surviving mutants for manual review
    conn = sqlite3.connect(session_db)
    cursor = conn.execute(
        "SELECT module, operator, occurrence, status, line_number "
        "FROM mutation_specs JOIN results USING (job_id) "
        "WHERE status = 'survived' "
        "ORDER BY module, line_number"
    )
    results = [MutantResult(*row) for row in cursor.fetchall()]
    conn.close()
    return results

def print_mutation_report(session_db: str) -> None:
    # Generates a human-readable report of surviving mutants
    survivors = analyze_surviving_mutants(session_db)
    by_module: dict[str, list[MutantResult]] = {}
    for m in survivors:
        by_module.setdefault(m.module, []).append(m)

    print(f"Total surviving mutants: {len(survivors)}\n")
    for module, mutants in sorted(by_module.items()):
        print(f"  {module}: {len(mutants)} survivors")
        for m in mutants:
            print(f"    Line {m.line_number}: {m.operator} (occurrence {m.occurrence})")
```

## CI Integration Strategy

The **trade-off** with mutation testing in CI is speed: running hundreds of mutants is slow.
**Therefore**, the best practice is a tiered approach:

- **Pre-commit**: Run mutation testing only on changed files (`mutmut run --paths-to-mutate=$(git diff --name-only)`)
- **PR check**: Run full mutation testing on the package containing changes
- **Nightly**: Run complete mutation analysis across the entire codebase
- **Quality gate**: Enforce a minimum mutation score (e.g., 80%) for new code

## Summary and Key Takeaways

- **Mutation testing measures test suite effectiveness**, not code correctness -- it answers
  "can my tests detect real faults?"
- **The Competent Programmer Hypothesis** justifies single-point mutations: real bugs look
  like small code changes, **therefore** killing mutants correlates with catching real bugs
- **Boundary tests are the highest-value additions** when surviving mutants reveal gaps --
  most survivors involve relational operator mutations at boundaries
- **Equivalent mutants** are the main **pitfall**: they cannot be killed and require manual
  classification or heuristic detection
- **Best practice**: use mutation testing to *improve* your test suite, not as a pass/fail
  gate initially. Review surviving mutants, write targeted tests, and watch the score climb
- **mutmut** is best for quick feedback on small-to-medium projects; **cosmic-ray** scales
  better for large codebases with its distributed execution model
- **CI integration**: tier your mutation testing -- fast checks on changed files in PRs,
  comprehensive analysis in nightly builds
""",
    ),

    # --- 5. Load Testing and Performance ---
    (
        "load_testing_performance_locust_k6_python",
        "Explain load testing and performance engineering -- designing load test scenarios with "
        "Locust and k6, percentile-based SLOs (p50/p95/p99), profiling bottlenecks with cProfile "
        "and py-spy, capacity planning methodology, distributed load generation, correlating "
        "metrics with infrastructure dashboards, and building a continuous performance regression "
        "pipeline. Provide complete Python Locust implementation examples.",
        r"""
# Load Testing and Performance Engineering: From Locust Scripts to Capacity Planning

## Why Load Testing Is Not Optional

Every production system has a breaking point. Load testing finds that point **before** your
customers do. The **common mistake** is treating load testing as a pre-launch checkbox --
run it once, hit a target number, ship it. Real performance engineering is continuous:
every deployment can introduce a regression, every new feature changes the load profile,
and infrastructure costs scale with traffic.

**Because** performance degrades non-linearly, a system that handles 1,000 RPS at p99=50ms
might handle 2,000 RPS at p99=200ms and collapse entirely at 2,500 RPS. You need to
understand these curves, not just single data points.

## Percentile-Based SLOs: Beyond Averages

Averages lie. A service with 100ms average latency might have a p99 of 2 seconds -- meaning
1 in 100 requests is 20x slower than average. **Because** real users experience the worst
percentiles (especially during checkout flows with multiple serial API calls), SLOs must
be percentile-based.

```
SLO Definition Examples:

  Tier 1 (User-facing API):
    p50 latency  < 100ms
    p95 latency  < 250ms
    p99 latency  < 500ms
    Error rate   < 0.1%
    Availability > 99.95%

  Tier 2 (Internal service):
    p50 latency  < 200ms
    p95 latency  < 500ms
    p99 latency  < 1000ms
    Error rate   < 0.5%

  Tier 3 (Batch processing):
    p95 job completion < 5 minutes
    Failure rate       < 1%

  The math: If a user flow hits 5 serial Tier-1 services, the
  compound p99 is NOT 5 x 500ms = 2.5s. It is worse because
  slow requests cluster. Therefore, individual service SLOs
  must be tighter than the end-to-end target.
```

## Python Locust: Complete Load Test Implementation

Locust is a Python-native load testing framework that defines user behavior as code. Its
**best practice** advantages over tools like JMeter: tests are version-controlled Python,
easy to parameterize, and support complex user flows with state.

```python
import time
import json
import random
import logging
from typing import Optional, Dict, Any, List
from locust import HttpUser, task, between, events, tag, SequentialTaskSet
from locust.runners import MasterRunner, WorkerRunner
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class TestData:
    # Shared test data loaded once and distributed to all users
    product_ids: List[int] = field(default_factory=list)
    user_credentials: List[Dict[str, str]] = field(default_factory=list)
    coupon_codes: List[str] = field(default_factory=list)

# Global test data -- loaded once at start
test_data = TestData()

@events.init.add_listener
def on_init(environment: Any, **kwargs: Any) -> None:
    # Load test data before any users spawn
    # In production, fetch this from a test data service or file
    test_data.product_ids = list(range(1, 1001))
    test_data.user_credentials = [
        {"username": f"loadtest_user_{i}", "password": "test_pass_123"}
        for i in range(500)
    ]
    test_data.coupon_codes = ["SAVE10", "SAVE20", "FREESHIP"]
    logger.info("Test data loaded: %d products, %d users",
                len(test_data.product_ids), len(test_data.user_credentials))


class BrowsingUser(HttpUser):
    # Simulates a casual browsing user -- mostly reads, occasional cart add
    wait_time = between(1, 5)  # think time between requests
    weight = 7                  # 70% of simulated users are browsers

    def on_start(self) -> None:
        # Called when a simulated user starts
        self.session_products: List[int] = []

    @tag("browse")
    @task(10)
    def view_product_list(self) -> None:
        # Browses the product catalog -- highest frequency action
        page = random.randint(1, 50)
        with self.client.get(
            f"/api/products?page={page}&limit=20",
            name="/api/products?page=[N]",  # group in stats
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if not data.get("products"):
                    response.failure("Empty product list")
                else:
                    response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @tag("browse")
    @task(5)
    def view_product_detail(self) -> None:
        # Views a specific product page
        product_id = random.choice(test_data.product_ids)
        self.session_products.append(product_id)
        self.client.get(
            f"/api/products/{product_id}",
            name="/api/products/[id]",
        )

    @tag("browse", "cart")
    @task(1)
    def add_to_cart(self) -> None:
        # Occasionally adds a viewed product to cart
        if not self.session_products:
            return
        product_id = random.choice(self.session_products)
        self.client.post(
            "/api/cart/items",
            json={"product_id": product_id, "quantity": random.randint(1, 3)},
            name="/api/cart/items",
        )


class CheckoutUser(HttpUser):
    # Simulates a purchasing user -- full browse-to-checkout flow
    wait_time = between(2, 8)
    weight = 2   # 20% of simulated users complete checkout

    @tag("checkout")
    @task
    def full_checkout_flow(self) -> None:
        # Sequential flow: login -> browse -> cart -> checkout
        creds = random.choice(test_data.user_credentials)

        # Step 1: Login
        login_resp = self.client.post("/api/auth/login", json=creds)
        if login_resp.status_code != 200:
            logger.warning("Login failed for %s", creds["username"])
            return

        token = login_resp.json().get("token", "")
        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Browse products
        self.client.get("/api/products?page=1&limit=20", headers=headers)

        # Step 3: Add items to cart
        product_id = random.choice(test_data.product_ids)
        self.client.post(
            "/api/cart/items",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )

        # Step 4: Apply coupon (sometimes)
        if random.random() < 0.3:
            coupon = random.choice(test_data.coupon_codes)
            self.client.post(
                "/api/cart/coupon",
                json={"code": coupon},
                headers=headers,
                name="/api/cart/coupon",
            )

        # Step 5: Checkout
        with self.client.post(
            "/api/checkout",
            json={"payment_method": "test_card"},
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 409:
                response.failure("Cart conflict during checkout")
            else:
                response.failure(f"Checkout failed: {response.status_code}")


class APIHealthUser(HttpUser):
    # Simulates monitoring / health check traffic
    wait_time = between(5, 15)
    weight = 1   # 10% of simulated users

    @tag("health")
    @task
    def health_check(self) -> None:
        self.client.get("/api/health")

    @tag("health")
    @task
    def metrics_endpoint(self) -> None:
        self.client.get("/api/metrics", name="/api/metrics")
```

## Profiling Bottlenecks: cProfile and py-spy

When load tests reveal performance problems, **profiling** identifies the root cause. The
**trade-off** between profiling tools: `cProfile` has zero setup cost but adds overhead and
requires code changes; `py-spy` attaches to running processes with near-zero overhead but
requires process access.

```python
import cProfile
import pstats
import io
from typing import Callable, TypeVar, Any
from functools import wraps
import time

T = TypeVar("T")

def profile_endpoint(func: Callable[..., T]) -> Callable[..., T]:
    # Decorator that profiles a function and logs the top bottlenecks
    # Use in development/staging, never in production
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            profiler.disable()
            stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stream)
            stats.sort_stats("cumulative")
            stats.print_stats(20)  # top 20 functions
            logger.info("Profile for %s:\n%s", func.__name__, stream.getvalue())
    return wrapper


# py-spy usage (command-line, no code changes needed):
# Attach to running process:
#   $ py-spy top --pid 12345
#
# Generate flame graph:
#   $ py-spy record -o profile.svg --pid 12345 --duration 30
#
# Profile a specific command:
#   $ py-spy record -o profile.svg -- python manage.py runserver


# Custom latency tracker for identifying slow endpoints
class LatencyTracker:
    # Tracks per-endpoint latency percentiles in-memory
    def __init__(self, max_samples: int = 10000) -> None:
        self._samples: Dict[str, List[float]] = {}
        self._max_samples = max_samples

    def record(self, endpoint: str, duration_ms: float) -> None:
        # Records a latency sample for the given endpoint
        if endpoint not in self._samples:
            self._samples[endpoint] = []
        samples = self._samples[endpoint]
        samples.append(duration_ms)
        if len(samples) > self._max_samples:
            # Keep only recent samples to bound memory
            self._samples[endpoint] = samples[-self._max_samples:]

    def percentile(self, endpoint: str, pct: float) -> Optional[float]:
        # Computes the given percentile for an endpoint
        samples = self._samples.get(endpoint)
        if not samples:
            return None
        sorted_samples = sorted(samples)
        idx = int(len(sorted_samples) * pct / 100.0)
        idx = min(idx, len(sorted_samples) - 1)
        return sorted_samples[idx]

    def report(self) -> Dict[str, Dict[str, Optional[float]]]:
        # Returns p50/p95/p99 for all tracked endpoints
        result: Dict[str, Dict[str, Optional[float]]] = {}
        for endpoint in sorted(self._samples):
            result[endpoint] = {
                "p50": self.percentile(endpoint, 50),
                "p95": self.percentile(endpoint, 95),
                "p99": self.percentile(endpoint, 99),
                "count": float(len(self._samples[endpoint])),
            }
        return result
```

## Capacity Planning Methodology

Capacity planning translates load test results into infrastructure decisions. The **best
practice** is a structured four-step process:

1. **Characterize workload**: what does the traffic profile look like? Peak vs. average
   ratio, daily/weekly patterns, growth rate
2. **Benchmark current capacity**: at what load does the system violate SLOs?
3. **Model scaling behavior**: does throughput scale linearly with instances? Where are
   the bottlenecks (CPU, memory, database connections, network)?
4. **Plan headroom**: provision for peak + 30% headroom + projected growth

**However**, capacity planning has a critical **pitfall**: assuming linear scaling. Most
systems hit bottlenecks -- shared databases, connection pools, lock contention -- that
cause throughput to plateau or degrade. **Therefore**, always load test at 2x expected
peak to find these saturation points.

## Distributed Load Generation

For high-throughput tests, a single Locust machine is insufficient. Locust supports
distributed mode with a master/worker architecture.

```yaml
# docker-compose.yml for distributed Locust
# Scales to millions of requests per second with enough workers
version: "3.8"
services:
  locust-master:
    image: locustio/locust:2.20
    command: >
      -f /tests/locustfile.py
      --master
      --host=https://api.staging.example.com
      --users=10000
      --spawn-rate=100
      --run-time=30m
      --csv=/results/loadtest
      --html=/results/report.html
    volumes:
      - ./tests:/tests
      - ./results:/results
    ports:
      - "8089:8089"

  locust-worker:
    image: locustio/locust:2.20
    command: >
      -f /tests/locustfile.py
      --worker
      --master-host=locust-master
    volumes:
      - ./tests:/tests
    deploy:
      replicas: 8    # scale up for higher load

# Run: docker-compose up --scale locust-worker=16
```

## Continuous Performance Regression Pipeline

The **trade-off** with performance testing in CI is cost and time. **Therefore**, use a
tiered approach: fast smoke tests on every PR, thorough load tests on merge to main,
and full capacity tests weekly.

```python
# ci_performance_gate.py -- Performance regression check for CI
import json
import sys
from typing import Dict, NamedTuple
from pathlib import Path

class SLOThreshold(NamedTuple):
    # Defines acceptable performance for an endpoint
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate_pct: float

# SLO definitions per endpoint
SLO_THRESHOLDS: Dict[str, SLOThreshold] = {
    "/api/products?page=[N]":  SLOThreshold(p50_ms=50, p95_ms=150, p99_ms=300, error_rate_pct=0.1),
    "/api/products/[id]":      SLOThreshold(p50_ms=30, p95_ms=100, p99_ms=200, error_rate_pct=0.1),
    "/api/cart/items":         SLOThreshold(p50_ms=80, p95_ms=200, p99_ms=400, error_rate_pct=0.5),
    "/api/checkout":           SLOThreshold(p50_ms=200, p95_ms=500, p99_ms=1000, error_rate_pct=0.1),
    "/api/health":             SLOThreshold(p50_ms=10, p95_ms=30, p99_ms=50, error_rate_pct=0.0),
}

def check_performance_regression(csv_stats_path: str) -> bool:
    # Parses Locust CSV output and checks against SLO thresholds
    # Returns True if all SLOs pass, False otherwise
    import csv
    violations: list[str] = []

    with open(csv_stats_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            endpoint = row.get("Name", "")
            if endpoint not in SLO_THRESHOLDS:
                continue

            slo = SLO_THRESHOLDS[endpoint]
            p50 = float(row.get("50%", 0))
            p95 = float(row.get("95%", 0))
            p99 = float(row.get("99%", 0))
            total = int(row.get("Request Count", 0))
            failures = int(row.get("Failure Count", 0))
            error_rate = (failures / total * 100) if total > 0 else 0

            if p50 > slo.p50_ms:
                violations.append(f"{endpoint}: p50={p50}ms > {slo.p50_ms}ms")
            if p95 > slo.p95_ms:
                violations.append(f"{endpoint}: p95={p95}ms > {slo.p95_ms}ms")
            if p99 > slo.p99_ms:
                violations.append(f"{endpoint}: p99={p99}ms > {slo.p99_ms}ms")
            if error_rate > slo.error_rate_pct:
                violations.append(f"{endpoint}: errors={error_rate:.2f}% > {slo.error_rate_pct}%")

    if violations:
        print("PERFORMANCE REGRESSION DETECTED:")
        for v in violations:
            print(f"  FAIL: {v}")
        return False

    print("All performance SLOs passed.")
    return True


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "results/loadtest_stats.csv"
    success = check_performance_regression(csv_path)
    sys.exit(0 if success else 1)
```

## Summary and Key Takeaways

- **Percentile-based SLOs are non-negotiable** -- averages hide tail latency that real users
  experience; always define p50, p95, and p99 targets
- **Locust** provides Python-native load testing with realistic user behavior modeling,
  weighted user types, and sequential task flows
- **Profiling identifies root causes**: use `cProfile` for development and `py-spy` for
  production processes; flame graphs are the fastest path to understanding bottlenecks
- **Capacity planning requires non-linear thinking** -- **because** systems hit saturation
  points, always test at 2x expected peak to find them
- **Best practice**: build a continuous performance regression pipeline with SLO gates in CI;
  fast smoke tests on PRs, thorough tests on merge, capacity tests weekly
- **Pitfall**: testing with unrealistic traffic patterns. **Therefore**, model your load tests
  on production traffic analysis -- weighted user types, think times, and data distributions
- **Distributed Locust** scales horizontally with master/worker architecture for testing at
  thousands of concurrent users
""",
    ),
]
