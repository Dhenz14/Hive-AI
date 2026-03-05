"""Error-driven learning -- analyze failures, generate targeted training data, and self-correct."""

PAIRS = [
    (
        "local-ai/error-pattern-analysis",
        "Show error pattern analysis for AI self-improvement: categorize failures, extract error signatures, and generate targeted training data from mistakes.",
        """Error pattern analysis and targeted data generation:

```python
import json
import re
import traceback
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from typing import Optional
from datetime import datetime


@dataclass
class CodeFailure:
    \"\"\"Record of a failed code generation attempt.\"\"\"
    task_id: str
    prompt: str
    generated_code: str
    error_type: str        # syntax, runtime, logic, timeout, quality
    error_message: str
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    category: str = ""
    difficulty: float = 0.5
    timestamp: str = ""


@dataclass
class ErrorPattern:
    \"\"\"Recurring error pattern extracted from failures.\"\"\"
    pattern_name: str
    error_type: str
    frequency: int
    example_failures: list[str] = field(default_factory=list)
    fix_template: str = ""
    training_pairs_generated: int = 0


class ErrorAnalyzer:
    \"\"\"Analyze code generation failures to find systematic weaknesses.

    Pipeline:
    1. Collect failures from self-training attempts
    2. Classify errors by type and extract patterns
    3. Cluster similar errors into systematic weaknesses
    4. Generate targeted training data for each weakness
    5. Prioritize training on highest-impact patterns
    \"\"\"

    def __init__(self):
        self.failures: list[CodeFailure] = []
        self.patterns: dict[str, ErrorPattern] = {}
        self.error_classifiers = {
            "syntax": self._classify_syntax,
            "runtime": self._classify_runtime,
            "logic": self._classify_logic,
            "quality": self._classify_quality,
        }

    def record_failure(self, failure: CodeFailure):
        \"\"\"Record and classify a new failure.\"\"\"
        if not failure.error_type:
            failure.error_type = self._auto_classify(failure)
        if not failure.timestamp:
            failure.timestamp = datetime.now().isoformat()
        self.failures.append(failure)
        self._update_patterns(failure)

    def _auto_classify(self, failure: CodeFailure) -> str:
        \"\"\"Classify error type from error message.\"\"\"
        msg = failure.error_message.lower()
        if any(kw in msg for kw in ["syntaxerror", "indentation", "unexpected"]):
            return "syntax"
        if any(kw in msg for kw in ["nameerror", "typeerror", "attributeerror",
                                      "indexerror", "keyerror", "valueerror"]):
            return "runtime"
        if any(kw in msg for kw in ["timeout", "time limit"]):
            return "timeout"
        if any(kw in msg for kw in ["wrong answer", "assertion", "expected"]):
            return "logic"
        return "quality"

    def _classify_syntax(self, failure: CodeFailure) -> str:
        msg = failure.error_message
        if "IndentationError" in msg:
            return "syntax/indentation"
        if "unterminated string" in msg:
            return "syntax/string_literal"
        if "unmatched" in msg or "bracket" in msg:
            return "syntax/brackets"
        if "invalid syntax" in msg:
            return "syntax/general"
        return "syntax/other"

    def _classify_runtime(self, failure: CodeFailure) -> str:
        msg = failure.error_message
        if "NameError" in msg:
            return "runtime/undefined_variable"
        if "TypeError" in msg and "argument" in msg:
            return "runtime/wrong_args"
        if "TypeError" in msg:
            return "runtime/type_mismatch"
        if "IndexError" in msg:
            return "runtime/off_by_one"
        if "KeyError" in msg:
            return "runtime/missing_key"
        if "AttributeError" in msg:
            return "runtime/wrong_attribute"
        return "runtime/other"

    def _classify_logic(self, failure: CodeFailure) -> str:
        if failure.expected_output and failure.actual_output:
            expected = str(failure.expected_output).strip()
            actual = str(failure.actual_output).strip()
            if expected and actual:
                # Off-by-one in numeric output
                try:
                    exp_num = float(expected)
                    act_num = float(actual)
                    if abs(exp_num - act_num) <= 1:
                        return "logic/off_by_one"
                except ValueError:
                    pass
                # Reversed output
                if expected == actual[::-1]:
                    return "logic/reversed"
                # Partial match
                if expected in actual or actual in expected:
                    return "logic/partial_solution"
        return "logic/wrong_algorithm"

    def _classify_quality(self, failure: CodeFailure) -> str:
        return "quality/below_threshold"

    def _update_patterns(self, failure: CodeFailure):
        \"\"\"Extract or update error pattern from failure.\"\"\"
        sub_type = self.error_classifiers.get(
            failure.error_type, lambda f: f.error_type
        )(failure)

        if sub_type not in self.patterns:
            self.patterns[sub_type] = ErrorPattern(
                pattern_name=sub_type,
                error_type=failure.error_type,
                frequency=0,
            )
        pattern = self.patterns[sub_type]
        pattern.frequency += 1
        if len(pattern.example_failures) < 5:
            pattern.example_failures.append(failure.task_id)

    def get_weakness_report(self) -> list[dict]:
        \"\"\"Rank weaknesses by frequency and impact.\"\"\"
        ranked = sorted(self.patterns.values(),
                        key=lambda p: p.frequency, reverse=True)
        return [
            {
                "pattern": p.pattern_name,
                "frequency": p.frequency,
                "pct_of_failures": p.frequency / max(1, len(self.failures)),
                "examples": p.example_failures[:3],
                "needs_training_data": p.training_pairs_generated < p.frequency,
            }
            for p in ranked
        ]

    def generate_targeted_pairs(self, pattern_name: str,
                                  n_pairs: int = 10) -> list[dict]:
        \"\"\"Generate training pairs that specifically target a weakness.

        For each error pattern, create examples that:
        1. Show the WRONG approach (what the model does)
        2. Show the CORRECT approach (what it should do)
        3. Include the reasoning for why the correct approach works
        \"\"\"
        pattern = self.patterns.get(pattern_name)
        if not pattern:
            return []

        # Get example failures for this pattern
        relevant = [f for f in self.failures
                     if self._get_subtype(f) == pattern_name][:5]

        pairs = []
        for failure in relevant:
            pair = self._create_correction_pair(failure, pattern)
            if pair:
                pairs.append(pair)
                pattern.training_pairs_generated += 1

        return pairs[:n_pairs]

    def _get_subtype(self, failure: CodeFailure) -> str:
        classifier = self.error_classifiers.get(
            failure.error_type, lambda f: f.error_type)
        return classifier(failure)

    def _create_correction_pair(self, failure: CodeFailure,
                                  pattern: ErrorPattern) -> Optional[dict]:
        \"\"\"Create a training pair from a failure.

        Format: prompt -> correct solution with explanation of the pitfall.
        \"\"\"
        # Build a prompt that teaches the correct approach
        correction_prompt = (
            f"{failure.prompt}\\n\\n"
            f"Common mistake to avoid: {pattern.pattern_name}\\n"
            f"Previous incorrect attempt produced: {failure.error_message}"
        )

        # The response should show the correct solution
        # In a real system, this would use a stronger model or verified solution
        return {
            "category": f"error-correction/{pattern.pattern_name}",
            "prompt": correction_prompt,
            "response": None,  # Filled by teacher model or human
            "metadata": {
                "source": "error_analysis",
                "pattern": pattern.pattern_name,
                "original_task": failure.task_id,
            },
        }


class FailureReplayBuffer:
    \"\"\"Maintain a buffer of hard examples for replay during training.

    Key insight: the model learns fastest from examples it recently
    got wrong. Replay these during training with higher weight.
    \"\"\"

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self.buffer: list[dict] = []  # (pair, difficulty, failure_count)
        self.failure_counts: Counter = Counter()

    def add_failure(self, task_id: str, pair: dict, difficulty: float):
        \"\"\"Add a failed example to the replay buffer.\"\"\"
        self.failure_counts[task_id] += 1
        entry = {
            "pair": pair,
            "difficulty": difficulty,
            "failure_count": self.failure_counts[task_id],
            "added_at": datetime.now().isoformat(),
        }
        self.buffer.append(entry)
        if len(self.buffer) > self.max_size:
            # Remove easiest examples (lowest difficulty * failure_count)
            self.buffer.sort(
                key=lambda x: x["difficulty"] * x["failure_count"],
                reverse=True,
            )
            self.buffer = self.buffer[:self.max_size]

    def sample_replay_batch(self, batch_size: int = 16) -> list[dict]:
        \"\"\"Sample hard examples weighted by failure count.\"\"\"
        if not self.buffer:
            return []
        weights = [e["failure_count"] * e["difficulty"] for e in self.buffer]
        total = sum(weights) or 1
        probs = [w / total for w in weights]

        import random
        indices = random.choices(range(len(self.buffer)),
                                  weights=probs, k=min(batch_size, len(self.buffer)))
        return [self.buffer[i]["pair"] for i in indices]

    def remove_mastered(self, task_ids: list[str]):
        \"\"\"Remove examples the model now handles correctly.\"\"\"
        mastered = set(task_ids)
        self.buffer = [
            e for e in self.buffer
            if e["pair"].get("task_id") not in mastered
        ]
```

Key patterns:
1. **Error taxonomy** -- classify failures into syntax/runtime/logic/quality sub-types for targeted training
2. **Pattern frequency** -- rank weaknesses by how often they occur; fix highest-impact patterns first
3. **Correction pairs** -- transform failures into training data showing the pitfall and correct approach
4. **Failure replay** -- maintain buffer of hard examples; sample weighted by difficulty and failure count
5. **Mastery tracking** -- remove examples from replay once the model handles them correctly"""
    ),
    (
        "local-ai/automated-test-generation",
        "Show automated test generation for AI self-improvement: the AI generates test cases for its own code, discovers edge cases, and creates training data from failures.",
        """Automated test generation for self-improvement:

```python
import ast
import subprocess
import sys
import tempfile
import os
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class TestCase:
    \"\"\"A generated test case for validating code.\"\"\"
    input_data: Any
    expected_output: Any
    test_type: str = "functional"  # functional, edge, performance, type
    description: str = ""


@dataclass
class TestResult:
    \"\"\"Result of running a test case.\"\"\"
    test: TestCase
    passed: bool
    actual_output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class TestGenerator:
    \"\"\"Generate test cases for code the AI writes.

    Strategy: for each function signature, generate:
    1. Normal cases (happy path)
    2. Edge cases (empty, zero, None, boundary values)
    3. Type confusion cases (wrong types that should be handled)
    4. Performance cases (large inputs)
    \"\"\"

    def generate_tests(self, code: str, function_name: str,
                        n_tests: int = 10) -> list[TestCase]:
        \"\"\"Generate test cases by analyzing function signature and body.\"\"\"
        tests = []

        # Parse function signature
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                func_node = node
                break

        if not func_node:
            return []

        # Analyze parameters
        params = self._extract_params(func_node)

        # Generate test categories
        tests.extend(self._normal_cases(params))
        tests.extend(self._edge_cases(params))
        tests.extend(self._boundary_cases(params))
        tests.extend(self._type_cases(params))

        return tests[:n_tests]

    def _extract_params(self, func_node: ast.FunctionDef) -> list[dict]:
        \"\"\"Extract parameter names, types, and defaults.\"\"\"
        params = []
        args = func_node.args

        for i, arg in enumerate(args.args):
            param = {"name": arg.arg, "type": "unknown", "has_default": False}

            # Check type annotation
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    param["type"] = arg.annotation.id
                elif isinstance(arg.annotation, ast.Subscript):
                    if isinstance(arg.annotation.value, ast.Name):
                        param["type"] = arg.annotation.value.id

            # Check for defaults
            n_defaults = len(args.defaults)
            n_args = len(args.args)
            if i >= n_args - n_defaults:
                param["has_default"] = True

            params.append(param)

        return params

    def _normal_cases(self, params: list[dict]) -> list[TestCase]:
        \"\"\"Generate typical happy-path test cases.\"\"\"
        type_examples = {
            "int": [1, 5, 42, -1, 100],
            "float": [1.0, 3.14, -2.5, 0.001],
            "str": ["hello", "world", "test string", "a"],
            "list": [[1, 2, 3], [10, 20], ["a", "b", "c"]],
            "dict": [{"a": 1}, {"key": "val", "num": 42}],
            "bool": [True, False],
            "unknown": [1, "test", [1, 2], True],
        }

        cases = []
        for param in params:
            examples = type_examples.get(param["type"], type_examples["unknown"])
            for val in examples[:2]:
                cases.append(TestCase(
                    input_data={param["name"]: val},
                    expected_output=None,  # Will be determined by execution
                    test_type="functional",
                    description=f"Normal case: {param['name']}={val!r}",
                ))
        return cases

    def _edge_cases(self, params: list[dict]) -> list[TestCase]:
        \"\"\"Generate edge cases for each parameter type.\"\"\"
        type_edges = {
            "int": [0, -1, 2**31 - 1, -2**31],
            "float": [0.0, float("inf"), float("-inf"), 1e-10],
            "str": ["", " ", "\\n", "a" * 1000],
            "list": [[], [0], list(range(1000))],
            "dict": [{}, {"": ""}, {i: i for i in range(100)}],
            "bool": [True, False, 0, 1],
            "unknown": [None, 0, "", [], {}],
        }

        cases = []
        for param in params:
            edges = type_edges.get(param["type"], type_edges["unknown"])
            for val in edges:
                cases.append(TestCase(
                    input_data={param["name"]: val},
                    expected_output=None,
                    test_type="edge",
                    description=f"Edge case: {param['name']}={val!r}",
                ))
        return cases

    def _boundary_cases(self, params: list[dict]) -> list[TestCase]:
        \"\"\"Generate boundary value cases.\"\"\"
        cases = []
        for param in params:
            if param["type"] == "int":
                for val in [-1, 0, 1]:
                    cases.append(TestCase(
                        input_data={param["name"]: val},
                        expected_output=None,
                        test_type="boundary",
                        description=f"Boundary: {param['name']}={val}",
                    ))
        return cases

    def _type_cases(self, params: list[dict]) -> list[TestCase]:
        \"\"\"Generate wrong-type cases to test robustness.\"\"\"
        type_confusions = {
            "int": ["1", 1.5, True, None],
            "str": [123, None, True, []],
            "list": ["not a list", 42, None],
            "dict": ["not a dict", [], None],
        }
        cases = []
        for param in params:
            confusions = type_confusions.get(param["type"], [None])
            for val in confusions[:2]:
                cases.append(TestCase(
                    input_data={param["name"]: val},
                    expected_output=None,
                    test_type="type",
                    description=f"Type confusion: {param['name']}={val!r}",
                ))
        return cases


class CodeExecutor:
    \"\"\"Safely execute generated code with test cases.\"\"\"

    def __init__(self, timeout_sec: float = 5.0):
        self.timeout = timeout_sec

    def run_tests(self, code: str, function_name: str,
                   tests: list[TestCase]) -> list[TestResult]:
        \"\"\"Execute code against test cases in isolated subprocess.\"\"\"
        results = []
        for test in tests:
            result = self._run_single(code, function_name, test)
            results.append(result)
        return results

    def _run_single(self, code: str, function_name: str,
                     test: TestCase) -> TestResult:
        \"\"\"Run a single test case in subprocess sandbox.\"\"\"
        import time

        # Build test script
        test_script = f'''
import json, sys, time
{code}

input_data = json.loads(sys.argv[1])
start = time.perf_counter()
try:
    result = {function_name}(**input_data)
    elapsed = (time.perf_counter() - start) * 1000
    print(json.dumps({{"output": repr(result), "time_ms": elapsed}}))
except Exception as e:
    print(json.dumps({{"error": str(e), "type": type(e).__name__}}))
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                           delete=False) as f:
            f.write(test_script)
            script_path = f.name

        try:
            start = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, script_path,
                 json.dumps(test.input_data)],
                capture_output=True, text=True,
                timeout=self.timeout,
            )
            elapsed = (time.perf_counter() - start) * 1000

            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout.strip())
                if "error" in data:
                    return TestResult(
                        test=test, passed=False,
                        error=f"{data.get('type', 'Error')}: {data['error']}",
                        execution_time_ms=elapsed,
                    )
                return TestResult(
                    test=test, passed=True,
                    actual_output=data["output"],
                    execution_time_ms=data.get("time_ms", elapsed),
                )
            else:
                return TestResult(
                    test=test, passed=False,
                    error=proc.stderr[:500] if proc.stderr else "No output",
                    execution_time_ms=elapsed,
                )
        except subprocess.TimeoutExpired:
            return TestResult(
                test=test, passed=False,
                error=f"Timeout after {self.timeout}s",
                execution_time_ms=self.timeout * 1000,
            )
        finally:
            os.unlink(script_path)


# Usage: generate tests, run them, feed failures back to training
generator = TestGenerator()
executor = CodeExecutor(timeout_sec=5.0)

sample_code = '''
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
'''

tests = generator.generate_tests(sample_code, "fibonacci", n_tests=8)
results = executor.run_tests(sample_code, "fibonacci", tests)

passed = sum(1 for r in results if r.passed)
failed = [r for r in results if not r.passed]
print(f"Passed: {passed}/{len(results)}")
for f in failed:
    print(f"  FAIL: {f.test.description} -> {f.error}")
```

Key patterns:
1. **Signature analysis** -- parse function AST to determine parameter types and generate relevant tests
2. **Test categories** -- normal, edge, boundary, and type confusion cases; systematic coverage
3. **Subprocess sandbox** -- execute untrusted code in isolated process with timeout; prevents hangs
4. **Failure extraction** -- failed tests become training signal; the AI learns from what it gets wrong
5. **Self-testing loop** -- generate code -> generate tests -> run -> extract failures -> retrain"""
    ),
]
