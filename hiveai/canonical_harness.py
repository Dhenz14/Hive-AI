"""
hiveai/canonical_harness.py

System-owned canonical test harnesses for executable verification.

Instead of trusting model-authored assertions (weak oracle), this module
provides task-matched canonical tests that verify the model's CODE against
known-correct expected outputs.

Verifier modes:
  - canonical_tests: exact expected outputs from system-owned harness
  - property_checks: invariant/metamorphic checks (sorted, shape, bijection)
  - generated_assertions: model-authored tests (weak fallback)
  - no_verdict: task is time/env sensitive, skip verification

Usage:
    mode, harness = match_harness(user_query, extracted_code)
    if harness:
        result = run_harness(extracted_code, harness)
"""
import re
import ast
import subprocess
import sys
import tempfile
import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Harness definitions — canonical tests for known task types
# ---------------------------------------------------------------------------

# Each harness: (pattern, verifier_mode, canonical_test_code, property_checks)
# pattern: regex matched against the user query
# canonical_test_code: Python code appended AFTER the model's solution code
# property_checks: additional invariant checks (optional)

HARNESSES = [
    {
        "id": "merge_sorted",
        "patterns": [r"merge.*sorted.*list", r"merge.*two.*sorted"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: merge_sorted ===
# Find the merge function (try common names)
import types
_fn = None
for _name in ['merge_sorted', 'merge_sorted_lists', 'merge_two_sorted', 'merge']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No merge function found"

# Canonical tests with verified expected outputs
assert _fn([], []) == [], "empty + empty"
assert _fn([1, 2, 3], []) == [1, 2, 3], "non-empty + empty"
assert _fn([], [4, 5, 6]) == [4, 5, 6], "empty + non-empty"
assert _fn([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6], "interleaved"
assert _fn([1], [2]) == [1, 2], "single elements"
assert _fn([1, 1, 2, 2], [1, 2, 2, 3]) == [1, 1, 1, 2, 2, 2, 2, 3], "duplicates"
# Property: output is sorted
_out = _fn([10, 20, 30], [5, 15, 25])
assert _out == sorted(_out), "output must be sorted"
# Property: multiset preserved
from collections import Counter
_a, _b = [3, 1, 4], [1, 5, 9]
assert Counter(_fn(_a, _b)) == Counter(_a + _b), "all elements preserved"
""",
    },
    {
        "id": "binary_search",
        "patterns": [r"binary.?search", r"binary.*search.*index"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: binary_search ===
_fn = None
for _name in ['binary_search', 'bsearch', 'bin_search']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No binary_search function found"

assert _fn([1, 2, 3, 4, 5], 3) == 2, "found in middle"
assert _fn([1, 2, 3, 4, 5], 1) == 0, "found at start"
assert _fn([1, 2, 3, 4, 5], 5) == 4, "found at end"
assert _fn([1, 2, 3, 4, 5], 6) == -1, "not found (too high)"
assert _fn([1, 2, 3, 4, 5], 0) == -1, "not found (too low)"
assert _fn([], 1) == -1, "empty list"
assert _fn([42], 42) == 0, "single element found"
assert _fn([42], 99) == -1, "single element not found"
# Property: if found, element at index equals target
_arr = [10, 20, 30, 40, 50]
_idx = _fn(_arr, 30)
assert _idx >= 0 and _arr[_idx] == 30, "index points to target"
""",
    },
    {
        "id": "validate_brackets",
        "patterns": [r"valid.*bracket", r"balanced.*bracket", r"bracket.*balanc", r"parenthes.*match", r"bracket.*valid"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: validate_brackets ===
_fn = None
for _name in ['validate_brackets', 'is_balanced', 'check_brackets', 'balanced_brackets']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No bracket validator function found"

assert _fn("") == True, "empty string"
assert _fn("()") == True, "simple parens"
assert _fn("[]") == True, "simple brackets"
assert _fn("{}") == True, "simple braces"
assert _fn("({[]})") == True, "nested mixed"
assert _fn("(") == False, "unbalanced open"
assert _fn(")") == False, "unbalanced close"
assert _fn("([)]") == False, "interleaved wrong"
assert _fn("((()))") == True, "deeply nested"
assert _fn("{[()]}") == True, "all three nested"
assert _fn(")(") == False, "reversed"
""",
    },
    {
        "id": "rotate_90",
        "patterns": [r"rotate.*90", r"rotate.*matrix.*clockwise", r"clockwise.*rotat"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: rotate_90 ===
_fn = None
for _name in ['rotate_90', 'rotate', 'rotate_matrix', 'rotate_clockwise']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No rotate function found"

# 2x2
_m = [[1, 2], [3, 4]]
_fn(_m)
assert _m == [[3, 1], [4, 2]], f"2x2 failed: {_m}"

# 3x3
_m = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
_fn(_m)
assert _m == [[7, 4, 1], [8, 5, 2], [9, 6, 3]], f"3x3 failed: {_m}"

# Property: 4 rotations = identity
_m = [[1, 2], [3, 4]]
for _ in range(4):
    _fn(_m)
assert _m == [[1, 2], [3, 4]], "4 rotations should return to original"
""",
    },
    {
        "id": "trie",
        "patterns": [r"\btrie\b.*insert.*search", r"\btrie\b.*prefix"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: trie ===
_cls = None
for _name in ['Trie', 'TrieNode']:
    _cls = globals().get(_name)
    if _cls and isinstance(_cls, type):
        break
assert _cls is not None, "No Trie class found"

_t = _cls()
_t.insert("apple")
assert _t.search("apple") == True, "inserted word found"
assert _t.search("app") == False, "prefix is not full word"
assert _t.starts_with("app") == True, "prefix match"
_t.insert("app")
assert _t.search("app") == True, "after inserting prefix as word"
assert _t.search("banana") == False, "word not inserted"
_t.insert("banana")
assert _t.search("banana") == True, "newly inserted word"
assert _t.starts_with("ban") == True, "prefix of new word"
assert _t.starts_with("xyz") == False, "no such prefix"
""",
    },
    {
        "id": "deep_merge",
        "patterns": [r"deep.*merge.*dict", r"recursive.*merge.*dict", r"merge.*nested.*dict"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: deep_merge ===
_fn = None
for _name in ['deep_merge', 'merge_dicts', 'recursive_merge']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No deep_merge function found"

# Flat merge
assert _fn({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}, "flat merge"
# Nested merge
assert _fn({"a": {"x": 1}}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}}, "nested merge"
# List concat
assert _fn({"a": [1, 2]}, {"a": [3, 4]}) == {"a": [1, 2, 3, 4]}, "list concat"
# Second wins on type conflict
assert _fn({"a": 1}, {"a": "override"}) == {"a": "override"}, "second wins"
# Empty dicts
assert _fn({}, {"a": 1}) == {"a": 1}, "empty first"
assert _fn({"a": 1}, {}) == {"a": 1}, "empty second"
""",
    },
    {
        "id": "find_all_paths",
        "patterns": [r"find.*all.*path", r"all.*path.*graph", r"dfs.*path.*graph"],
        "mode": "property_checks",
        "tests": """
# === CANONICAL HARNESS: find_all_paths (property-based) ===
_fn = None
for _name in ['find_all_paths', 'all_paths', 'find_paths', 'dfs_paths']:
    _fn = globals().get(_name)
    if _fn and callable(_fn):
        break
assert _fn is not None, "No path-finding function found"

_g = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
_paths = _fn(_g, "A", "D")
# Property: all paths start with A and end with D
for _p in _paths:
    assert _p[0] == "A" and _p[-1] == "D", f"path must go A->D: {_p}"
# Property: at least 2 paths exist (A->B->D and A->C->D)
assert len(_paths) >= 2, f"expected >=2 paths, got {len(_paths)}"
# Property: no path visits same node twice
for _p in _paths:
    assert len(_p) == len(set(_p)), f"cycle in path: {_p}"
# No path case
_paths2 = _fn({"A": ["B"], "B": []}, "A", "C")
assert _paths2 == [] or _paths2 == (), "no path should return empty"
""",
    },
    {
        "id": "lru_cache",
        "patterns": [r"lru.*cache", r"least.*recently.*used"],
        "mode": "canonical_tests",
        "tests": """
# === CANONICAL HARNESS: lru_cache ===
_cls = None
for _name in ['LRUCache', 'LruCache', 'Cache']:
    _cls = globals().get(_name)
    if _cls and isinstance(_cls, type):
        break
assert _cls is not None, "No LRUCache class found"

_c = _cls(2)  # capacity 2
_c.put(1, 1)
_c.put(2, 2)
assert _c.get(1) == 1, "key 1 should exist"
_c.put(3, 3)  # evicts key 2
assert _c.get(2) == -1, "key 2 should be evicted"
assert _c.get(3) == 3, "key 3 should exist"
_c.put(4, 4)  # evicts key 1
assert _c.get(1) == -1, "key 1 should be evicted"
assert _c.get(3) == 3, "key 3 still exists"
assert _c.get(4) == 4, "key 4 exists"
# Overwrite
_c.put(3, 30)
assert _c.get(3) == 30, "overwrite should update value"
""",
    },
    {
        "id": "retry_decorator",
        "patterns": [r"retry.*decorator", r"decorator.*retry.*backoff"],
        "mode": "no_verdict",
        "reason": "time_sensitive_backoff",
        "tests": "",
    },
    {
        "id": "rate_limiter",
        "patterns": [r"rate.*limit", r"token.*bucket"],
        "mode": "no_verdict",
        "reason": "time_sensitive_unhardened",
        "tests": "",
    },
]


@dataclass
class HarnessMatch:
    harness_id: str
    mode: str           # canonical_tests | property_checks | no_verdict | generated_assertions
    tests: str          # canonical test code to run against model's solution
    reason: str = ""    # for no_verdict: why


def match_harness(user_query: str) -> HarnessMatch | None:
    """Match a user query to a canonical harness.

    Returns HarnessMatch if a known task pattern is detected, None otherwise.
    When None, the caller should fall back to generated_assertions (model-authored tests).
    """
    q_lower = user_query.lower()
    for h in HARNESSES:
        for pattern in h["patterns"]:
            if re.search(pattern, q_lower):
                return HarnessMatch(
                    harness_id=h["id"],
                    mode=h["mode"],
                    tests=h.get("tests", ""),
                    reason=h.get("reason", ""),
                )
    return None


def run_harness(solution_code: str, harness: HarnessMatch, timeout: int = 15) -> dict:
    """Run canonical tests against the model's solution code.

    Returns:
        {
            "passed": bool,
            "harness_id": str,
            "mode": str,
            "error": str or None,
            "reason": str (for no_verdict)
        }
    """
    if harness.mode == "no_verdict":
        return {
            "passed": None,
            "harness_id": harness.harness_id,
            "mode": "no_verdict",
            "error": None,
            "reason": harness.reason,
        }

    # Combine solution + canonical tests
    combined = f"{solution_code}\n\n{harness.tests}"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(combined)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return {
                "passed": True,
                "harness_id": harness.harness_id,
                "mode": harness.mode,
                "error": None,
            }
        else:
            return {
                "passed": False,
                "harness_id": harness.harness_id,
                "mode": harness.mode,
                "error": result.stderr[-1000:] if result.stderr else "unknown error",
            }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "harness_id": harness.harness_id,
            "mode": harness.mode,
            "error": f"timeout after {timeout}s",
        }
    finally:
        os.unlink(tmp_path)
