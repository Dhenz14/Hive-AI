"""Benchmark tasks for evaluating coding model quality.

Four categories:
1. single_shot   - Generate code from a prompt, check syntax/compilability
2. refactor      - Multi-file refactoring, check cross-file consistency
3. debug         - Iterative fix loop: generate -> test -> fix
4. context       - Long-context retention: answer questions about distant code
"""

import ast
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskResult:
    task_id: str
    category: str
    passed: bool = False
    score: float = 0.0
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _check_python_syntax(code: str) -> tuple[bool, str]:
    """Check if Python code parses without syntax errors."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _extract_code_blocks(text: str) -> list[str]:
    """Extract fenced code blocks from markdown response."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        # Try unfenced: if the whole response looks like code
        lines = text.strip().split("\n")
        if lines and (lines[0].startswith("import ") or lines[0].startswith("from ")
                      or lines[0].startswith("def ") or lines[0].startswith("class ")):
            blocks = [text.strip()]
    return blocks


def _run_python_code(code: str, timeout: int = 15) -> tuple[bool, str]:
    """Execute Python code in a subprocess, return (success, output)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [sys.executable, f.name],
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "timeout"
        finally:
            Path(f.name).unlink(missing_ok=True)


def _keyword_overlap(response: str, keywords: list[str]) -> float:
    """Fraction of expected keywords found in the response."""
    if not keywords:
        return 1.0
    response_lower = response.lower()
    found = sum(1 for kw in keywords if kw.lower() in response_lower)
    return found / len(keywords)


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

SINGLE_SHOT_TASKS = [
    {
        "id": "ss-1-fastapi",
        "prompt": (
            "Write a Python FastAPI endpoint POST /items that accepts a JSON body with "
            "fields: name (str, required, 1-100 chars), price (float, required, > 0), "
            "tags (list[str], optional). Return 201 with the created item including an "
            "auto-generated UUID id field. Include the Pydantic models."
        ),
        "keywords": ["fastapi", "pydantic", "basemodel", "uuid", "post"],
    },
    {
        "id": "ss-2-async-queue",
        "prompt": (
            "Write a Python async task queue using asyncio. It should support: "
            "enqueue(coroutine), a configurable number of workers, graceful shutdown, "
            "and retry with exponential backoff on failure (max 3 retries). "
            "Include a usage example that enqueues 10 tasks."
        ),
        "keywords": ["asyncio", "await", "queue", "retry", "backoff", "worker"],
    },
    {
        "id": "ss-3-binary-tree",
        "prompt": (
            "Implement a self-balancing AVL tree in Python with insert, delete, search, "
            "and in-order traversal. Include rotation methods and a function to verify "
            "the AVL balance property. Add a test that inserts 1000 random integers "
            "and verifies the tree stays balanced."
        ),
        "keywords": ["rotate", "balance", "height", "insert", "delete", "avl"],
    },
    {
        "id": "ss-4-decorator",
        "prompt": (
            "Write a Python decorator @cached that implements LRU caching with: "
            "configurable max_size, TTL expiration in seconds, thread-safety, "
            "and a .cache_info() method on the wrapped function that returns "
            "hits, misses, and current size. Do not use functools.lru_cache."
        ),
        "keywords": ["decorator", "lock", "threading", "ttl", "cache_info", "ordereddict"],
    },
    {
        "id": "ss-5-sql-builder",
        "prompt": (
            "Write a Python SQL query builder class that supports SELECT, WHERE, JOIN, "
            "ORDER BY, GROUP BY, HAVING, LIMIT, and parameterized queries (no SQL injection). "
            "Use method chaining. Example: "
            'Query("users").select("name", "email").where("age > ?", 18).join("orders", "users.id = orders.user_id").limit(10).build() '
            "should return the SQL string and parameters tuple."
        ),
        "keywords": ["select", "where", "join", "parameterized", "build", "order_by"],
    },
]


REFACTOR_TASKS = [
    {
        "id": "rf-1-sync-to-async",
        "prompt": (
            "Refactor the following synchronous database module to use async/await with "
            "aiosqlite. Preserve the exact same public API (function names and signatures) "
            "but make all functions async. Handle connection pooling.\n\n"
            "```python\n"
            "import sqlite3\n"
            "from contextlib import contextmanager\n\n"
            "DB_PATH = 'app.db'\n\n"
            "@contextmanager\n"
            "def get_conn():\n"
            "    conn = sqlite3.connect(DB_PATH)\n"
            "    conn.row_factory = sqlite3.Row\n"
            "    try:\n"
            "        yield conn\n"
            "    finally:\n"
            "        conn.close()\n\n"
            "def get_user(user_id: int) -> dict | None:\n"
            "    with get_conn() as conn:\n"
            "        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()\n"
            "        return dict(row) if row else None\n\n"
            "def create_user(name: str, email: str) -> int:\n"
            "    with get_conn() as conn:\n"
            "        cursor = conn.execute('INSERT INTO users (name, email) VALUES (?, ?)', (name, email))\n"
            "        conn.commit()\n"
            "        return cursor.lastrowid\n\n"
            "def list_users(limit: int = 100) -> list[dict]:\n"
            "    with get_conn() as conn:\n"
            "        rows = conn.execute('SELECT * FROM users LIMIT ?', (limit,)).fetchall()\n"
            "        return [dict(r) for r in rows]\n"
            "```"
        ),
        "keywords": ["async", "await", "aiosqlite", "get_user", "create_user", "list_users"],
        "required_functions": ["get_user", "create_user", "list_users"],
    },
    {
        "id": "rf-2-class-extract",
        "prompt": (
            "Refactor this monolithic function into a clean class hierarchy. Extract at "
            "least 3 classes with single responsibility. Keep the same behavior.\n\n"
            "```python\n"
            "def process_order(order_data: dict) -> dict:\n"
            "    # Validate\n"
            "    if not order_data.get('items'):\n"
            "        raise ValueError('Order must have items')\n"
            "    for item in order_data['items']:\n"
            "        if item['quantity'] <= 0:\n"
            "            raise ValueError(f'Invalid quantity for {item[\"name\"]}')\n"
            "        if item['price'] < 0:\n"
            "            raise ValueError(f'Invalid price for {item[\"name\"]}')\n"
            "    \n"
            "    # Calculate totals\n"
            "    subtotal = sum(i['price'] * i['quantity'] for i in order_data['items'])\n"
            "    tax_rate = 0.08\n"
            "    if order_data.get('state') == 'OR':\n"
            "        tax_rate = 0.0\n"
            "    elif order_data.get('state') == 'CA':\n"
            "        tax_rate = 0.0725\n"
            "    tax = subtotal * tax_rate\n"
            "    \n"
            "    # Apply discount\n"
            "    discount = 0\n"
            "    if order_data.get('coupon') == 'SAVE10':\n"
            "        discount = subtotal * 0.10\n"
            "    elif order_data.get('coupon') == 'SAVE20':\n"
            "        discount = subtotal * 0.20\n"
            "    elif subtotal > 100:\n"
            "        discount = 5.0\n"
            "    \n"
            "    total = subtotal + tax - discount\n"
            "    \n"
            "    # Format receipt\n"
            "    lines = ['=== RECEIPT ===']\n"
            "    for item in order_data['items']:\n"
            "        lines.append(f\"{item['name']} x{item['quantity']} @ ${item['price']:.2f}\")\n"
            "    lines.append(f'Subtotal: ${subtotal:.2f}')\n"
            "    lines.append(f'Tax: ${tax:.2f}')\n"
            "    if discount > 0:\n"
            "        lines.append(f'Discount: -${discount:.2f}')\n"
            "    lines.append(f'Total: ${total:.2f}')\n"
            "    \n"
            "    return {'total': total, 'tax': tax, 'discount': discount, 'receipt': '\\n'.join(lines)}\n"
            "```"
        ),
        "keywords": ["class", "validate", "calculate", "receipt", "discount", "tax"],
        "min_classes": 3,
    },
]


DEBUG_TASKS = [
    {
        "id": "db-1-off-by-one",
        "prompt": (
            "The following function has a bug. Find and fix it, then explain what was wrong.\n\n"
            "```python\n"
            "def binary_search(arr: list[int], target: int) -> int:\n"
            "    '''Return index of target in sorted array, or -1 if not found.'''\n"
            "    left, right = 0, len(arr)\n"
            "    while left < right:\n"
            "        mid = (left + right) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            left = mid\n"
            "        else:\n"
            "            right = mid\n"
            "    return -1\n"
            "```\n\n"
            "Test case that fails: binary_search([1, 3, 5, 7, 9], 9) hangs forever."
        ),
        "keywords": ["left = mid + 1", "infinite loop", "off-by-one"],
        "expected_fix": "left = mid + 1",
    },
    {
        "id": "db-2-race-condition",
        "prompt": (
            "This concurrent counter has a race condition. Fix it and explain the issue.\n\n"
            "```python\n"
            "import threading\n\n"
            "class Counter:\n"
            "    def __init__(self):\n"
            "        self.value = 0\n"
            "    \n"
            "    def increment(self):\n"
            "        current = self.value\n"
            "        self.value = current + 1\n"
            "    \n"
            "    def get(self):\n"
            "        return self.value\n\n"
            "counter = Counter()\n"
            "threads = [threading.Thread(target=counter.increment) for _ in range(1000)]\n"
            "for t in threads: t.start()\n"
            "for t in threads: t.join()\n"
            "print(counter.get())  # Expected: 1000, Actual: varies\n"
            "```"
        ),
        "keywords": ["lock", "threading.Lock", "race condition", "atomic"],
        "expected_fix": "Lock",
    },
    {
        "id": "db-3-memory-leak",
        "prompt": (
            "This caching decorator leaks memory. Find the issue and fix it.\n\n"
            "```python\n"
            "def memoize(func):\n"
            "    cache = {}\n"
            "    def wrapper(*args, **kwargs):\n"
            "        key = (args, tuple(sorted(kwargs.items())))\n"
            "        if key not in cache:\n"
            "            cache[key] = func(*args, **kwargs)\n"
            "        return cache[key]\n"
            "    return wrapper\n\n"
            "@memoize\n"
            "def process_data(data: bytes) -> str:\n"
            "    return data.decode('utf-8').upper()\n\n"
            "# Called millions of times with unique data\n"
            "for i in range(10_000_000):\n"
            "    process_data(f'data-{i}'.encode())\n"
            "```"
        ),
        "keywords": ["unbounded", "maxsize", "evict", "lru", "weakref"],
        "expected_fix": "maxsize",
    },
]


CONTEXT_TASKS = [
    {
        "id": "ctx-1-find-bug-deep",
        "prompt_template": (
            "Here is a large Python module. There is a bug in the `{target_func}` function "
            "near the end of the file. What is the bug and how would you fix it?\n\n"
            "```python\n{code}\n```"
        ),
        "target_func": "calculate_final_score",
        "bug_description": "divides by zero when all weights are zero",
        "keywords": ["zero", "division", "weight", "check"],
    },
    {
        "id": "ctx-2-trace-dependency",
        "prompt_template": (
            "Read this entire module carefully. The `{target_func}` function at the end "
            "calls several internal functions. Trace the full call chain and list every "
            "function it depends on, in order.\n\n"
            "```python\n{code}\n```"
        ),
        "target_func": "run_pipeline",
        "keywords": ["validate", "transform", "aggregate", "format"],
    },
]


def _generate_long_module(target_func: str, variant: str = "bug") -> str:
    """Generate a realistic long Python module for context retention tests."""
    # ~150 lines of realistic filler, then target function near the end
    parts = []

    parts.append(textwrap.dedent('''\
        """Data processing pipeline for analytics dashboard."""

        import math
        import statistics
        from dataclasses import dataclass, field
        from typing import Optional


        @dataclass
        class DataPoint:
            timestamp: float
            value: float
            category: str
            weight: float = 1.0
            is_valid: bool = True


        @dataclass
        class ProcessingConfig:
            min_value: float = 0.0
            max_value: float = 1000.0
            outlier_std_devs: float = 3.0
            smoothing_window: int = 5
            normalize: bool = True
            categories: list[str] = field(default_factory=lambda: ["A", "B", "C"])


        def validate_data(points: list[DataPoint], config: ProcessingConfig) -> list[DataPoint]:
            """Remove invalid and out-of-range data points."""
            valid = []
            for p in points:
                if not p.is_valid:
                    continue
                if p.value < config.min_value or p.value > config.max_value:
                    continue
                if p.category not in config.categories:
                    continue
                valid.append(p)
            return valid


        def remove_outliers(points: list[DataPoint], config: ProcessingConfig) -> list[DataPoint]:
            """Remove statistical outliers based on standard deviation."""
            if len(points) < 3:
                return points
            values = [p.value for p in points]
            mean = statistics.mean(values)
            std = statistics.stdev(values)
            threshold = config.outlier_std_devs * std
            return [p for p in points if abs(p.value - mean) <= threshold]


        def smooth_values(points: list[DataPoint], config: ProcessingConfig) -> list[DataPoint]:
            """Apply moving average smoothing."""
            if len(points) < config.smoothing_window:
                return points
            result = []
            values = [p.value for p in points]
            for i in range(len(values)):
                start = max(0, i - config.smoothing_window // 2)
                end = min(len(values), i + config.smoothing_window // 2 + 1)
                window = values[start:end]
                smoothed = sum(window) / len(window)
                new_point = DataPoint(
                    timestamp=points[i].timestamp,
                    value=smoothed,
                    category=points[i].category,
                    weight=points[i].weight,
                    is_valid=True,
                )
                result.append(new_point)
            return result


        def normalize_values(points: list[DataPoint]) -> list[DataPoint]:
            """Scale values to 0-1 range."""
            if not points:
                return points
            values = [p.value for p in points]
            min_val = min(values)
            max_val = max(values)
            if max_val == min_val:
                return [DataPoint(p.timestamp, 0.5, p.category, p.weight) for p in points]
            result = []
            for p in points:
                normalized = (p.value - min_val) / (max_val - min_val)
                result.append(DataPoint(p.timestamp, normalized, p.category, p.weight))
            return result


        def group_by_category(points: list[DataPoint]) -> dict[str, list[DataPoint]]:
            """Group data points by their category."""
            groups: dict[str, list[DataPoint]] = {}
            for p in points:
                groups.setdefault(p.category, []).append(p)
            return groups


        def aggregate_group(points: list[DataPoint]) -> dict:
            """Calculate summary statistics for a group of points."""
            if not points:
                return {"count": 0, "mean": 0, "std": 0, "min": 0, "max": 0}
            values = [p.value for p in points]
            return {
                "count": len(values),
                "mean": statistics.mean(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "max": max(values),
                "weighted_mean": sum(p.value * p.weight for p in points) / sum(p.weight for p in points),
            }


        def format_report(aggregated: dict[str, dict]) -> str:
            """Format aggregated results into a text report."""
            lines = ["=== Analytics Report ===", ""]
            for category, stats in sorted(aggregated.items()):
                lines.append(f"Category: {category}")
                lines.append(f"  Count: {stats['count']}")
                lines.append(f"  Mean:  {stats['mean']:.4f}")
                lines.append(f"  Std:   {stats['std']:.4f}")
                lines.append(f"  Range: [{stats['min']:.4f}, {stats['max']:.4f}]")
                lines.append("")
            return "\\n".join(lines)


        def transform_data(points: list[DataPoint], config: ProcessingConfig) -> list[DataPoint]:
            """Apply all transformations in sequence."""
            points = remove_outliers(points, config)
            points = smooth_values(points, config)
            if config.normalize:
                points = normalize_values(points)
            return points

    '''))

    # Add ~80 more lines of helper functions for padding
    parts.append(textwrap.dedent('''\
        def compute_trend(points: list[DataPoint]) -> float:
            """Simple linear regression slope."""
            n = len(points)
            if n < 2:
                return 0.0
            x = list(range(n))
            y = [p.value for p in points]
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
            denominator = sum((xi - x_mean) ** 2 for xi in x)
            if denominator == 0:
                return 0.0
            return numerator / denominator


        def detect_anomalies(points: list[DataPoint], threshold: float = 2.0) -> list[int]:
            """Return indices of anomalous points using z-score method."""
            if len(points) < 3:
                return []
            values = [p.value for p in points]
            mean = statistics.mean(values)
            std = statistics.stdev(values)
            if std == 0:
                return []
            return [i for i, v in enumerate(values) if abs((v - mean) / std) > threshold]


        def interpolate_missing(timestamps: list[float], values: list[float],
                                 target_timestamps: list[float]) -> list[float]:
            """Linear interpolation for missing timestamps."""
            result = []
            for t in target_timestamps:
                if t <= timestamps[0]:
                    result.append(values[0])
                elif t >= timestamps[-1]:
                    result.append(values[-1])
                else:
                    for i in range(len(timestamps) - 1):
                        if timestamps[i] <= t <= timestamps[i + 1]:
                            frac = (t - timestamps[i]) / (timestamps[i + 1] - timestamps[i])
                            interp = values[i] + frac * (values[i + 1] - values[i])
                            result.append(interp)
                            break
            return result


        def compute_percentiles(values: list[float], percentiles: list[int]) -> dict[int, float]:
            """Compute specified percentiles from a list of values."""
            if not values:
                return {p: 0.0 for p in percentiles}
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            result = {}
            for p in percentiles:
                idx = (p / 100) * (n - 1)
                lower = int(math.floor(idx))
                upper = min(lower + 1, n - 1)
                frac = idx - lower
                result[p] = sorted_vals[lower] + frac * (sorted_vals[upper] - sorted_vals[lower])
            return result

    '''))

    # Now add the target function with the bug
    if variant == "bug":
        parts.append(textwrap.dedent('''\
            def calculate_final_score(groups: dict[str, list[DataPoint]],
                                       weights: dict[str, float]) -> float:
                """Calculate weighted final score across all categories.

                Args:
                    groups: category -> list of data points
                    weights: category -> weight multiplier
                """
                total_score = 0.0
                total_weight = 0.0
                for category, points in groups.items():
                    if not points:
                        continue
                    cat_mean = statistics.mean([p.value for p in points])
                    w = weights.get(category, 0.0)
                    total_score += cat_mean * w
                    total_weight += w

                # BUG: no check for total_weight == 0, causes ZeroDivisionError
                return total_score / total_weight


            def run_pipeline(raw_data: list[DataPoint],
                              config: ProcessingConfig | None = None,
                              weights: dict[str, float] | None = None) -> dict:
                """Full processing pipeline from raw data to final report."""
                if config is None:
                    config = ProcessingConfig()
                if weights is None:
                    weights = {c: 1.0 for c in config.categories}

                validated = validate_data(raw_data, config)
                transformed = transform_data(validated, config)
                groups = group_by_category(transformed)
                aggregated = {cat: aggregate_group(pts) for cat, pts in groups.items()}
                report = format_report(aggregated)
                score = calculate_final_score(groups, weights)

                return {
                    "report": report,
                    "score": score,
                    "num_points": len(transformed),
                    "categories": list(groups.keys()),
                }
        '''))
    else:
        # No-bug variant for call-chain tracing
        parts.append(textwrap.dedent('''\
            def calculate_final_score(groups: dict[str, list[DataPoint]],
                                       weights: dict[str, float]) -> float:
                """Calculate weighted final score across all categories."""
                total_score = 0.0
                total_weight = 0.0
                for category, points in groups.items():
                    if not points:
                        continue
                    cat_mean = statistics.mean([p.value for p in points])
                    w = weights.get(category, 0.0)
                    total_score += cat_mean * w
                    total_weight += w
                if total_weight == 0:
                    return 0.0
                return total_score / total_weight


            def run_pipeline(raw_data: list[DataPoint],
                              config: ProcessingConfig | None = None,
                              weights: dict[str, float] | None = None) -> dict:
                """Full processing pipeline from raw data to final report."""
                if config is None:
                    config = ProcessingConfig()
                if weights is None:
                    weights = {c: 1.0 for c in config.categories}

                validated = validate_data(raw_data, config)
                transformed = transform_data(validated, config)
                groups = group_by_category(transformed)
                aggregated = {cat: aggregate_group(pts) for cat, pts in groups.items()}
                report = format_report(aggregated)
                score = calculate_final_score(groups, weights)

                return {
                    "report": report,
                    "score": score,
                    "num_points": len(transformed),
                    "categories": list(groups.keys()),
                }
        '''))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def evaluate_single_shot(response: str, task: dict) -> TaskResult:
    """Evaluate a single-shot code generation task."""
    result = TaskResult(task_id=task["id"], category="single_shot")
    blocks = _extract_code_blocks(response)

    if not blocks:
        result.details["reason"] = "no code blocks found"
        return result

    # Concatenate all code blocks for syntax check
    all_code = "\n\n".join(blocks)
    syntax_ok, syntax_err = _check_python_syntax(all_code)

    keyword_score = _keyword_overlap(response, task.get("keywords", []))

    result.details["num_blocks"] = len(blocks)
    result.details["syntax_valid"] = syntax_ok
    result.details["syntax_error"] = syntax_err
    result.details["keyword_score"] = round(keyword_score, 3)

    # Score: 40% syntax, 40% keywords, 20% has multiple blocks (completeness)
    score = 0.0
    if syntax_ok:
        score += 0.4
    score += keyword_score * 0.4
    if len(blocks) >= 2 or len(all_code.split("\n")) > 20:
        score += 0.2

    result.score = round(score, 3)
    result.passed = score >= 0.6
    return result


def evaluate_refactor(response: str, task: dict) -> TaskResult:
    """Evaluate a refactoring task."""
    result = TaskResult(task_id=task["id"], category="refactor")
    blocks = _extract_code_blocks(response)

    if not blocks:
        result.details["reason"] = "no code blocks found"
        return result

    all_code = "\n\n".join(blocks)
    syntax_ok, syntax_err = _check_python_syntax(all_code)

    # Count class definitions
    try:
        tree = ast.parse(all_code)
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    except SyntaxError:
        classes = []
        functions = []

    keyword_score = _keyword_overlap(response, task.get("keywords", []))

    # Check required functions preserved
    required = task.get("required_functions", [])
    preserved = sum(1 for f in required if f in functions) / len(required) if required else 1.0

    min_classes = task.get("min_classes", 2)
    class_score = min(1.0, len(classes) / min_classes) if min_classes else 1.0

    result.details["syntax_valid"] = syntax_ok
    result.details["classes_found"] = classes
    result.details["functions_found"] = functions
    result.details["keyword_score"] = round(keyword_score, 3)
    result.details["preserved_api"] = round(preserved, 3)
    result.details["class_score"] = round(class_score, 3)

    score = 0.0
    if syntax_ok:
        score += 0.3
    score += keyword_score * 0.2
    score += class_score * 0.25
    score += preserved * 0.25

    result.score = round(score, 3)
    result.passed = score >= 0.6
    return result


def evaluate_debug(response: str, task: dict) -> TaskResult:
    """Evaluate a debugging task."""
    result = TaskResult(task_id=task["id"], category="debug")

    keyword_score = _keyword_overlap(response, task.get("keywords", []))
    has_fix = task.get("expected_fix", "") in response

    blocks = _extract_code_blocks(response)
    has_code = len(blocks) > 0
    syntax_ok = False
    if blocks:
        syntax_ok, _ = _check_python_syntax("\n\n".join(blocks))

    # Check if explanation is present (not just code)
    explanation_lines = [l for l in response.split("\n")
                         if l.strip() and not l.strip().startswith("```")
                         and not l.strip().startswith("#")]
    has_explanation = len(explanation_lines) >= 3

    result.details["has_fix"] = has_fix
    result.details["keyword_score"] = round(keyword_score, 3)
    result.details["has_code"] = has_code
    result.details["syntax_valid"] = syntax_ok
    result.details["has_explanation"] = has_explanation

    score = 0.0
    if has_fix:
        score += 0.35
    score += keyword_score * 0.25
    if has_code and syntax_ok:
        score += 0.2
    if has_explanation:
        score += 0.2

    result.score = round(score, 3)
    result.passed = score >= 0.6
    return result


def evaluate_context(response: str, task: dict) -> TaskResult:
    """Evaluate a context retention task."""
    result = TaskResult(task_id=task["id"], category="context")

    keyword_score = _keyword_overlap(response, task.get("keywords", []))
    mentions_target = task.get("target_func", "") in response

    # Check that the response references the specific function
    bug_desc = task.get("bug_description", "")
    mentions_bug = bug_desc != "" and any(
        word in response.lower() for word in bug_desc.lower().split()[:3]
    )

    result.details["keyword_score"] = round(keyword_score, 3)
    result.details["mentions_target"] = mentions_target
    result.details["mentions_bug"] = mentions_bug

    score = 0.0
    score += keyword_score * 0.4
    if mentions_target:
        score += 0.3
    if mentions_bug or bug_desc == "":
        score += 0.3

    result.score = round(score, 3)
    result.passed = score >= 0.5
    return result


def get_all_tasks() -> list[dict]:
    """Return all tasks with their category and evaluator."""
    tasks = []

    for t in SINGLE_SHOT_TASKS:
        tasks.append({**t, "category": "single_shot", "evaluator": evaluate_single_shot})

    for t in REFACTOR_TASKS:
        tasks.append({**t, "category": "refactor", "evaluator": evaluate_refactor})

    for t in DEBUG_TASKS:
        tasks.append({**t, "category": "debug", "evaluator": evaluate_debug})

    # Context tasks need the generated module
    for t in CONTEXT_TASKS:
        variant = "bug" if "bug" in t["id"] else "trace"
        code = _generate_long_module(t["target_func"], variant)
        prompt = t["prompt_template"].format(target_func=t["target_func"], code=code)
        tasks.append({
            **t,
            "prompt": prompt,
            "category": "context",
            "evaluator": evaluate_context,
        })

    return tasks
