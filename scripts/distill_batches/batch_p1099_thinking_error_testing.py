"""Thinking-trace pairs: error testing strategies."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How do I implement chaos engineering in my Python services to test error handling? I want to systematically inject failures to find weaknesses before they hit production.''',
        r'''<think>
Chaos engineering -- the user wants to systematically inject failures.
My first thought is to point them at Netflix's Chaos Monkey, but wait,
that operates at the infrastructure level (killing VMs). They said
"Python services," so they probably want code-level fault injection
they can run in tests or staging, not infrastructure-level chaos.

Let me think about what kinds of faults matter here:
1. Fault injection (network errors, latency, exceptions)
2. Controlled blast radius (don't break production for real)
3. Hypothesis-driven experiments ("we believe X will happen when Y fails")
4. Automated chaos with safety controls (kill switch, rollback)
5. Observability during chaos (metrics, logs)

I considered just showing unittest.mock patches that raise exceptions,
but actually that is too narrow -- real chaos engineering needs a
framework that can inject faults probabilistically at runtime, not
just in test mocks. Since they mentioned "before they hit production,"
they need something that runs in staging with real traffic patterns.

Hmm, should I use decorators or middleware? Decorators are more
Pythonic and can target specific functions, whereas middleware only
works at the request level. Actually, decorators make more sense
because they can wrap any function -- database calls, HTTP clients,
internal services -- not just request handlers.

I should show practical fault injection decorators and a chaos
experiment framework with a kill switch, not just theory.
</think>

Chaos engineering systematically verifies error handling by injecting controlled failures. Here is a practical framework:

```python
import random
import time
import functools
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any
from contextlib import contextmanager


# ============================================================
# FAULT INJECTION TYPES
# ============================================================

class FaultType(Enum):
    EXCEPTION = "exception"       # Raise an exception
    LATENCY = "latency"           # Add artificial delay
    RETURN_ERROR = "return_error"  # Return an error value
    TIMEOUT = "timeout"           # Simulate timeout (very long delay)
    CORRUPTION = "corruption"     # Return corrupted/wrong data


@dataclass
class FaultConfig:
    fault_type: FaultType
    probability: float = 0.1     # 0.0 to 1.0
    exception_class: type = RuntimeError
    exception_message: str = "Chaos fault injected"
    latency_ms: int = 5000
    error_value: Any = None
    enabled: bool = True


# ============================================================
# CHAOS CONTROLLER
# ============================================================

class ChaosController:
    """Central controller for all chaos experiments.

    Provides a kill switch and per-function fault configuration.
    """

    def __init__(self):
        self._faults: dict[str, FaultConfig] = {}
        self._enabled = False
        self._lock = threading.Lock()
        self._stats: dict[str, dict] = {}

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        """Kill switch -- immediately stops all fault injection."""
        self._enabled = False

    def register_fault(self, name: str, config: FaultConfig):
        with self._lock:
            self._faults[name] = config
            self._stats[name] = {"injected": 0, "skipped": 0, "total": 0}

    def remove_fault(self, name: str):
        with self._lock:
            self._faults.pop(name, None)

    def should_inject(self, name: str) -> Optional[FaultConfig]:
        """Check if a fault should be injected for the given function."""
        if not self._enabled:
            return None

        with self._lock:
            config = self._faults.get(name)
            if not config or not config.enabled:
                return None

            self._stats[name]["total"] += 1

            if random.random() < config.probability:
                self._stats[name]["injected"] += 1
                return config
            else:
                self._stats[name]["skipped"] += 1
                return None

    def inject(self, config: FaultConfig):
        """Actually perform the fault injection."""
        if config.fault_type == FaultType.EXCEPTION:
            raise config.exception_class(config.exception_message)

        elif config.fault_type == FaultType.LATENCY:
            time.sleep(config.latency_ms / 1000.0)

        elif config.fault_type == FaultType.TIMEOUT:
            time.sleep(30.0)  # Simulate a hung connection

        elif config.fault_type == FaultType.RETURN_ERROR:
            return config.error_value

        elif config.fault_type == FaultType.CORRUPTION:
            return config.error_value  # Caller returns wrong data

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)


# Global controller
chaos = ChaosController()


# ============================================================
# DECORATOR FOR FAULT INJECTION
# ============================================================

def chaos_point(name: str):
    """Decorator that marks a function as a chaos injection point.

    Usage:
        @chaos_point("database.query")
        def query_database(sql):
            ...

    Then register faults:
        chaos.register_fault("database.query", FaultConfig(
            fault_type=FaultType.EXCEPTION,
            probability=0.3,
            exception_class=ConnectionError,
        ))
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            config = chaos.should_inject(name)
            if config:
                if config.fault_type in (FaultType.RETURN_ERROR,
                                          FaultType.CORRUPTION):
                    return chaos.inject(config)
                elif config.fault_type == FaultType.LATENCY:
                    chaos.inject(config)  # Add delay, then continue
                else:
                    chaos.inject(config)  # Raises exception

            return func(*args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def chaos_experiment(name: str, faults: dict[str, FaultConfig]):
    """Context manager for running a chaos experiment.

    Registers faults, enables chaos, runs the experiment,
    then cleans up -- even if the experiment crashes.

    Usage:
        faults = {
            "database.query": FaultConfig(FaultType.LATENCY, 0.5, latency_ms=3000),
            "cache.get": FaultConfig(FaultType.EXCEPTION, 0.3),
        }
        with chaos_experiment("test_db_slowdown", faults):
            run_load_test()
    """
    # Register all faults
    for fault_name, config in faults.items():
        chaos.register_fault(fault_name, config)

    chaos.enable()
    print(f"Chaos experiment '{name}' started with {len(faults)} fault points")

    try:
        yield chaos
    finally:
        chaos.disable()
        stats = chaos.get_stats()
        print(f"Chaos experiment '{name}' ended")
        for fault_name in faults:
            s = stats.get(fault_name, {})
            print(f"  {fault_name}: {s.get('injected', 0)} injected / "
                  f"{s.get('total', 0)} total calls")
            chaos.remove_fault(fault_name)


# ============================================================
# EXAMPLE: INSTRUMENTED SERVICE
# ============================================================

@chaos_point("database.query")
def query_database(sql: str) -> list[dict]:
    """Simulated database query."""
    return [{"id": 1, "name": "Alice"}]


@chaos_point("cache.get")
def cache_get(key: str) -> Optional[str]:
    """Simulated cache lookup."""
    return None  # Cache miss


@chaos_point("external_api.call")
def call_external_api(endpoint: str) -> dict:
    """Simulated external API call."""
    return {"status": "ok"}


def handle_request(user_id: str) -> dict:
    """Request handler with error handling we want to test."""
    # Try cache first
    try:
        cached = cache_get(f"user:{user_id}")
        if cached:
            return {"source": "cache", "data": cached}
    except Exception:
        pass  # Cache failure should not break the request

    # Fall back to database
    try:
        rows = query_database(f"SELECT * FROM users WHERE id = '{user_id}'")
        return {"source": "database", "data": rows}
    except Exception as exc:
        # Database failure -- try external API as last resort
        try:
            result = call_external_api(f"/users/{user_id}")
            return {"source": "external_api", "data": result}
        except Exception:
            return {"source": "error", "error": "All data sources failed"}


# ============================================================
# RUN A CHAOS EXPERIMENT
# ============================================================

faults = {
    "database.query": FaultConfig(
        fault_type=FaultType.EXCEPTION,
        probability=0.5,
        exception_class=ConnectionError,
        exception_message="Database connection refused",
    ),
    "cache.get": FaultConfig(
        fault_type=FaultType.LATENCY,
        probability=0.3,
        latency_ms=2000,
    ),
}

with chaos_experiment("test_db_failover", faults):
    results = {"database": 0, "cache": 0, "external_api": 0, "error": 0}
    for i in range(100):
        result = handle_request(f"user-{i}")
        results[result["source"]] += 1

    print(f"Results: {results}")
    # With 50% DB failure rate, we should see a mix of database
    # and external_api sources. If "error" count is high,
    # our fallback logic has a bug.
```

**Chaos experiment checklist:**

1. **State your hypothesis** before running: "If the database fails 50% of the time, all requests should still succeed via the external API fallback"
2. **Start small**: 10% failure rate in staging, not 100% in production
3. **Always have a kill switch**: `chaos.disable()` stops everything instantly
4. **Measure during chaos**: track success rates, latency percentiles, error rates
5. **Automate and repeat**: chaos tests should run in CI, not just as one-off experiments''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement fault injection for testing in Python without modifying the production code too much? I want to test error paths in unit tests and integration tests.''',
        r'''<think>
The user wants to write tests that exercise error paths. My first
instinct is to just show unittest.mock.patch, but wait -- that only
covers one approach, and mocking can become brittle when the internal
implementation changes. Let me think about what actually works well.

Approaches I know:
1. unittest.mock.patch to replace functions with error-raising ones
2. Dependency injection (pass error-raising implementations)
3. Context managers that temporarily break things
4. Monkey-patching at the module level
5. Custom test fixtures

I considered recommending dependency injection as the primary pattern
since it is the most testable architecture. But actually, most existing
codebases are not built with DI in mind, so the user probably has
tightly coupled code they need to test right now. Therefore I should
show mock.patch for the immediate fix, then show DI as the cleaner
long-term approach.

Hmm, should I use pytest fixtures or plain context managers? Since
they are likely already using pytest (it is the de facto standard),
pytest fixtures with yield would be the most natural fit because
they handle setup and teardown automatically. Plain context managers
could work too, but fixtures compose better.

The key is making error paths testable without cluttering production
code. I should show practical patterns for pytest with both approaches.
</think>

Test-time fault injection should be clean, targeted, and not require modifying production code. Here are the key patterns:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import contextmanager
from typing import Any, Callable
import socket
import time


# ============================================================
# THE PRODUCTION CODE WE WANT TO TEST
# ============================================================

class UserService:
    def __init__(self, db, cache, email_client):
        self.db = db
        self.cache = cache
        self.email_client = email_client

    def get_user(self, user_id: str) -> dict:
        # Try cache
        try:
            cached = self.cache.get(f"user:{user_id}")
            if cached:
                return cached
        except Exception:
            pass  # Cache failure is non-fatal

        # Database lookup
        user = self.db.find_one("users", {"id": user_id})
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Cache the result (best effort)
        try:
            self.cache.set(f"user:{user_id}", user, ttl=300)
        except Exception:
            pass  # Cache write failure is non-fatal

        return user

    def create_user(self, data: dict) -> dict:
        user = self.db.insert("users", data)
        try:
            self.email_client.send_welcome(user["email"])
        except Exception:
            # Log but don't fail -- user was created successfully
            pass
        return user


# ============================================================
# PATTERN 1: DEPENDENCY INJECTION WITH FAKES
# ============================================================

class FaultyDatabase:
    """A database fake that fails in configurable ways."""

    def __init__(self):
        self._fault: str = None
        self._fault_count: int = 0
        self._call_count: int = 0
        self._data: dict = {}

    def set_fault(self, fault_type: str, count: int = -1):
        """Configure a fault. count=-1 means fail forever."""
        self._fault = fault_type
        self._fault_count = count

    def clear_fault(self):
        self._fault = None

    def _maybe_fault(self):
        if self._fault is None:
            return
        if self._fault_count == 0:
            self._fault = None
            return

        if self._fault_count > 0:
            self._fault_count -= 1

        if self._fault == "connection_error":
            raise ConnectionError("Database connection refused")
        elif self._fault == "timeout":
            raise TimeoutError("Query timed out after 30s")
        elif self._fault == "integrity":
            raise Exception("IntegrityError: duplicate key")
        elif self._fault == "slow":
            time.sleep(5)

    def find_one(self, collection: str, query: dict) -> dict:
        self._call_count += 1
        self._maybe_fault()
        key = f"{collection}:{query.get('id', '')}"
        return self._data.get(key)

    def insert(self, collection: str, data: dict) -> dict:
        self._call_count += 1
        self._maybe_fault()
        data["id"] = data.get("id", f"generated-{self._call_count}")
        self._data[f"{collection}:{data['id']}"] = data
        return data


class FaultyCache:
    """A cache fake with configurable failures."""

    def __init__(self):
        self._data = {}
        self._get_fault = None
        self._set_fault = None

    def fail_on_get(self, error: Exception = None):
        self._get_fault = error or ConnectionError("Redis down")

    def fail_on_set(self, error: Exception = None):
        self._set_fault = error or ConnectionError("Redis down")

    def get(self, key: str) -> Any:
        if self._get_fault:
            raise self._get_fault
        return self._data.get(key)

    def set(self, key: str, value: Any, ttl: int = 0):
        if self._set_fault:
            raise self._set_fault
        self._data[key] = value


# ============================================================
# PATTERN 2: PYTEST FIXTURES WITH FAULT INJECTION
# ============================================================

@pytest.fixture
def faulty_db():
    return FaultyDatabase()

@pytest.fixture
def faulty_cache():
    return FaultyCache()

@pytest.fixture
def mock_email():
    return MagicMock()

@pytest.fixture
def user_service(faulty_db, faulty_cache, mock_email):
    return UserService(faulty_db, faulty_cache, mock_email)


class TestUserServiceErrorPaths:
    """Test that error handling works correctly."""

    def test_cache_failure_falls_back_to_db(self, user_service, faulty_db, faulty_cache):
        """When cache fails, service should still return data from DB."""
        faulty_db.insert("users", {"id": "u1", "name": "Alice"})
        faulty_cache.fail_on_get(ConnectionError("Redis timeout"))

        user = user_service.get_user("u1")
        assert user["name"] == "Alice"

    def test_cache_write_failure_does_not_break_response(
            self, user_service, faulty_db, faulty_cache):
        """Cache write failure should not affect the returned user."""
        faulty_db.insert("users", {"id": "u1", "name": "Alice"})
        faulty_cache.fail_on_set(ConnectionError("Redis full"))

        user = user_service.get_user("u1")
        assert user["name"] == "Alice"

    def test_db_failure_raises_appropriate_error(
            self, user_service, faulty_db):
        """Database failure should propagate as a clear error."""
        faulty_db.set_fault("connection_error")

        with pytest.raises(ConnectionError, match="connection refused"):
            user_service.get_user("u1")

    def test_email_failure_does_not_prevent_user_creation(
            self, user_service, mock_email):
        """Email send failure should not roll back user creation."""
        mock_email.send_welcome.side_effect = ConnectionError("SMTP down")

        user = user_service.create_user({"email": "bob@example.com"})
        assert user["email"] == "bob@example.com"
        mock_email.send_welcome.assert_called_once()

    def test_transient_db_failure_then_recovery(
            self, user_service, faulty_db):
        """DB fails twice then recovers -- third call should work."""
        faulty_db.insert("users", {"id": "u1", "name": "Alice"})
        faulty_db.set_fault("connection_error", count=2)

        # First two calls fail
        with pytest.raises(ConnectionError):
            user_service.get_user("u1")
        with pytest.raises(ConnectionError):
            user_service.get_user("u1")

        # Third call succeeds (fault exhausted)
        user = user_service.get_user("u1")
        assert user["name"] == "Alice"


# ============================================================
# PATTERN 3: NETWORK-LEVEL FAULT INJECTION
# ============================================================

@contextmanager
def simulate_network_failure(target_host: str = None):
    """Block network connections during the test.

    Uses monkey-patching on socket.create_connection.
    """
    original_connect = socket.create_connection

    def failing_connect(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if target_host is None or host == target_host:
            raise ConnectionRefusedError(
                f"Simulated network failure to {host}"
            )
        return original_connect(address, *args, **kwargs)

    with patch("socket.create_connection", side_effect=failing_connect):
        yield


@contextmanager
def simulate_slow_network(delay_seconds: float = 2.0):
    """Add latency to all network connections."""
    original_connect = socket.create_connection

    def slow_connect(address, *args, **kwargs):
        time.sleep(delay_seconds)
        return original_connect(address, *args, **kwargs)

    with patch("socket.create_connection", side_effect=slow_connect):
        yield


# Usage in tests:
# def test_handles_network_failure():
#     with simulate_network_failure("database.internal"):
#         result = my_service.handle_request(data)
#         assert result["status"] == "degraded"


# ============================================================
# PATTERN 4: MOCK SIDE EFFECTS FOR COMPLEX SEQUENCES
# ============================================================

def test_retry_then_succeed():
    """Test that retry logic works by failing N times then succeeding."""
    db = MagicMock()
    db.find_one.side_effect = [
        ConnectionError("attempt 1"),
        ConnectionError("attempt 2"),
        {"id": "u1", "name": "Alice"},  # Third attempt succeeds
    ]

    # If your code has retry logic, it should survive 2 failures
    # and return the result from the third attempt


def test_different_errors_on_each_call():
    """Test handling of different error types in sequence."""
    api = MagicMock()
    api.call.side_effect = [
        TimeoutError("request 1 timed out"),
        ConnectionError("request 2 connection refused"),
        ValueError("request 3 invalid response"),
        {"status": "ok"},  # Fourth attempt succeeds
    ]


# ============================================================
# PATTERN 5: PARAMETRIZED ERROR TESTING
# ============================================================

@pytest.mark.parametrize("error_class,error_msg,expected_status", [
    (ConnectionError, "refused", "connection_error"),
    (TimeoutError, "timed out", "timeout"),
    (ValueError, "invalid", "bad_data"),
    (PermissionError, "denied", "auth_error"),
    (OSError, "disk full", "system_error"),
])
def test_error_classification(error_class, error_msg, expected_status):
    """Verify that different exception types map to correct error categories."""
    # classifier = ErrorClassifier()
    # result = classifier.classify(error_class(error_msg))
    # assert result == expected_status
    pass
```

**Fault injection testing principles:**

1. **Dependency injection over monkey-patching**: pass fakes through constructors, not by patching globals -- it is safer and more explicit
2. **Configurable fakes over mocks**: `FaultyDatabase` with `set_fault()` is easier to reason about than complex `side_effect` chains
3. **Test the boundaries**: cache failure, DB failure, email failure, network failure -- each should be tested independently
4. **Test recovery**: not just "does it fail gracefully" but "does it recover when the fault clears"
5. **Parametrize error types**: use `@pytest.mark.parametrize` to verify all exception types are handled correctly without writing N separate tests''',
    ),
    (
        "thinking/error-handling",
        r'''How do I measure error path code coverage? I suspect many of my except blocks are never tested. How do I find and test them?''',
        r'''<think>
The user wants to find untested error paths. My first thought is just
"run coverage.py," but wait -- standard line coverage does not tell
you much about error handling. A line inside an except block might be
"covered" because one test triggers it, but that does not mean every
exception type or every failure mode is tested.

Let me think about what actually reveals error-handling gaps:
1. Coverage.py with branch coverage -- this is better than line
   coverage because it shows whether both the try and except branches
   were taken. But it still does not tell you if the RIGHT exception
   was caught.
2. Finding untested except blocks specifically
3. Mutation testing -- this could be the most revealing approach,
   since it actually changes error-handling code and checks if tests
   notice. But hmm, mutation testing is slow and might be overkill
   for a first pass.
4. Static analysis to find bare except blocks (a code smell)
5. Systematic enumeration of all error paths

Actually, I think the best approach is layered: start with branch
coverage to find the obvious gaps, then use AST analysis to find
except blocks that coverage missed, and finally use mutation testing
for the critical paths. This way you get quick wins first before
investing in the slower, more thorough techniques.

I should show how to use coverage tools specifically for error paths,
plus custom scripts to find the gaps that coverage misses.
</think>

Most codebases have poor error path coverage because except blocks are hard to trigger in tests. Here is how to find and fix the gaps:

```python
# ============================================================
# STEP 1: FIND UNTESTED EXCEPT BLOCKS WITH COVERAGE.PY
# ============================================================

# Run tests with branch coverage:
#   pytest --cov=myapp --cov-branch --cov-report=html
#
# In the HTML report, look for RED lines inside except blocks.
# These are error paths that never executed during tests.

# You can also get a machine-readable report:
#   pytest --cov=myapp --cov-branch --cov-report=json
#
# Then parse it to find untested except blocks:

import json
import ast
import os
from pathlib import Path
from typing import Optional


class ExceptBlockFinder(ast.NodeVisitor):
    """Find all except blocks in Python source files."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.except_blocks: list[dict] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        exc_type = "bare except"
        if node.type:
            if isinstance(node.type, ast.Name):
                exc_type = node.type.id
            elif isinstance(node.type, ast.Tuple):
                types = []
                for elt in node.type.elts:
                    if isinstance(elt, ast.Name):
                        types.append(elt.id)
                exc_type = ", ".join(types)

        self.except_blocks.append({
            "file": self.filepath,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "exception_type": exc_type,
            "body_lines": list(range(node.lineno, (node.end_lineno or node.lineno) + 1)),
        })
        self.generic_visit(node)


def find_except_blocks(source_dir: str) -> list[dict]:
    """Find all except blocks in a source directory."""
    blocks = []
    for path in Path(source_dir).rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            finder = ExceptBlockFinder(str(path))
            finder.visit(tree)
            blocks.extend(finder.except_blocks)
        except SyntaxError:
            continue
    return blocks


def find_untested_except_blocks(source_dir: str,
                                  coverage_json: str) -> list[dict]:
    """Cross-reference except blocks with coverage data
    to find untested error paths."""
    # Load coverage data
    with open(coverage_json) as f:
        cov_data = json.load(f)

    all_blocks = find_except_blocks(source_dir)
    untested = []

    for block in all_blocks:
        filepath = block["file"]

        # Normalize path for coverage data lookup
        rel_path = os.path.relpath(filepath)
        file_cov = cov_data.get("files", {}).get(rel_path, {})
        missing_lines = set(file_cov.get("missing_lines", []))

        # Check if any line in the except body is uncovered
        body_lines = set(block["body_lines"])
        uncovered = body_lines & missing_lines

        if uncovered:
            block["uncovered_lines"] = sorted(uncovered)
            block["coverage_pct"] = (
                1 - len(uncovered) / max(len(body_lines), 1)
            ) * 100
            untested.append(block)

    return sorted(untested, key=lambda b: b["file"])


# Usage:
# untested = find_untested_except_blocks("src/", "coverage.json")
# for block in untested:
#     print(f"{block['file']}:{block['line']} "
#           f"except {block['exception_type']} "
#           f"({block['coverage_pct']:.0f}% covered)")


# ============================================================
# STEP 2: ANTI-PATTERN DETECTOR
# ============================================================

class ErrorHandlingAnalyzer(ast.NodeVisitor):
    """Static analysis to find error handling anti-patterns."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.issues: list[dict] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Anti-pattern 1: Bare except (catches everything including SystemExit)
        if node.type is None:
            self.issues.append({
                "file": self.filepath,
                "line": node.lineno,
                "severity": "high",
                "issue": "Bare except clause catches SystemExit, KeyboardInterrupt",
                "fix": "Use 'except Exception:' instead",
            })

        # Anti-pattern 2: Empty except body (silently swallows errors)
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.issues.append({
                "file": self.filepath,
                "line": node.lineno,
                "severity": "medium",
                "issue": "Empty except block silently swallows errors",
                "fix": "At minimum, log the exception",
            })

        # Anti-pattern 3: Catching too broad an exception
        if node.type and isinstance(node.type, ast.Name):
            if node.type.id == "Exception":
                # Check if it is re-raised
                has_raise = any(
                    isinstance(stmt, ast.Raise) for stmt in node.body
                )
                if not has_raise:
                    self.issues.append({
                        "file": self.filepath,
                        "line": node.lineno,
                        "severity": "low",
                        "issue": "Catches broad 'Exception' without re-raising",
                        "fix": "Catch specific exceptions or re-raise after logging",
                    })

        self.generic_visit(node)


def analyze_error_handling(source_dir: str) -> list[dict]:
    """Run static analysis on all Python files."""
    all_issues = []
    for path in Path(source_dir).rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            analyzer = ErrorHandlingAnalyzer(str(path))
            analyzer.visit(tree)
            all_issues.extend(analyzer.issues)
        except SyntaxError:
            continue
    return all_issues


# ============================================================
# STEP 3: SYSTEMATIC ERROR PATH TEST GENERATOR
# ============================================================

def generate_error_test_plan(source_dir: str) -> list[dict]:
    """Generate a test plan for all error paths in the codebase."""
    blocks = find_except_blocks(source_dir)
    test_plan = []

    for block in blocks:
        test_plan.append({
            "location": f"{block['file']}:{block['line']}",
            "exception_type": block["exception_type"],
            "test_name": (
                f"test_{Path(block['file']).stem}"
                f"_line{block['line']}"
                f"_{block['exception_type'].lower().replace(', ', '_')}"
            ),
            "strategy": _suggest_strategy(block["exception_type"]),
        })

    return test_plan


def _suggest_strategy(exc_type: str) -> str:
    """Suggest a testing strategy based on exception type."""
    strategies = {
        "ConnectionError": "Mock the connection to raise ConnectionError",
        "TimeoutError": "Mock with side_effect=TimeoutError or set short timeout",
        "ValueError": "Pass invalid input data that triggers validation",
        "KeyError": "Pass dict missing required keys",
        "FileNotFoundError": "Use tmp_path fixture with nonexistent file",
        "PermissionError": "Use mock or create read-only file",
        "json.JSONDecodeError": "Pass malformed JSON string",
        "OSError": "Mock filesystem operations to raise OSError",
        "bare except": "WARNING: refactor to specific exception first",
    }

    for known_type, strategy in strategies.items():
        if known_type in exc_type:
            return strategy
    return "Mock the operation in the try block to raise " + exc_type


# ============================================================
# STEP 4: COVERAGE-DRIVEN TEST FIXTURE
# ============================================================

import pytest


class ErrorPathTestHelper:
    """Helper for systematically testing error paths."""

    @staticmethod
    @pytest.fixture
    def connection_errors():
        """Common connection-related errors to test against."""
        return [
            ConnectionError("Connection refused"),
            ConnectionResetError("Connection reset by peer"),
            BrokenPipeError("Broken pipe"),
            TimeoutError("Connection timed out"),
            OSError("Network is unreachable"),
        ]

    @staticmethod
    def assert_error_handled(func, *args, expected_errors=None, **kwargs):
        """Verify a function handles errors gracefully.

        If expected_errors is None, the function should not raise.
        If expected_errors is a list of types, it should raise one of them.
        """
        if expected_errors is None:
            # Should not raise any exception
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                pytest.fail(
                    f"Expected no exception but got "
                    f"{type(exc).__name__}: {exc}"
                )
        else:
            with pytest.raises(tuple(expected_errors)):
                func(*args, **kwargs)


# ============================================================
# EXAMPLE: COMPLETE ERROR PATH TEST SUITE
# ============================================================

class TestErrorPaths:
    """Systematic tests for every error path in UserService."""

    def test_get_user_cache_connection_error(self):
        """Line 15: except block in cache.get()"""
        # Tests that cache ConnectionError is caught and DB is used
        pass

    def test_get_user_cache_timeout_error(self):
        """Line 15: except block in cache.get() with TimeoutError"""
        pass

    def test_get_user_db_connection_error(self):
        """Line 22: database query fails"""
        # Tests that ConnectionError propagates correctly
        pass

    def test_get_user_cache_set_failure(self):
        """Line 28: except block in cache.set()"""
        # Tests that cache write failure is swallowed
        pass

    def test_create_user_email_failure(self):
        """Line 38: except block in email_client.send_welcome()"""
        # Tests that email failure does not roll back user creation
        pass
```

**Finding and fixing error path coverage gaps:**

1. **Run `pytest --cov-branch`**: branch coverage catches except blocks that never execute, not just lines
2. **Parse the coverage JSON**: programmatically find which except blocks have uncovered lines
3. **Static analysis first**: find bare excepts and silent swallows before writing tests -- fix the anti-patterns
4. **Generate a test plan**: list every except block with a suggested testing strategy
5. **Prioritize by severity**: test error paths in critical code (payments, auth) before less important ones (logging, metrics)''',
    ),
    (
        "thinking/error-handling",
        r'''What is property-based testing and how do I use it to find edge cases in my error handling code? I feel like my manually written test cases miss a lot of scenarios.''',
        r'''<think>
Property-based testing for error handling -- interesting. My initial
thought is to just show basic Hypothesis examples, but wait, the user
specifically asked about error handling. That changes things because
most Hypothesis tutorials focus on testing correctness of happy paths
(e.g., "sort then unsort gives original"), not on testing that errors
are raised and handled properly.

What makes error-handling property tests different:
1. Generate random invalid inputs to test validation -- this is the
   obvious one, but I need to think about WHAT makes inputs invalid.
   It could be wrong types, out-of-range values, missing fields...
2. Generate random sequences of operations to test state machines --
   hmm, this is actually really powerful because it can find ordering
   bugs where error recovery leaves the system in a bad state.
3. Test invariants that should hold EVEN when errors occur -- for
   example, "the database connection should never be left open after
   an exception." This is the kind of thing humans forget to test.
4. Find boundary conditions automatically

I considered focusing on just input validation testing since that is
the simplest use case. But actually, the stateful testing (sequences
of operations) is where Hypothesis really shines for error handling,
because it can discover that "if operation A fails, then operation B
corrupts data" -- scenarios humans rarely think to test manually.

I should show Hypothesis strategies for error-handling-specific testing
with both stateless and stateful approaches.
</think>

Property-based testing generates thousands of random inputs to find edge cases your manually written tests miss. Here is how to use it for error handling:

```python
import pytest
from hypothesis import given, assume, settings, example
from hypothesis import strategies as st
from typing import Optional
import math
import re


# ============================================================
# THE CODE UNDER TEST
# ============================================================

class InputValidator:
    """Validates user input with various rules."""

    @staticmethod
    def validate_email(email: str) -> str:
        if not isinstance(email, str):
            raise TypeError("Email must be a string")
        if not email or not email.strip():
            raise ValueError("Email cannot be empty")
        if len(email) > 254:
            raise ValueError("Email too long")
        if "@" not in email:
            raise ValueError("Email must contain @")
        local, domain = email.rsplit("@", 1)
        if not local:
            raise ValueError("Email local part cannot be empty")
        if not domain or "." not in domain:
            raise ValueError("Email domain must contain a dot")
        return email.strip().lower()

    @staticmethod
    def validate_age(age) -> int:
        if age is None:
            raise ValueError("Age is required")
        if isinstance(age, bool):
            raise TypeError("Age cannot be a boolean")
        if isinstance(age, str):
            try:
                age = int(age)
            except (ValueError, OverflowError):
                raise ValueError(f"Cannot parse '{age}' as age")
        if not isinstance(age, (int, float)):
            raise TypeError(f"Age must be a number, got {type(age).__name__}")
        if isinstance(age, float):
            if math.isnan(age) or math.isinf(age):
                raise ValueError("Age cannot be NaN or infinity")
            age = int(age)
        if age < 0 or age > 150:
            raise ValueError(f"Age must be 0-150, got {age}")
        return age

    @staticmethod
    def validate_amount(amount) -> float:
        if amount is None:
            raise ValueError("Amount is required")
        if isinstance(amount, str):
            amount = amount.strip().lstrip("$")
            try:
                amount = float(amount)
            except ValueError:
                raise ValueError(f"Cannot parse '{amount}' as amount")
        if not isinstance(amount, (int, float)):
            raise TypeError(f"Amount must be a number")
        if math.isnan(amount) or math.isinf(amount):
            raise ValueError("Amount cannot be NaN or infinity")
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        if amount > 1_000_000:
            raise ValueError("Amount exceeds maximum")
        return round(float(amount), 2)


# ============================================================
# PROPERTY 1: VALIDATORS NEVER CRASH (ALWAYS RAISE CLEAN ERRORS)
# ============================================================

@given(st.from_type(type).flatmap(st.from_type))
def test_validate_email_never_crashes_on_any_type(value):
    """No matter what type we pass, validate_email should either
    return a string or raise ValueError/TypeError -- never crash
    with an unexpected exception."""
    try:
        result = InputValidator.validate_email(value)
        assert isinstance(result, str)
    except (ValueError, TypeError):
        pass  # Expected
    except Exception as exc:
        pytest.fail(
            f"Unexpected exception {type(exc).__name__}: {exc} "
            f"for input {value!r} (type {type(value).__name__})"
        )


@given(st.text())
def test_validate_email_never_crashes_on_any_string(email: str):
    """Any string input should produce a valid result or a clean error."""
    try:
        result = InputValidator.validate_email(email)
        assert isinstance(result, str)
        assert "@" in result
    except ValueError:
        pass


# ============================================================
# PROPERTY 2: VALID INPUTS ALWAYS PASS
# ============================================================

@given(
    local=st.from_regex(r"[a-z][a-z0-9.]{0,30}", fullmatch=True),
    domain=st.from_regex(r"[a-z]{1,20}\.[a-z]{2,5}", fullmatch=True),
)
def test_well_formed_emails_always_pass(local: str, domain: str):
    """Emails matching our regex pattern should always validate."""
    email = f"{local}@{domain}"
    result = InputValidator.validate_email(email)
    assert result == email.lower()


@given(st.integers(min_value=0, max_value=150))
def test_valid_ages_always_pass(age: int):
    """Any integer 0-150 should be accepted."""
    result = InputValidator.validate_age(age)
    assert result == age


@given(st.floats(min_value=0.0, max_value=1_000_000.0,
                  allow_nan=False, allow_infinity=False))
def test_valid_amounts_always_pass(amount: float):
    """Any finite positive float within range should be accepted."""
    result = InputValidator.validate_amount(amount)
    assert 0 <= result <= 1_000_000
    assert isinstance(result, float)


# ============================================================
# PROPERTY 3: INVALID INPUTS ALWAYS RAISE (NEVER SILENTLY PASS)
# ============================================================

@given(st.integers(max_value=-1) | st.integers(min_value=151))
def test_out_of_range_ages_always_rejected(age: int):
    """Ages outside 0-150 must always be rejected."""
    with pytest.raises(ValueError, match="must be 0-150"):
        InputValidator.validate_age(age)


@given(st.floats(allow_nan=True, allow_infinity=True).filter(
    lambda x: math.isnan(x) or math.isinf(x)
))
def test_nan_and_inf_amounts_always_rejected(amount: float):
    """NaN and infinity must always be rejected."""
    with pytest.raises(ValueError, match="NaN or infinity"):
        InputValidator.validate_amount(amount)


@given(st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
def test_negative_amounts_always_rejected(amount: float):
    """Negative amounts must always be rejected."""
    assume(amount < 0)
    with pytest.raises(ValueError, match="negative"):
        InputValidator.validate_amount(amount)


# ============================================================
# PROPERTY 4: IDEMPOTENCY (VALIDATE TWICE = SAME RESULT)
# ============================================================

@given(st.emails())
def test_email_validation_is_idempotent(email: str):
    """Validating a valid email twice should give the same result."""
    try:
        result1 = InputValidator.validate_email(email)
        result2 = InputValidator.validate_email(result1)
        assert result1 == result2
    except ValueError:
        pass  # Some generated emails may not pass our rules


@given(st.integers(min_value=0, max_value=150))
def test_age_validation_is_idempotent(age: int):
    """Validating a valid age twice gives the same result."""
    result1 = InputValidator.validate_age(age)
    result2 = InputValidator.validate_age(result1)
    assert result1 == result2


# ============================================================
# PROPERTY 5: ERROR MESSAGES ARE INFORMATIVE
# ============================================================

@given(st.text(min_size=1).filter(lambda s: "@" not in s))
def test_missing_at_sign_gives_helpful_error(email: str):
    """Error message should mention the @ sign requirement."""
    try:
        InputValidator.validate_email(email)
    except ValueError as exc:
        assert "@" in str(exc), (
            f"Error message should mention '@' but got: {exc}"
        )


# ============================================================
# PROPERTY 6: ROUNDTRIP CONSISTENCY
# ============================================================

@given(st.floats(min_value=0, max_value=999999.99,
                  allow_nan=False, allow_infinity=False))
def test_amount_roundtrip_through_string(amount: float):
    """amount -> string -> validate should give same result."""
    try:
        direct = InputValidator.validate_amount(amount)
        via_string = InputValidator.validate_amount(str(amount))
        assert abs(direct - via_string) < 0.01, (
            f"Direct: {direct}, via string: {via_string}"
        )
    except ValueError:
        pass  # Some floats may have string repr issues


# ============================================================
# STATEFUL TESTING: ERROR HANDLING IN STATEFUL SYSTEMS
# ============================================================

from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

class BankAccountStateMachine(RuleBasedStateMachine):
    """Test that error handling preserves account invariants
    even under random sequences of operations."""

    def __init__(self):
        super().__init__()
        self.balance = 0.0
        self.transaction_count = 0

    @rule(amount=st.floats(min_value=0.01, max_value=10000,
                            allow_nan=False, allow_infinity=False))
    def deposit(self, amount):
        self.balance += amount
        self.transaction_count += 1

    @rule(amount=st.floats(min_value=0.01, max_value=10000,
                            allow_nan=False, allow_infinity=False))
    def withdraw(self, amount):
        if amount > self.balance:
            with pytest.raises(ValueError):
                if amount > self.balance:
                    raise ValueError("Insufficient funds")
        else:
            self.balance -= amount
            self.transaction_count += 1

    @invariant()
    def balance_never_negative(self):
        assert self.balance >= -0.001, (
            f"Balance went negative: {self.balance}"
        )

    @invariant()
    def balance_is_finite(self):
        assert math.isfinite(self.balance), (
            f"Balance is not finite: {self.balance}"
        )


TestBankAccount = BankAccountStateMachine.TestCase
```

**Why property-based testing catches more bugs:**

1. **Volume**: Hypothesis runs hundreds of random inputs per test, not just the 3-5 you would write by hand
2. **Shrinking**: when it finds a failing input, it automatically simplifies it to the minimal reproducing case
3. **Edge cases**: it naturally tries empty strings, zero, negative numbers, NaN, very long strings, unicode
4. **Invariant testing**: instead of testing specific outputs, you test properties that must ALWAYS hold ("balance is never negative")
5. **Stateful testing**: RuleBasedStateMachine generates random sequences of operations to find state-dependent bugs that single-call tests miss''',
    ),
    (
        "thinking/error-handling",
        r'''What is mutation testing and how can it verify that my error handling code actually works? I have tests that pass but I am not confident they are catching real bugs.''',
        r'''<think>
Mutation testing for error handling -- this is a great question because
error handling is exactly where mutation testing is most valuable. Let
me think about why: most developers write happy-path tests, so when a
mutant removes an except block or changes a caught exception type, the
tests often still pass. That surviving mutant reveals a real gap.

Could I just recommend "pip install mutmut and run it"? That would be
too shallow. The user needs to understand what mutations matter for
error handling specifically:
1. Remove an except block -> tests should fail
2. Change caught exception type -> tests should fail
3. Remove retry logic -> tests should fail
4. Change error message -> tests might not catch this (weak tests)
5. Remove logging in except block -> tests probably won't catch this

Wait, points 4 and 5 are interesting. Should tests actually verify
error messages and logging? I considered saying "no, that is too
brittle," but actually for error handling, the log output IS the
observable behavior. If an except block silently swallows an error
without logging, that is a bug. Therefore, tests should verify that
errors produce appropriate log output, even if they do not verify
exact message strings.

Hmm, mutmut can be very slow on large codebases since it runs the
full test suite for each mutant. I should show how to scope it to
just error-handling code (specific files or functions) to keep
runtimes manageable.

I should show mutmut usage, how to interpret results, and how to
write tests that catch the surviving mutants.
</think>

Mutation testing verifies that your tests actually detect bugs by systematically breaking your code and checking if tests catch it. Here is how to use it for error handling:

```python
# ============================================================
# STEP 1: INSTALL AND RUN MUTMUT
# ============================================================

# pip install mutmut
#
# Run mutation testing:
#   mutmut run --paths-to-mutate=src/error_handling.py
#
# View results:
#   mutmut results
#   mutmut show <mutation_id>

# ============================================================
# EXAMPLE: CODE WITH ERROR HANDLING
# ============================================================

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Payment processing with retry and error handling."""

    def __init__(self, gateway, max_retries: int = 3,
                 base_delay: float = 1.0):
        self.gateway = gateway
        self.max_retries = max_retries
        self.base_delay = base_delay

    def charge(self, amount: float, card_token: str) -> dict:
        """Charge a payment with retry logic."""
        if amount <= 0:
            raise ValueError(f"Amount must be positive, got {amount}")
        if amount > 50000:
            raise ValueError(f"Amount {amount} exceeds single charge limit")
        if not card_token:
            raise ValueError("Card token is required")

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.gateway.charge(amount, card_token)
                if result.get("status") == "declined":
                    # Do NOT retry declined cards
                    return {"success": False, "reason": "Card declined",
                            "decline_code": result.get("code")}
                return {"success": True, "transaction_id": result["id"]}

            except ConnectionError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Payment attempt {attempt} failed, "
                        f"retrying in {delay}s: {exc}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"Payment failed after {self.max_retries} attempts"
                    )

            except Exception as exc:
                # Unknown errors should NOT be retried
                logger.error(f"Unexpected payment error: {exc}")
                raise

        raise ConnectionError(
            f"Payment failed after {self.max_retries} retries: {last_error}"
        )


# ============================================================
# STEP 2: TESTS THAT SURVIVE MUTATION (WEAK TESTS)
# ============================================================

# These tests PASS but are weak -- mutations will survive.

def test_charge_success_weak(mocker):
    """This test does not verify the return value structure."""
    gateway = mocker.MagicMock()
    gateway.charge.return_value = {"status": "ok", "id": "txn-123"}
    proc = PaymentProcessor(gateway)

    result = proc.charge(100.0, "tok_123")
    assert result["success"]  # Weak: does not check transaction_id


def test_charge_retry_weak(mocker):
    """This test does not verify retry count or delay."""
    gateway = mocker.MagicMock()
    gateway.charge.side_effect = [
        ConnectionError("fail"),
        {"status": "ok", "id": "txn-456"},
    ]
    proc = PaymentProcessor(gateway)

    result = proc.charge(100.0, "tok_123")
    assert result["success"]  # Weak: does not verify attempt count


# ============================================================
# STEP 3: TESTS THAT KILL MUTATIONS (STRONG TESTS)
# ============================================================

# These tests are mutation-resistant -- they verify exact behavior.

def test_charge_success_strong(mocker):
    """Verify exact return structure on success."""
    gateway = mocker.MagicMock()
    gateway.charge.return_value = {"status": "ok", "id": "txn-123"}
    proc = PaymentProcessor(gateway)

    result = proc.charge(100.0, "tok_123")

    assert result == {"success": True, "transaction_id": "txn-123"}
    gateway.charge.assert_called_once_with(100.0, "tok_123")


def test_charge_negative_amount_strong(mocker):
    """Verify exact error message for negative amount."""
    gateway = mocker.MagicMock()
    proc = PaymentProcessor(gateway)

    import pytest
    with pytest.raises(ValueError, match="must be positive"):
        proc.charge(-10.0, "tok_123")

    # Verify gateway was NOT called (important!)
    gateway.charge.assert_not_called()


def test_charge_over_limit_strong(mocker):
    """Verify exact limit enforcement."""
    gateway = mocker.MagicMock()
    proc = PaymentProcessor(gateway)

    import pytest
    with pytest.raises(ValueError, match="exceeds single charge limit"):
        proc.charge(50001.0, "tok_123")

    gateway.charge.assert_not_called()


def test_charge_retry_count_strong(mocker):
    """Verify exact number of retries and exponential backoff."""
    gateway = mocker.MagicMock()
    gateway.charge.side_effect = [
        ConnectionError("fail 1"),
        ConnectionError("fail 2"),
        {"status": "ok", "id": "txn-789"},
    ]
    proc = PaymentProcessor(gateway, max_retries=3, base_delay=0.01)
    mocker.patch("time.sleep")

    result = proc.charge(100.0, "tok_123")

    assert result == {"success": True, "transaction_id": "txn-789"}
    assert gateway.charge.call_count == 3  # Kills mutation of retry count

    # Verify exponential backoff delays
    sleep_calls = time.sleep.call_args_list
    assert len(sleep_calls) == 2
    assert sleep_calls[0].args[0] == pytest.approx(0.01)  # base_delay * 2^0
    assert sleep_calls[1].args[0] == pytest.approx(0.02)  # base_delay * 2^1


def test_charge_declined_not_retried_strong(mocker):
    """Verify that declined cards are NOT retried."""
    gateway = mocker.MagicMock()
    gateway.charge.return_value = {
        "status": "declined", "code": "insufficient_funds"
    }
    proc = PaymentProcessor(gateway)

    result = proc.charge(100.0, "tok_123")

    assert result["success"] is False
    assert result["reason"] == "Card declined"
    assert result["decline_code"] == "insufficient_funds"
    # Critical: gateway called only ONCE (no retry on decline)
    gateway.charge.assert_called_once()


def test_charge_unknown_error_not_retried_strong(mocker):
    """Verify that unknown exceptions propagate immediately."""
    gateway = mocker.MagicMock()
    gateway.charge.side_effect = RuntimeError("Unknown gateway error")
    proc = PaymentProcessor(gateway)

    import pytest
    with pytest.raises(RuntimeError, match="Unknown gateway error"):
        proc.charge(100.0, "tok_123")

    # Should fail on first attempt, no retry
    gateway.charge.assert_called_once()


def test_charge_all_retries_exhausted_strong(mocker):
    """Verify behavior when all retries fail."""
    gateway = mocker.MagicMock()
    gateway.charge.side_effect = ConnectionError("network down")
    proc = PaymentProcessor(gateway, max_retries=3, base_delay=0.01)
    mocker.patch("time.sleep")

    import pytest
    with pytest.raises(ConnectionError, match="3 retries"):
        proc.charge(100.0, "tok_123")

    assert gateway.charge.call_count == 3  # All retries attempted


# ============================================================
# STEP 4: INTERPRETING MUTMUT RESULTS
# ============================================================

# mutmut results output example:
#
# Survived mutations (TESTS ARE WEAK HERE):
#   src/payment.py:12 - changed "amount <= 0" to "amount < 0"
#     -> Your test does not test amount=0
#
#   src/payment.py:25 - removed "time.sleep(delay)"
#     -> Your test does not verify backoff timing
#
#   src/payment.py:30 - changed "ConnectionError" to "Exception"
#     -> Your test does not verify which exceptions are retried
#
# Killed mutations (TESTS ARE STRONG HERE):
#   src/payment.py:14 - changed "50000" to "50001"
#     -> test_charge_over_limit caught this
#
#   src/payment.py:20 - removed retry loop
#     -> test_charge_retry_count caught this

# ============================================================
# COMMON MUTATIONS TO WATCH FOR IN ERROR HANDLING
# ============================================================

# 1. Boundary changes: "amount <= 0" -> "amount < 0"
#    Fix: Test the exact boundary (amount=0)
#
# 2. Exception type changes: "except ConnectionError" -> "except Exception"
#    Fix: Verify that non-ConnectionError exceptions are NOT caught
#
# 3. Retry count changes: "range(1, 4)" -> "range(1, 3)"
#    Fix: Assert exact call_count on the mocked dependency
#
# 4. Removed error handling: entire except block removed
#    Fix: Test that the error IS caught (function does not raise)
#
# 5. Swapped return values: "success=True" -> "success=False"
#    Fix: Assert exact return value, not just truthiness
#
# 6. Removed re-raise: "raise" removed from except block
#    Fix: Test that the function DOES raise for unexpected errors
#
# 7. Changed error message: "must be positive" -> ""
#    Fix: Match on error message content with pytest.raises(match=...)
```

**Mutation testing workflow:**

1. **Run `mutmut run`**: it creates hundreds of small code changes and reruns your tests against each one
2. **Check survived mutations**: these are bugs your tests would not catch -- the most important output
3. **Write targeted tests**: for each survived mutation, write a test that would detect that specific change
4. **Repeat until mutation score is high**: aim for 80%+ mutation kill rate on error handling code
5. **Focus on critical paths**: payment processing, authentication, and data integrity code should have near-100% mutation kill rate

**Why mutation testing matters for error handling:**

- High code coverage does NOT mean strong tests -- a test can execute an except block without verifying its behavior
- Mutation testing answers: "if I introduced a bug in this error handler, would my tests catch it?"
- It is especially valuable for retry logic, where off-by-one errors in retry counts are common and hard to spot''',
    ),
]
