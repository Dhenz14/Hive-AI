PAIRS = [
    ("projects/testing-framework", r'''<think>
A test framework needs test discovery that finds test functions/classes
automatically. I should implement file scanning, naming conventions,
and decorator-based test registration.
</think>
Build a testing framework with automatic test discovery, test collection, and execution orchestration.''', r'''import importlib
import inspect
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set


@dataclass
class TestCase:
    """Represents a single test case."""
    name: str
    func: Callable
    module: str
    class_name: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    skip: bool = False
    skip_reason: str = ""
    expected_failure: bool = False
    timeout: Optional[float] = None

    @property
    def full_name(self) -> str:
        if self.class_name:
            return f"{self.module}::{self.class_name}::{self.name}"
        return f"{self.module}::{self.name}"


@dataclass
class TestResult:
    """Result of running a single test."""
    test: TestCase
    status: str  # passed, failed, error, skipped, xfail
    duration: float = 0.0
    error_message: str = ""
    traceback_str: str = ""
    output: str = ""


class TestDiscovery:
    """Discovers tests in Python source files."""

    def __init__(self, test_dir: str = "tests", pattern: str = "test_*.py"):
        self._test_dir = Path(test_dir)
        self._pattern = pattern

    def discover(self) -> List[TestCase]:
        """Find all test cases in the test directory."""
        tests = []
        for filepath in self._test_dir.rglob(self._pattern):
            module_tests = self._load_module_tests(filepath)
            tests.extend(module_tests)
        return tests

    def _load_module_tests(self, filepath: Path) -> List[TestCase]:
        """Load test cases from a single Python file."""
        tests = []
        module_name = filepath.stem

        # Add parent dir to sys.path temporarily
        parent = str(filepath.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)

        try:
            spec = importlib.util.spec_from_file_location(module_name, str(filepath))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return tests

        # Find test functions
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name.startswith("test_"):
                tc = TestCase(
                    name=name,
                    func=obj,
                    module=module_name,
                    tags=getattr(obj, "_test_tags", set()),
                    skip=getattr(obj, "_skip", False),
                    skip_reason=getattr(obj, "_skip_reason", ""),
                    expected_failure=getattr(obj, "_xfail", False),
                    timeout=getattr(obj, "_timeout", None),
                )
                tests.append(tc)

            # Find test classes
            elif inspect.isclass(obj) and name.startswith("Test"):
                for method_name, method in inspect.getmembers(obj, inspect.isfunction):
                    if method_name.startswith("test_"):
                        tc = TestCase(
                            name=method_name,
                            func=method,
                            module=module_name,
                            class_name=name,
                            tags=getattr(method, "_test_tags", set()),
                            skip=getattr(method, "_skip", False),
                            skip_reason=getattr(method, "_skip_reason", ""),
                        )
                        tests.append(tc)

        return tests


class TestRunner:
    """Executes test cases and collects results."""

    def __init__(self):
        self._results: List[TestResult] = []
        self._before_all: List[Callable] = []
        self._after_all: List[Callable] = []
        self._before_each: List[Callable] = []
        self._after_each: List[Callable] = []

    def add_hook(self, hook_type: str, func: Callable) -> None:
        hooks = {
            "before_all": self._before_all,
            "after_all": self._after_all,
            "before_each": self._before_each,
            "after_each": self._after_each,
        }
        hooks[hook_type].append(func)

    def run(self, tests: List[TestCase], filter_tags: Optional[Set[str]] = None) -> List[TestResult]:
        """Run all test cases and return results."""
        self._results = []

        if filter_tags:
            tests = [t for t in tests if t.tags & filter_tags]

        for hook in self._before_all:
            hook()

        for test in tests:
            result = self._run_single(test)
            self._results.append(result)

        for hook in self._after_all:
            hook()

        return self._results

    def _run_single(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        if test.skip:
            return TestResult(
                test=test,
                status="skipped",
                error_message=test.skip_reason,
            )

        for hook in self._before_each:
            hook()

        start = time.perf_counter()
        try:
            if test.class_name:
                # Instantiate the class and call the method
                cls = type(test.class_name, (), {test.name: test.func})
                instance = cls()
                getattr(instance, test.name)()
            else:
                test.func()

            duration = time.perf_counter() - start

            if test.expected_failure:
                status = "xfail"
            else:
                status = "passed"

            result = TestResult(test=test, status=status, duration=duration)

        except AssertionError as e:
            duration = time.perf_counter() - start
            if test.expected_failure:
                status = "xfail"
            else:
                status = "failed"
            result = TestResult(
                test=test,
                status=status,
                duration=duration,
                error_message=str(e),
                traceback_str=traceback.format_exc(),
            )

        except Exception as e:
            duration = time.perf_counter() - start
            result = TestResult(
                test=test,
                status="error",
                duration=duration,
                error_message=str(e),
                traceback_str=traceback.format_exc(),
            )

        for hook in self._after_each:
            hook()

        return result


def run_tests(test_dir: str = "tests", tags: Optional[Set[str]] = None, verbose: bool = True) -> bool:
    """Convenience function to discover and run tests."""
    discovery = TestDiscovery(test_dir)
    tests = discovery.discover()
    runner = TestRunner()
    results = runner.run(tests, filter_tags=tags)

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skipped")

    if verbose:
        for r in results:
            symbol = {"passed": ".", "failed": "F", "error": "E", "skipped": "S", "xfail": "x"}.get(r.status, "?")
            print(f"  {symbol} {r.test.full_name} ({r.duration:.3f}s)")
            if r.status in ("failed", "error") and r.traceback_str:
                print(f"    {r.error_message}")

        total_time = sum(r.duration for r in results)
        print(f"\n{len(results)} tests in {total_time:.2f}s: {passed} passed, {failed} failed, {errors} errors, {skipped} skipped")

    return failed == 0 and errors == 0
'''),
    ("projects/testing-framework", r'''Implement an assertion library with rich comparison messages and custom matchers.''', r'''import math
import re
from typing import Any, Callable, Container, List, Optional, Type, Union


class AssertionError(Exception):
    """Custom assertion error with formatted message."""
    pass


class Matcher:
    """Base class for custom matchers."""

    def matches(self, actual: Any) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def describe_mismatch(self, actual: Any) -> str:
        return f"got {repr(actual)}"


class EqualTo(Matcher):
    def __init__(self, expected: Any):
        self.expected = expected

    def matches(self, actual: Any) -> bool:
        return actual == self.expected

    def describe(self) -> str:
        return f"equal to {repr(self.expected)}"

    def describe_mismatch(self, actual: Any) -> str:
        if isinstance(actual, str) and isinstance(self.expected, str):
            # Show diff for strings
            for i, (a, e) in enumerate(zip(actual, self.expected)):
                if a != e:
                    return f"strings differ at index {i}: got {repr(a)}, expected {repr(e)}"
            if len(actual) != len(self.expected):
                return f"string lengths differ: got {len(actual)}, expected {len(self.expected)}"
        return f"got {repr(actual)}"


class CloseTo(Matcher):
    def __init__(self, expected: float, delta: float = 1e-6):
        self.expected = expected
        self.delta = delta

    def matches(self, actual: Any) -> bool:
        return abs(float(actual) - self.expected) <= self.delta

    def describe(self) -> str:
        return f"close to {self.expected} (within {self.delta})"


class ContainsString(Matcher):
    def __init__(self, substring: str):
        self.substring = substring

    def matches(self, actual: Any) -> bool:
        return self.substring in str(actual)

    def describe(self) -> str:
        return f"containing {repr(self.substring)}"


class MatchesRegex(Matcher):
    def __init__(self, pattern: str):
        self.pattern = pattern

    def matches(self, actual: Any) -> bool:
        return bool(re.search(self.pattern, str(actual)))

    def describe(self) -> str:
        return f"matching pattern {repr(self.pattern)}"


class HasLength(Matcher):
    def __init__(self, expected_length: int):
        self.expected_length = expected_length

    def matches(self, actual: Any) -> bool:
        return len(actual) == self.expected_length

    def describe(self) -> str:
        return f"with length {self.expected_length}"


class InstanceOf(Matcher):
    def __init__(self, expected_type: Type):
        self.expected_type = expected_type

    def matches(self, actual: Any) -> bool:
        return isinstance(actual, self.expected_type)

    def describe(self) -> str:
        return f"instance of {self.expected_type.__name__}"


class Expect:
    """Fluent assertion interface."""

    def __init__(self, actual: Any):
        self.actual = actual
        self._negated = False

    @property
    def not_to(self) -> "Expect":
        """Negate the next assertion."""
        self._negated = True
        return self

    def _check(self, matcher: Matcher) -> None:
        result = matcher.matches(self.actual)
        if self._negated:
            result = not result
        if not result:
            neg = "not " if self._negated else ""
            msg = f"Expected {repr(self.actual)} {neg}to be {matcher.describe()}"
            mismatch = matcher.describe_mismatch(self.actual)
            raise AssertionError(f"{msg}, but {mismatch}")
        self._negated = False

    def to_equal(self, expected: Any) -> None:
        self._check(EqualTo(expected))

    def to_be_close_to(self, expected: float, delta: float = 1e-6) -> None:
        self._check(CloseTo(expected, delta))

    def to_contain(self, item: Any) -> None:
        if isinstance(self.actual, str):
            self._check(ContainsString(item))
        else:
            result = item in self.actual
            if self._negated:
                result = not result
            if not result:
                neg = "not " if self._negated else ""
                raise AssertionError(f"Expected {repr(self.actual)} {neg}to contain {repr(item)}")
            self._negated = False

    def to_match(self, pattern: str) -> None:
        self._check(MatchesRegex(pattern))

    def to_have_length(self, length: int) -> None:
        self._check(HasLength(length))

    def to_be_instance_of(self, expected_type: Type) -> None:
        self._check(InstanceOf(expected_type))

    def to_be_truthy(self) -> None:
        if not bool(self.actual) and not self._negated:
            raise AssertionError(f"Expected {repr(self.actual)} to be truthy")
        if bool(self.actual) and self._negated:
            raise AssertionError(f"Expected {repr(self.actual)} to be falsy")
        self._negated = False

    def to_be_none(self) -> None:
        result = self.actual is None
        if self._negated:
            result = not result
        if not result:
            neg = "not " if self._negated else ""
            raise AssertionError(f"Expected {repr(self.actual)} {neg}to be None")
        self._negated = False

    def to_raise(self, exception_type: Optional[Type[Exception]] = None) -> None:
        """Assert that calling self.actual raises an exception."""
        try:
            self.actual()
            if not self._negated:
                raise AssertionError(f"Expected function to raise {exception_type or 'an exception'}")
        except Exception as e:
            if exception_type and not isinstance(e, exception_type):
                raise AssertionError(
                    f"Expected {exception_type.__name__} but got {type(e).__name__}: {e}"
                )
            if self._negated:
                raise AssertionError(f"Expected no exception but got {type(e).__name__}: {e}")
        self._negated = False

    def to_satisfy(self, matcher: Matcher) -> None:
        """Check against a custom matcher."""
        self._check(matcher)


def expect(actual: Any) -> Expect:
    """Create an expectation for fluent assertions."""
    return Expect(actual)
'''),
    ("projects/testing-framework", r'''Implement test fixtures with setup/teardown, scoping, and dependency injection for the testing framework.''', r'''import inspect
import functools
from typing import Any, Callable, Dict, Generator, List, Optional, Set


class FixtureScope:
    SESSION = "session"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"


class Fixture:
    """Represents a test fixture with lifecycle management."""

    def __init__(
        self,
        name: str,
        func: Callable,
        scope: str = FixtureScope.FUNCTION,
        autouse: bool = False,
    ):
        self.name = name
        self.func = func
        self.scope = scope
        self.autouse = autouse
        self._cached_value: Any = None
        self._is_cached = False
        self._teardown: Optional[Callable] = None
        self._dependencies: List[str] = []

        # Detect dependencies from function parameters
        sig = inspect.signature(func)
        self._dependencies = [
            p.name for p in sig.parameters.values()
            if p.name != "self"
        ]

    def setup(self, resolved_deps: Dict[str, Any]) -> Any:
        """Set up the fixture and return its value."""
        if self._is_cached:
            return self._cached_value

        # Resolve dependencies
        kwargs = {name: resolved_deps[name] for name in self._dependencies if name in resolved_deps}
        result = self.func(**kwargs)

        # Handle generator fixtures (for teardown)
        if inspect.isgenerator(result):
            gen = result
            value = next(gen)
            self._teardown = lambda: self._exhaust_generator(gen)
            result = value

        self._cached_value = result
        self._is_cached = True
        return result

    def teardown(self) -> None:
        """Tear down the fixture."""
        if self._teardown:
            try:
                self._teardown()
            except Exception:
                pass
        self._cached_value = None
        self._is_cached = False

    def _exhaust_generator(self, gen: Generator) -> None:
        try:
            next(gen)
        except StopIteration:
            pass


class FixtureRegistry:
    """Manages fixture registration and resolution."""

    def __init__(self):
        self._fixtures: Dict[str, Fixture] = {}
        self._active_fixtures: Dict[str, Fixture] = {}

    def register(
        self,
        name: Optional[str] = None,
        scope: str = FixtureScope.FUNCTION,
        autouse: bool = False,
    ) -> Callable:
        """Decorator to register a fixture."""
        def decorator(func: Callable) -> Callable:
            fixture_name = name or func.__name__
            fixture = Fixture(
                name=fixture_name,
                func=func,
                scope=scope,
                autouse=autouse,
            )
            self._fixtures[fixture_name] = fixture
            return func
        return decorator

    def resolve(self, fixture_names: List[str]) -> Dict[str, Any]:
        """Resolve a set of fixtures, handling dependencies."""
        resolved: Dict[str, Any] = {}
        visited: Set[str] = set()

        def _resolve_one(name: str) -> Any:
            if name in resolved:
                return resolved[name]

            if name in visited:
                raise ValueError(f"Circular fixture dependency detected: {name}")

            visited.add(name)
            fixture = self._fixtures.get(name)
            if not fixture:
                raise ValueError(f"Fixture '{name}' not found")

            # Resolve dependencies first
            for dep in fixture._dependencies:
                if dep not in resolved:
                    _resolve_one(dep)

            value = fixture.setup(resolved)
            resolved[name] = value
            self._active_fixtures[name] = fixture
            return value

        for fixture_name in fixture_names:
            _resolve_one(fixture_name)

        # Add autouse fixtures
        for name, fixture in self._fixtures.items():
            if fixture.autouse and name not in resolved:
                _resolve_one(name)

        return resolved

    def teardown_scope(self, scope: str) -> None:
        """Tear down all fixtures of a given scope."""
        to_teardown = [
            (name, f) for name, f in self._active_fixtures.items()
            if f.scope == scope
        ]
        # Teardown in reverse order
        for name, fixture in reversed(to_teardown):
            fixture.teardown()
            del self._active_fixtures[name]

    def teardown_all(self) -> None:
        """Tear down all active fixtures."""
        for name, fixture in reversed(list(self._active_fixtures.items())):
            fixture.teardown()
        self._active_fixtures.clear()

    def get_required_fixtures(self, test_func: Callable) -> List[str]:
        """Get fixture names required by a test function."""
        sig = inspect.signature(test_func)
        return [
            p.name for p in sig.parameters.values()
            if p.name in self._fixtures
        ]


# Global fixture registry
_registry = FixtureRegistry()


def fixture(func: Optional[Callable] = None, scope: str = FixtureScope.FUNCTION, autouse: bool = False):
    """Decorator to register a fixture function."""
    if func is not None:
        return _registry.register(scope=scope, autouse=autouse)(func)
    return _registry.register(scope=scope, autouse=autouse)


# Example usage:
# @fixture
# def database():
#     db = create_test_database()
#     yield db
#     db.drop()
#
# @fixture
# def user(database):
#     return database.create_user("test_user")
#
# def test_user_creation(user, database):
#     assert user.name == "test_user"
#     assert database.count_users() == 1
'''),
    ("projects/testing-framework", r'''<think>
A mocking library needs to intercept function calls, record them,
and return configurable values. I need to support both function mocking
and object attribute mocking with call verification.
</think>
Implement a mocking library with call recording, return value configuration, and verification.''', r'''import functools
from typing import Any, Callable, Dict, List, Optional, Tuple
from contextlib import contextmanager
import copy


class Call:
    """Records a single function call."""

    def __init__(self, args: tuple, kwargs: dict):
        self.args = args
        self.kwargs = kwargs

    def __repr__(self) -> str:
        arg_strs = [repr(a) for a in self.args]
        kwarg_strs = [f"{k}={repr(v)}" for k, v in self.kwargs.items()]
        all_args = ", ".join(arg_strs + kwarg_strs)
        return f"Call({all_args})"

    def matches(self, args: tuple, kwargs: dict) -> bool:
        """Check if this call matches the given arguments."""
        return self.args == args and self.kwargs == kwargs


class Mock:
    """A mock object that records calls and returns configured values."""

    def __init__(self, name: str = "mock", return_value: Any = None):
        self._name = name
        self._return_value = return_value
        self._side_effect: Optional[Callable] = None
        self._return_values: List[Any] = []
        self._call_count = 0
        self._calls: List[Call] = []
        self._children: Dict[str, "Mock"] = {}
        self._raises: Optional[Exception] = None

    def __call__(self, *args, **kwargs) -> Any:
        """Record the call and return configured value."""
        call = Call(args, kwargs)
        self._calls.append(call)
        self._call_count += 1

        if self._raises:
            raise self._raises

        if self._side_effect:
            return self._side_effect(*args, **kwargs)

        if self._return_values:
            idx = min(self._call_count - 1, len(self._return_values) - 1)
            return self._return_values[idx]

        return self._return_value

    def __getattr__(self, name: str) -> "Mock":
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._children:
            self._children[name] = Mock(name=f"{self._name}.{name}")
        return self._children[name]

    def returns(self, value: Any) -> "Mock":
        """Configure the return value."""
        self._return_value = value
        return self

    def returns_sequence(self, *values: Any) -> "Mock":
        """Return different values on successive calls."""
        self._return_values = list(values)
        return self

    def raises(self, exception: Exception) -> "Mock":
        """Configure the mock to raise an exception."""
        self._raises = exception
        return self

    def with_side_effect(self, func: Callable) -> "Mock":
        """Set a side effect function."""
        self._side_effect = func
        return self

    @property
    def called(self) -> bool:
        return self._call_count > 0

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def calls(self) -> List[Call]:
        return list(self._calls)

    @property
    def last_call(self) -> Optional[Call]:
        return self._calls[-1] if self._calls else None

    def assert_called(self) -> None:
        if not self.called:
            raise AssertionError(f"Expected {self._name} to be called, but it was not")

    def assert_called_once(self) -> None:
        if self._call_count != 1:
            raise AssertionError(
                f"Expected {self._name} to be called once, but was called {self._call_count} times"
            )

    def assert_called_with(self, *args, **kwargs) -> None:
        if not self._calls:
            raise AssertionError(f"Expected {self._name} to be called, but it was not")
        last = self._calls[-1]
        if not last.matches(args, kwargs):
            raise AssertionError(
                f"Expected {self._name} to be called with {Call(args, kwargs)}, "
                f"but was called with {last}"
            )

    def assert_called_times(self, n: int) -> None:
        if self._call_count != n:
            raise AssertionError(
                f"Expected {self._name} to be called {n} times, but was called {self._call_count} times"
            )

    def assert_any_call(self, *args, **kwargs) -> None:
        for call in self._calls:
            if call.matches(args, kwargs):
                return
        raise AssertionError(
            f"Expected {self._name} to be called with {Call(args, kwargs)}, "
            f"but no matching call found"
        )

    def reset(self) -> None:
        """Reset call history."""
        self._calls.clear()
        self._call_count = 0


@contextmanager
def patch(target_obj: Any, attribute: str, replacement: Any = None):
    """Context manager to temporarily replace an attribute."""
    original = getattr(target_obj, attribute)
    mock = replacement if replacement is not None else Mock(name=attribute)
    setattr(target_obj, attribute, mock)
    try:
        yield mock
    finally:
        setattr(target_obj, attribute, original)


@contextmanager
def patch_dict(target_dict: dict, updates: dict):
    """Context manager to temporarily update a dictionary."""
    original = {k: target_dict.get(k) for k in updates if k in target_dict}
    missing_keys = {k for k in updates if k not in target_dict}

    target_dict.update(updates)
    try:
        yield target_dict
    finally:
        target_dict.update(original)
        for k in missing_keys:
            target_dict.pop(k, None)


class Spy:
    """Wraps a real function, recording calls while still executing it."""

    def __init__(self, func: Callable):
        self._func = func
        self._calls: List[Call] = []

    def __call__(self, *args, **kwargs) -> Any:
        self._calls.append(Call(args, kwargs))
        return self._func(*args, **kwargs)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def calls(self) -> List[Call]:
        return list(self._calls)
'''),
    ("projects/testing-framework", r'''Implement test coverage tracking that measures which lines and branches were executed during tests.''', r'''import ast
import sys
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FileCoverage:
    """Coverage data for a single file."""
    filepath: str
    total_lines: Set[int] = field(default_factory=set)
    executed_lines: Set[int] = field(default_factory=set)
    branch_points: Set[int] = field(default_factory=set)
    branches_taken: Set[Tuple[int, int]] = field(default_factory=set)

    @property
    def line_coverage(self) -> float:
        if not self.total_lines:
            return 100.0
        return len(self.executed_lines & self.total_lines) / len(self.total_lines) * 100

    @property
    def missed_lines(self) -> Set[int]:
        return self.total_lines - self.executed_lines

    def to_dict(self) -> dict:
        return {
            "filepath": self.filepath,
            "total_lines": len(self.total_lines),
            "executed_lines": len(self.executed_lines & self.total_lines),
            "missed_lines": sorted(self.missed_lines),
            "line_coverage": f"{self.line_coverage:.1f}%",
        }


class LineAnalyzer:
    """Analyzes Python source to find executable lines."""

    def find_executable_lines(self, filepath: str) -> Set[int]:
        """Find all executable lines in a Python file."""
        with open(filepath, "r") as f:
            source = f.read()

        try:
            tree = ast.parse(source, filepath)
        except SyntaxError:
            return set()

        executable = set()
        self._walk(tree, executable)
        return executable

    def _walk(self, node: ast.AST, lines: Set[int]) -> None:
        """Walk the AST and collect executable line numbers."""
        # Nodes that represent executable lines
        executable_types = (
            ast.Assign, ast.AugAssign, ast.AnnAssign,
            ast.Return, ast.Delete, ast.Raise,
            ast.Assert, ast.Import, ast.ImportFrom,
            ast.Expr, ast.Pass, ast.Break, ast.Continue,
            ast.If, ast.For, ast.While, ast.With,
            ast.Try, ast.Global, ast.Nonlocal,
        )

        if isinstance(node, executable_types) and hasattr(node, "lineno"):
            lines.add(node.lineno)

        for child in ast.iter_child_nodes(node):
            self._walk(child, lines)

    def find_branch_points(self, filepath: str) -> Set[int]:
        """Find lines that are branch points (if, for, while, etc.)."""
        with open(filepath, "r") as f:
            source = f.read()

        try:
            tree = ast.parse(source, filepath)
        except SyntaxError:
            return set()

        branches = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try)):
                branches.add(node.lineno)
        return branches


class CoverageTracer:
    """Traces code execution using sys.settrace."""

    def __init__(self, source_dirs: Optional[List[str]] = None):
        self._source_dirs = [Path(d).resolve() for d in (source_dirs or ["."])]
        self._data: Dict[str, FileCoverage] = {}
        self._analyzer = LineAnalyzer()
        self._lock = threading.Lock()
        self._active = False

    def start(self) -> None:
        """Start collecting coverage data."""
        self._active = True
        sys.settrace(self._trace_calls)
        threading.settrace(self._trace_calls)

    def stop(self) -> None:
        """Stop collecting coverage data."""
        self._active = False
        sys.settrace(None)
        threading.settrace(None)

    def _should_trace(self, filename: str) -> bool:
        """Check if a file should be traced."""
        if not filename or filename.startswith("<"):
            return False
        filepath = Path(filename).resolve()
        return any(
            str(filepath).startswith(str(d))
            for d in self._source_dirs
        )

    def _trace_calls(self, frame, event, arg):
        """Trace function for sys.settrace."""
        if not self._active:
            return None

        filename = frame.f_code.co_filename
        if not self._should_trace(filename):
            return None

        if event == "call":
            return self._trace_lines

        return None

    def _trace_lines(self, frame, event, arg):
        """Line-level trace function."""
        if event == "line":
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno

            with self._lock:
                if filename not in self._data:
                    self._data[filename] = FileCoverage(
                        filepath=filename,
                        total_lines=self._analyzer.find_executable_lines(filename),
                        branch_points=self._analyzer.find_branch_points(filename),
                    )
                self._data[filename].executed_lines.add(lineno)

        return self._trace_lines

    def get_report(self) -> dict:
        """Generate a coverage report."""
        files = []
        total_executable = 0
        total_executed = 0

        for filepath, cov in sorted(self._data.items()):
            files.append(cov.to_dict())
            total_executable += len(cov.total_lines)
            total_executed += len(cov.executed_lines & cov.total_lines)

        overall = (total_executed / total_executable * 100) if total_executable else 100.0

        return {
            "overall_coverage": f"{overall:.1f}%",
            "total_executable_lines": total_executable,
            "total_executed_lines": total_executed,
            "files": files,
        }

    def print_report(self) -> None:
        """Print a formatted coverage report."""
        report = self.get_report()
        print(f"\n{'File':<50} {'Lines':>8} {'Covered':>8} {'Coverage':>10}")
        print("-" * 78)

        for f in report["files"]:
            name = Path(f["filepath"]).name
            print(f"{name:<50} {f['total_lines']:>8} {f['executed_lines']:>8} {f['line_coverage']:>10}")

        print("-" * 78)
        print(f"{'TOTAL':<50} {report['total_executable_lines']:>8} {report['total_executed_lines']:>8} {report['overall_coverage']:>10}")

    def reset(self) -> None:
        """Clear all coverage data."""
        self._data.clear()
'''),
]
