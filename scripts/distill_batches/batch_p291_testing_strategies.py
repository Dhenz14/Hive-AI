"""Testing strategies — property-based, snapshot, mutation, fuzz testing."""

PAIRS = [
    (
        "testing/property-based",
        "Show property-based testing with Hypothesis: generating test data, defining properties, and finding edge cases.",
        '''Property-based testing with Hypothesis:

```python
from hypothesis import given, strategies as st, assume, settings, example
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize
import json


# Basic property test
@given(st.lists(st.integers()))
def test_sort_preserves_length(lst):
    """Property: sorting never changes list length."""
    assert len(sorted(lst)) == len(lst)


@given(st.lists(st.integers(), min_size=1))
def test_sort_is_ordered(lst):
    """Property: sorted list is monotonically increasing."""
    result = sorted(lst)
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1]


# Composite strategies for complex data
@st.composite
def json_documents(draw):
    """Generate arbitrary valid JSON documents."""
    key = draw(st.text(min_size=1, max_size=20,
                        alphabet=st.characters(whitelist_categories=("L",))))
    value = draw(st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=100),
        st.booleans(),
        st.none(),
    ))
    return {key: value}


@given(json_documents())
def test_json_roundtrip(doc):
    """Property: JSON encode → decode is identity."""
    encoded = json.dumps(doc)
    decoded = json.loads(encoded)
    assert decoded == doc


# Stateful testing (model-based)
class SetModel(RuleBasedStateMachine):
    """Test a custom Set implementation against Python set."""

    def __init__(self):
        super().__init__()
        self.model = set()
        self.impl = CustomSet()

    @initialize()
    def init(self):
        self.model = set()
        self.impl = CustomSet()

    @rule(value=st.integers())
    def add(self, value):
        self.model.add(value)
        self.impl.add(value)
        assert len(self.model) == len(self.impl)

    @rule(value=st.integers())
    def remove(self, value):
        if value in self.model:
            self.model.remove(value)
            self.impl.remove(value)
        assert len(self.model) == len(self.impl)

    @rule(value=st.integers())
    def contains(self, value):
        assert (value in self.model) == (value in self.impl)


TestSet = SetModel.TestCase


# Test with specific examples + generated data
@given(st.text())
@example("")          # Always test empty string
@example("\\n\\t  ")    # Whitespace edge case
@settings(max_examples=200)
def test_strip_idempotent(s):
    """Property: stripping twice = stripping once."""
    assert s.strip().strip() == s.strip()
```

Key patterns:
1. **Properties over examples** — define what must be true for ALL inputs, not specific cases
2. **Composite strategies** — build complex test data from simple strategies
3. **Stateful testing** — model-based testing compares implementation against reference
4. **Shrinking** — Hypothesis automatically minimizes failing inputs for readable bugs
5. **Explicit examples** — combine property tests with known edge cases via @example'''
    ),
    (
        "testing/snapshot-testing",
        "Show snapshot testing: capturing output snapshots, updating baselines, and testing complex output structures.",
        '''Snapshot testing patterns:

```python
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Any


class SnapshotTester:
    """Capture and compare output snapshots for regression testing."""

    def __init__(self, snapshot_dir: str = "tests/snapshots"):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.update_mode = False  # Set via env var or flag

    def assert_match(self, name: str, actual: Any,
                      serializer: str = "json"):
        """Compare actual output to stored snapshot."""
        snapshot_path = self.snapshot_dir / f"{name}.snap"

        serialized = self._serialize(actual, serializer)

        if self.update_mode or not snapshot_path.exists():
            # Create or update snapshot
            snapshot_path.write_text(serialized)
            return

        expected = snapshot_path.read_text()
        if serialized != expected:
            diff = self._diff(expected, serialized)
            raise SnapshotMismatch(
                f"Snapshot '{name}' does not match:\\n{diff}\\n"
                f"Run with --update-snapshots to update."
            )

    def _serialize(self, value: Any, method: str) -> str:
        if method == "json":
            return json.dumps(value, indent=2, sort_keys=True, default=str)
        elif method == "text":
            return str(value)
        elif method == "repr":
            return repr(value)
        raise ValueError(f"Unknown serializer: {method}")

    def _diff(self, expected: str, actual: str) -> str:
        import difflib
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected", tofile="actual",
        )
        return "".join(diff)


class SnapshotMismatch(AssertionError):
    pass


# pytest integration
import pytest

@pytest.fixture
def snapshot(request, tmp_path):
    tester = SnapshotTester(snapshot_dir="tests/snapshots")
    tester.update_mode = request.config.getoption("--update-snapshots", False)
    return tester


# Usage in tests
def test_api_response(snapshot):
    response = api_client.get("/users/1")
    snapshot.assert_match("get_user_response", response.json())

def test_html_rendering(snapshot):
    html = render_template("profile.html", user=mock_user)
    snapshot.assert_match("profile_html", html, serializer="text")

def test_report_generation(snapshot):
    report = generate_report(test_data)
    snapshot.assert_match("monthly_report", report)
```

Key patterns:
1. **Golden file testing** — store expected output; compare against it in future runs
2. **Update mode** — `--update-snapshots` flag regenerates baselines after intentional changes
3. **Diff output** — unified diff shows exactly what changed; easy to review
4. **Multiple serializers** — JSON for structured data, text for HTML/strings
5. **Regression detection** — any unintentional output change is caught automatically'''
    ),
]
"""
