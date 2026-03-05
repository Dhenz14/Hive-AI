PAIRS = [
    (
        "ai-code-gen/ast-manipulation-code-transformation",
        "Explain AST-based code analysis and transformation including parsing source code into abstract syntax trees, visitor pattern traversal, automated refactoring operations, code generation from ASTs, and building custom linting rules with practical Python ast module examples",
        r"""# AST-Based Code Analysis and Transformation

## Why ASTs Matter for Code AI

Abstract Syntax Trees are the foundation of every code intelligence tool — linters, formatters, refactoring tools, and AI code generators all work with ASTs rather than raw text. This is critical **because** string manipulation is fragile (regex can't parse nested structures), while ASTs provide a structured, semantically meaningful representation of code. **Therefore**, understanding AST manipulation is essential for building reliable code tools.

### Parsing and Traversing Python ASTs

```python
import ast
import inspect
import textwrap
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

# --- AST analysis: complexity and code metrics ---

class ComplexityAnalyzer(ast.NodeVisitor):
    # Cyclomatic complexity = edges - nodes + 2*connected_components
    # Simplified: count decision points + 1
    # Best practice: flag functions with complexity > 10

    def __init__(self):
        self.results: list[dict] = []
        self._current_function: Optional[str] = None
        self._current_complexity: int = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._current_function = node.name
        self._current_complexity = 1  # Base complexity

        # Count all decision points
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                self._current_complexity += 1
            elif isinstance(child, ast.BoolOp):
                # Each 'and'/'or' adds a branch
                self._current_complexity += len(child.values) - 1
            elif isinstance(child, ast.ExceptHandler):
                self._current_complexity += 1
            elif isinstance(child, ast.Assert):
                self._current_complexity += 1
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                self._current_complexity += 1
                # Count comprehension conditions
                for generator in child.generators:
                    self._current_complexity += len(generator.ifs)

        self.results.append({
            "name": node.name,
            "line": node.lineno,
            "complexity": self._current_complexity,
            "args": len(node.args.args),
            "is_complex": self._current_complexity > 10,
        })

        self.generic_visit(node)

    # Also handle async functions
    visit_AsyncFunctionDef = visit_FunctionDef

class TypeAnnotationChecker(ast.NodeVisitor):
    # Check for missing type annotations
    # Common mistake: only checking function return types,
    # not parameter annotations

    def __init__(self):
        self.issues: list[dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Skip __init__ return type (always None)
        if node.name != "__init__" and node.returns is None:
            self.issues.append({
                "type": "missing_return_type",
                "function": node.name,
                "line": node.lineno,
            })

        for arg in node.args.args:
            if arg.arg != "self" and arg.annotation is None:
                self.issues.append({
                    "type": "missing_param_type",
                    "function": node.name,
                    "param": arg.arg,
                    "line": node.lineno,
                })

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

def analyze_code(source: str) -> dict:
    tree = ast.parse(source)

    # Run analyzers
    complexity = ComplexityAnalyzer()
    complexity.visit(tree)

    types = TypeAnnotationChecker()
    types.visit(tree)

    return {
        "functions": complexity.results,
        "type_issues": types.issues,
        "total_lines": len(source.splitlines()),
        "total_functions": len(complexity.results),
        "complex_functions": [f for f in complexity.results if f["is_complex"]],
    }

# Test analysis
sample_code = textwrap.dedent('''
    def process_data(items, threshold, mode):
        results = []
        for item in items:
            if item.value > threshold:
                if mode == "strict":
                    if item.validated and item.active:
                        results.append(item)
                elif mode == "lenient":
                    results.append(item)
                else:
                    raise ValueError(f"Unknown mode: {mode}")
            elif item.value < 0:
                try:
                    item.fix()
                except Exception:
                    pass
        return results

    def simple_add(a: int, b: int) -> int:
        return a + b
''')

report = analyze_code(sample_code)
for f in report["functions"]:
    print(f"  {f['name']}: complexity={f['complexity']}, complex={f['is_complex']}")
for issue in report["type_issues"]:
    print(f"  {issue['type']}: {issue.get('function', '')} {issue.get('param', '')}")
```

### AST Transformation: Automated Refactoring

**However**, AST analysis is only half the story. The real power comes from **transforming** ASTs — rewriting code programmatically. The **trade-off** is that AST transformation loses formatting and comments (Python's ast module doesn't preserve them), so production tools use CST (Concrete Syntax Tree) libraries like `libcst` instead.

```python
# --- AST transformers for automated refactoring ---

class PrintToLoggerTransformer(ast.NodeTransformer):
    # Convert print() calls to logger.info() calls
    # Pitfall: need to handle print with keyword arguments
    # (file=, end=, sep=, flush=)

    def __init__(self):
        self.transformations = 0

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "print":
                # Check for keyword args that don't map to logger
                has_file_kwarg = any(
                    kw.arg == "file" for kw in node.value.keywords
                )
                if has_file_kwarg:
                    return node  # Don't transform file= prints

                # Transform: print(x, y) -> logger.info("%s %s", x, y)
                # However, for simplicity we use f-string approach
                self.transformations += 1
                new_call = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="logger", ctx=ast.Load()),
                        attr="info",
                        ctx=ast.Load(),
                    ),
                    args=node.value.args,
                    keywords=[
                        kw for kw in node.value.keywords
                        if kw.arg not in ("file", "end", "flush")
                    ],
                )
                return ast.Expr(value=new_call)
        return node

class FStringConverter(ast.NodeTransformer):
    # Convert str.format() and % formatting to f-strings
    # Best practice: use f-strings for readability (Python 3.6+)

    def __init__(self):
        self.conversions = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)  # Visit children first

        # Detect "string".format(...) pattern
        if (isinstance(node.func, ast.Attribute) and
            node.func.attr == "format" and
            isinstance(node.func.value, ast.Constant) and
            isinstance(node.func.value.value, str)):

            template = node.func.value.value
            # Only handle simple positional {0}, {1} or {} cases
            if all(c in "{}0123456789" or c.isalpha() or c in " .,!?:;-_"
                   for c in template.replace("{{", "").replace("}}", "")):
                self.conversions += 1
                # Return the f-string as JoinedStr AST node
                # This is complex — simplified version returns original
                # In production, use libcst for safe transformations
                return node

        return node

class DeadCodeRemover(ast.NodeTransformer):
    # Remove unreachable code after return/raise/break/continue
    # Therefore, clean up code that can never execute

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        node.body = self._remove_dead_code(node.body)
        return node

    def _remove_dead_code(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        result: list[ast.stmt] = []
        for stmt in stmts:
            result.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                break  # Everything after is dead code
        return result if result else [ast.Pass()]

def refactor_code(source: str) -> str:
    tree = ast.parse(source)

    # Apply transformations in order
    transformer = PrintToLoggerTransformer()
    tree = transformer.visit(tree)

    dead_code = DeadCodeRemover()
    tree = dead_code.visit(tree)

    # Fix missing line numbers
    ast.fix_missing_locations(tree)

    # Unparse back to source
    # Trade-off: ast.unparse() loses comments and formatting
    return ast.unparse(tree)

# Demo
original = textwrap.dedent('''
    def greet(name):
        print("Hello", name)
        return name
        print("This is dead code")
        x = 42
''')

refactored = refactor_code(original)
print("Refactored:")
print(refactored)
```

### Building Custom Lint Rules

Custom linting rules catch project-specific anti-patterns that generic linters miss. The **best practice** is to write AST-based rules rather than regex-based ones.

```python
# --- Custom linter framework ---

@dataclass
class LintViolation:
    rule: str
    message: str
    file: str
    line: int
    column: int = 0
    severity: str = "warning"

class LintRule:
    rule_id: str = "CUSTOM000"
    description: str = ""

    def check(self, tree: ast.AST, filename: str) -> list[LintViolation]:
        raise NotImplementedError

class NoBareSleepRule(LintRule):
    rule_id = "CUSTOM001"
    description = "Disallow bare time.sleep() in async code"

    def check(self, tree: ast.AST, filename: str) -> list[LintViolation]:
        violations: list[LintViolation] = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == "sleep" and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "time"):
                # Check if we're inside an async function
                # Common mistake: using time.sleep in async code blocks the event loop
                violations.append(LintViolation(
                    rule=self.rule_id,
                    message="Use asyncio.sleep() instead of time.sleep() in async code",
                    file=filename,
                    line=node.lineno,
                ))
        return violations

class NoMutableDefaultArgsRule(LintRule):
    rule_id = "CUSTOM002"
    description = "Disallow mutable default arguments"

    MUTABLE_TYPES = {"List", "Dict", "Set", "list", "dict", "set"}

    def check(self, tree: ast.AST, filename: str) -> list[LintViolation]:
        violations: list[LintViolation] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        violations.append(LintViolation(
                            rule=self.rule_id,
                            message=(
                                f"Mutable default argument in {node.name}(). "
                                "Use None and create inside function body."
                            ),
                            file=filename,
                            line=default.lineno,
                        ))
        return violations

class Linter:
    def __init__(self):
        self.rules: list[LintRule] = [
            NoBareSleepRule(),
            NoMutableDefaultArgsRule(),
        ]

    def lint(self, source: str, filename: str = "<stdin>") -> list[LintViolation]:
        tree = ast.parse(source)
        violations: list[LintViolation] = []
        for rule in self.rules:
            violations.extend(rule.check(tree, filename))
        violations.sort(key=lambda v: v.line)
        return violations

# Test linter
bad_code = textwrap.dedent('''
    import time
    import asyncio

    async def fetch_data(urls, cache={}):
        for url in urls:
            time.sleep(1)
            cache[url] = "data"

    def process(items=[]):
        return items
''')

linter = Linter()
violations = linter.lint(bad_code, "example.py")
for v in violations:
    print(f"  {v.file}:{v.line} [{v.rule}] {v.message}")
```

## Summary and Key Takeaways

- **ASTs** provide structured, reliable code representation — always prefer AST manipulation over regex for code tools
- **`ast.NodeVisitor`** for read-only analysis (metrics, linting), **`ast.NodeTransformer`** for code rewriting
- A **common mistake** is forgetting to call `ast.fix_missing_locations()` after transformation — this causes `SyntaxError` when compiling
- The **trade-off** of Python's `ast` module vs `libcst`: `ast` is simpler but loses comments/formatting; `libcst` preserves everything but is more complex
- **Cyclomatic complexity > 10** is a reliable signal for functions that need refactoring
- **Custom lint rules** catch project-specific anti-patterns (mutable defaults, blocking sleep in async) that generic linters miss
- The **pitfall** of AST-based refactoring is handling edge cases — always test transformations against a large corpus before applying
- **Best practice**: combine AST analysis with AI code generation for intelligent refactoring suggestions"""
    ),
    (
        "ai-code-gen/llm-code-generation-patterns",
        "Explain LLM-based code generation patterns including fill-in-the-middle completion, repository-level context gathering, test-driven generation, iterative refinement with compiler feedback, and code review automation with practical implementation examples",
        r"""# LLM Code Generation: From Completion to Repository-Level Understanding

## Beyond Single-File Completion

Modern code AI goes far beyond autocomplete. **Because** real software development involves understanding project structure, API contracts, test patterns, and coding conventions, effective code generation requires **repository-level context**. The challenge is fitting relevant context into the LLM's limited context window while maximizing signal-to-noise ratio.

### Context Gathering and Retrieval

```python
import os
import re
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
import hashlib

# --- Repository context gathering ---

@dataclass
class FileContext:
    path: str
    content: str
    language: str
    relevance_score: float = 0.0
    # Metadata for ranking
    imports_target: bool = False
    same_directory: bool = False
    recently_modified: bool = False

@dataclass
class CodeContext:
    # What the LLM needs to generate good code
    target_file: str
    cursor_position: int
    prefix: str  # Code before cursor
    suffix: str  # Code after cursor (for fill-in-middle)
    related_files: list[FileContext] = field(default_factory=list)
    project_conventions: dict = field(default_factory=dict)

class ContextGatherer:
    # Best practice: gather context from multiple signals
    # Trade-off: more context = better generation but risks
    # exceeding context window and diluting relevant info

    def __init__(self, repo_root: str, max_context_tokens: int = 8000):
        self.repo_root = repo_root
        self.max_tokens = max_context_tokens
        self._file_index: dict[str, str] = {}

    def gather(self, target_file: str, cursor_pos: int) -> CodeContext:
        target_content = self._read_file(target_file)

        context = CodeContext(
            target_file=target_file,
            cursor_position=cursor_pos,
            prefix=target_content[:cursor_pos],
            suffix=target_content[cursor_pos:],
        )

        # 1. Find imports in target file
        imports = self._extract_imports(target_content)

        # 2. Find files that target imports from
        for imp in imports:
            resolved = self._resolve_import(imp, target_file)
            if resolved:
                content = self._read_file(resolved)
                context.related_files.append(FileContext(
                    path=resolved,
                    content=self._extract_signatures(content),
                    language=self._detect_language(resolved),
                    relevance_score=0.9,
                    imports_target=True,
                ))

        # 3. Find files in same directory (likely related)
        target_dir = os.path.dirname(target_file)
        for sibling in self._list_source_files(target_dir):
            if sibling != target_file and sibling not in [f.path for f in context.related_files]:
                content = self._read_file(sibling)
                context.related_files.append(FileContext(
                    path=sibling,
                    content=self._extract_signatures(content),
                    language=self._detect_language(sibling),
                    relevance_score=0.5,
                    same_directory=True,
                ))

        # 4. Find test files for target
        test_file = self._find_test_file(target_file)
        if test_file:
            content = self._read_file(test_file)
            context.related_files.append(FileContext(
                path=test_file,
                content=content[:2000],  # Truncate long test files
                language=self._detect_language(test_file),
                relevance_score=0.8,
            ))

        # 5. Extract project conventions
        context.project_conventions = self._detect_conventions(target_content)

        # Sort by relevance and trim to fit context window
        context.related_files.sort(key=lambda f: f.relevance_score, reverse=True)
        context.related_files = self._trim_to_token_budget(context.related_files)

        return context

    def _extract_imports(self, content: str) -> list[str]:
        imports = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line)
        return imports

    def _resolve_import(self, import_line: str, from_file: str) -> Optional[str]:
        # Resolve relative/absolute imports to file paths
        match = re.match(r"from\s+([\w.]+)\s+import", import_line)
        if match:
            module_path = match.group(1).replace(".", os.sep) + ".py"
            full_path = os.path.join(self.repo_root, module_path)
            if os.path.isfile(full_path):
                return full_path
        return None

    def _extract_signatures(self, content: str) -> str:
        # Extract only function/class signatures, not bodies
        # Therefore, more context fits in the window
        # Common mistake: including full file contents — wastes tokens
        lines = content.splitlines()
        signatures: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("def ", "async def ", "class ")):
                signatures.append(line)
                # Include decorators above
                j = i - 1
                while j >= 0 and lines[j].strip().startswith("@"):
                    signatures.insert(-1, lines[j])
                    j -= 1
        return "\n".join(signatures)

    def _detect_conventions(self, content: str) -> dict:
        return {
            "uses_type_hints": "def " in content and ":" in content and "->" in content,
            "uses_dataclasses": "@dataclass" in content,
            "uses_async": "async def" in content,
            "indent": "    " if "    " in content else "\t",
            "quote_style": "double" if '"""' in content or '"' in content else "single",
        }

    def _find_test_file(self, source_file: str) -> Optional[str]:
        name = os.path.basename(source_file)
        test_name = f"test_{name}"
        # Check tests/ directory and same directory
        for test_dir in ["tests", "test", "."]:
            test_path = os.path.join(
                os.path.dirname(source_file), test_dir, test_name
            )
            if os.path.isfile(test_path):
                return test_path
        return None

    def _detect_language(self, path: str) -> str:
        ext_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".rs": "rust", ".go": "go", ".java": "java"}
        ext = os.path.splitext(path)[1]
        return ext_map.get(ext, "unknown")

    def _list_source_files(self, directory: str) -> list[str]:
        if not os.path.isdir(directory):
            return []
        return [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.endswith((".py", ".js", ".ts"))
        ]

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return ""

    def _trim_to_token_budget(self, files: list[FileContext]) -> list[FileContext]:
        # Rough token estimate: 1 token per 4 characters
        total_tokens = 0
        result: list[FileContext] = []
        for f in files:
            file_tokens = len(f.content) // 4
            if total_tokens + file_tokens > self.max_tokens:
                # Truncate this file's content to fit
                remaining = (self.max_tokens - total_tokens) * 4
                if remaining > 200:
                    f.content = f.content[:remaining]
                    result.append(f)
                break
            total_tokens += file_tokens
            result.append(f)
        return result
```

### Iterative Generation with Compiler Feedback

The most powerful pattern is **iterative refinement**: generate code, compile/run tests, feed errors back to the LLM, and regenerate. This is how coding agents achieve high accuracy. **However**, the **pitfall** is infinite loops — set a maximum iteration count and bail out with the best attempt.

```python
# --- Iterative code generation with feedback ---

@dataclass
class GenerationResult:
    code: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    iterations: int = 0
    tests_passed: int = 0
    tests_total: int = 0

class IterativeCodeGenerator:
    # Generate -> Compile -> Test -> Fix loop
    # Best practice: include both compiler errors AND test failures
    # as feedback — LLMs are good at fixing specific errors

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.history: list[dict] = []

    def generate(
        self,
        task: str,
        context: CodeContext,
        test_code: str,
    ) -> GenerationResult:
        best_result = GenerationResult(code="", passed=False)

        for iteration in range(self.max_iterations):
            # Build prompt with context and previous errors
            prompt = self._build_prompt(task, context, iteration)
            generated_code = self._call_llm(prompt)

            # Try to compile
            compile_errors = self._check_syntax(generated_code)
            if compile_errors:
                self.history.append({
                    "iteration": iteration,
                    "type": "compile_error",
                    "errors": compile_errors,
                    "code": generated_code,
                })
                continue

            # Run tests
            test_result = self._run_tests(generated_code, test_code)

            result = GenerationResult(
                code=generated_code,
                passed=test_result["all_passed"],
                errors=test_result.get("failures", []),
                iterations=iteration + 1,
                tests_passed=test_result["passed"],
                tests_total=test_result["total"],
            )

            if result.passed:
                return result

            # Track best attempt (most tests passed)
            if result.tests_passed > best_result.tests_passed:
                best_result = result

            self.history.append({
                "iteration": iteration,
                "type": "test_failure",
                "errors": test_result["failures"],
                "code": generated_code,
            })

        return best_result

    def _build_prompt(self, task: str, context: CodeContext, iteration: int) -> str:
        parts = [f"Task: {task}\n"]

        # Add relevant file context
        if context.related_files:
            parts.append("Related code:")
            for f in context.related_files[:3]:
                parts.append(f"--- {f.path} ---")
                parts.append(f.content[:1500])

        # Add error feedback from previous iterations
        # Therefore, the LLM can learn from its mistakes
        if iteration > 0 and self.history:
            last = self.history[-1]
            parts.append("\nPrevious attempt had errors:")
            for error in last["errors"][:5]:
                parts.append(f"  - {error}")
            parts.append("\nFix these errors in your next attempt.")

        # Add conventions
        if context.project_conventions:
            conv = context.project_conventions
            parts.append("\nProject conventions:")
            if conv.get("uses_type_hints"):
                parts.append("  - Use type hints on all functions")
            if conv.get("uses_dataclasses"):
                parts.append("  - Use dataclasses for data types")

        return "\n".join(parts)

    def _call_llm(self, prompt: str) -> str:
        # Placeholder — in production, call Claude/GPT API
        # Pitfall: temperature 0 for code generation gives
        # deterministic but sometimes repetitive output
        # Trade-off: temperature 0.2-0.4 balances creativity with correctness
        return "# Generated code placeholder\npass"

    def _check_syntax(self, code: str) -> list[str]:
        try:
            compile(code, "<generated>", "exec")
            return []
        except SyntaxError as e:
            return [f"SyntaxError at line {e.lineno}: {e.msg}"]

    def _run_tests(self, code: str, test_code: str) -> dict:
        # Execute generated code + tests in isolated namespace
        # Common mistake: not isolating test execution
        namespace: dict = {}
        try:
            exec(code, namespace)
            exec(test_code, namespace)
            return {"all_passed": True, "passed": 1, "total": 1, "failures": []}
        except AssertionError as e:
            return {"all_passed": False, "passed": 0, "total": 1, "failures": [str(e)]}
        except Exception as e:
            return {"all_passed": False, "passed": 0, "total": 1, "failures": [f"{type(e).__name__}: {e}"]}

# --- Automated code review ---

@dataclass
class ReviewComment:
    line: int
    severity: str  # "error", "warning", "suggestion"
    category: str
    message: str

class AutomatedReviewer:
    # Combine static analysis with LLM review
    # Best practice: run rule-based checks first,
    # then use LLM for semantic issues

    def review(self, diff: str, context: CodeContext) -> list[ReviewComment]:
        comments: list[ReviewComment] = []

        # Rule-based checks (fast, reliable)
        comments.extend(self._check_security(diff))
        comments.extend(self._check_style(diff))
        comments.extend(self._check_performance(diff))

        # LLM-based review (slower, catches semantic issues)
        # However, LLM reviews can have false positives
        # comments.extend(self._llm_review(diff, context))

        return comments

    def _check_security(self, diff: str) -> list[ReviewComment]:
        comments: list[ReviewComment] = []
        patterns = [
            (r"eval\(", "Avoid eval() — use ast.literal_eval() for safe parsing"),
            (r"subprocess\..*shell=True", "Avoid shell=True — use list args to prevent injection"),
            (r"password.*=.*['\"]", "Hardcoded password detected — use environment variables"),
            (r"\.execute\(.*%s", "SQL injection risk — use parameterized queries"),
            (r"pickle\.load", "Pickle deserialization is unsafe — use JSON for untrusted data"),
        ]
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+") and not line.startswith("+++"):
                for pattern, message in patterns:
                    if re.search(pattern, line):
                        comments.append(ReviewComment(
                            line=i, severity="error",
                            category="security", message=message,
                        ))
        return comments

    def _check_style(self, diff: str) -> list[ReviewComment]:
        comments: list[ReviewComment] = []
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+") and not line.startswith("+++"):
                if len(line) > 120:
                    comments.append(ReviewComment(
                        line=i, severity="warning",
                        category="style", message="Line exceeds 120 characters",
                    ))
                if "TODO" in line or "FIXME" in line:
                    comments.append(ReviewComment(
                        line=i, severity="suggestion",
                        category="style", message="TODO/FIXME found — track in issue tracker",
                    ))
        return comments

    def _check_performance(self, diff: str) -> list[ReviewComment]:
        comments: list[ReviewComment] = []
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+"):
                if "for " in line and ".append(" in line:
                    comments.append(ReviewComment(
                        line=i, severity="suggestion",
                        category="performance",
                        message="Consider list comprehension instead of loop + append",
                    ))
        return comments
```

## Summary and Key Takeaways

- **Repository-level context** is essential for good code generation — gather imports, related files, tests, and conventions
- **Extract signatures only** from related files to maximize context window utilization — a **common mistake** is including full file contents
- **Iterative generation** (generate → compile → test → fix) dramatically improves accuracy — the LLM excels at fixing specific errors
- The **trade-off** of iteration count: more iterations = better results but higher latency and cost
- **Fill-in-the-middle** (prefix + suffix) gives better completions than prefix-only, because the model sees where the code is going
- **Automated code review** should combine fast rule-based checks (security, style) with slower LLM review (semantic issues)
- The **pitfall** of LLM code review is false positives — always include confidence scores and let developers override
- **Best practice**: use temperature 0.2-0.4 for code generation — 0 is deterministic but repetitive, higher values introduce errors"""
    ),
    (
        "ai-code-gen/code-embeddings-semantic-search",
        "Explain code embedding and semantic search techniques including code-specific embedding models, chunking strategies for source code, hybrid lexical and semantic search, cross-language code search, and building a codebase search engine with vector databases",
        r"""# Code Embeddings and Semantic Search

## Why Code Search Needs Specialized Approaches

Traditional text search (grep, ripgrep) finds exact or regex matches, but developers often search by **intent**: "function that validates email addresses" or "error handling for database connections." Semantic code search bridges this gap using **embedding models** trained on code. This matters **because** large codebases have thousands of files, and knowing what exists is half the battle of software development.

### Code-Specific Embedding Models

```python
import hashlib
import json
import math
import re
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path

# --- Code chunking strategies ---
# Best practice: chunk code at semantic boundaries (functions, classes)
# not at fixed character/line counts

@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    chunk_type: str  # "function", "class", "module_level", "import"
    name: str = ""
    language: str = "python"
    embedding: list[float] = field(default_factory=list)

    @property
    def id(self) -> str:
        raw = f"{self.file_path}:{self.start_line}-{self.end_line}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

class CodeChunker:
    # Chunk source code at semantic boundaries
    # Trade-off: smaller chunks = more precise retrieval but lose context
    # Larger chunks = more context but dilute the signal

    def __init__(self, max_chunk_lines: int = 50, overlap_lines: int = 5):
        self.max_chunk_lines = max_chunk_lines
        self.overlap_lines = overlap_lines

    def chunk_python(self, file_path: str, content: str) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        lines = content.splitlines()

        # First pass: identify top-level definitions
        boundaries: list[tuple[int, int, str, str]] = []  # (start, end, type, name)
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith(("def ", "async def ")):
                name = self._extract_name(stripped)
                end = self._find_block_end(lines, i)
                boundaries.append((i, end, "function", name))
                i = end + 1
            elif stripped.startswith("class "):
                name = self._extract_name(stripped)
                end = self._find_block_end(lines, i)
                boundaries.append((i, end, "class", name))
                i = end + 1
            else:
                i += 1

        # Create chunks from boundaries
        for start, end, chunk_type, name in boundaries:
            chunk_content = "\n".join(lines[start:end + 1])
            # However, large functions may exceed max chunk size
            if end - start > self.max_chunk_lines:
                # Split large blocks with overlap
                for sub_start in range(start, end, self.max_chunk_lines - self.overlap_lines):
                    sub_end = min(sub_start + self.max_chunk_lines, end)
                    chunks.append(CodeChunk(
                        file_path=file_path,
                        start_line=sub_start + 1,
                        end_line=sub_end + 1,
                        content="\n".join(lines[sub_start:sub_end + 1]),
                        chunk_type=chunk_type,
                        name=name,
                    ))
            else:
                chunks.append(CodeChunk(
                    file_path=file_path,
                    start_line=start + 1,
                    end_line=end + 1,
                    content=chunk_content,
                    chunk_type=chunk_type,
                    name=name,
                ))

        # Add module-level code (imports, constants)
        # Common mistake: skipping imports — they're crucial for understanding
        # what libraries/patterns a file uses
        module_lines: list[str] = []
        module_start = 0
        for start, _, _, _ in boundaries:
            if start > 0:
                module_chunk = "\n".join(lines[module_start:start]).strip()
                if module_chunk:
                    module_lines.append(module_chunk)
            module_start = boundaries[0][1] + 1 if boundaries else 0

        if module_lines:
            chunks.insert(0, CodeChunk(
                file_path=file_path,
                start_line=1,
                end_line=boundaries[0][0] if boundaries else len(lines),
                content="\n".join(module_lines),
                chunk_type="module_level",
                name=Path(file_path).stem,
            ))

        return chunks

    def _extract_name(self, line: str) -> str:
        match = re.match(r"(?:async\s+)?(?:def|class)\s+(\w+)", line.strip())
        return match.group(1) if match else "unknown"

    def _find_block_end(self, lines: list[str], start: int) -> int:
        if start >= len(lines):
            return start
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = start + 1
        while end < len(lines):
            line = lines[end]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            end += 1
        return end - 1

# --- Vector similarity search ---

class VectorIndex:
    # Simple in-memory vector index with cosine similarity
    # Pitfall: for >100k vectors, use HNSW (Faiss, Annoy, or Qdrant)

    def __init__(self):
        self.chunks: list[CodeChunk] = []

    def add(self, chunk: CodeChunk) -> None:
        self.chunks.append(chunk)

    def search(
        self, query_embedding: list[float], top_k: int = 10
    ) -> list[tuple[CodeChunk, float]]:
        results: list[tuple[CodeChunk, float]] = []
        for chunk in self.chunks:
            if not chunk.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, chunk.embedding)
            results.append((chunk, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
```

### Hybrid Search: Lexical + Semantic

**Therefore**, the best code search combines **lexical search** (BM25 for exact symbol names) with **semantic search** (embeddings for intent). Reciprocal Rank Fusion (RRF) merges results from both approaches.

```python
# --- Hybrid search with RRF fusion ---

class BM25Index:
    # Lexical search with BM25 scoring
    # Best practice: tokenize code differently than natural language
    # — split on camelCase, snake_case, dots, and colons

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[CodeChunk] = []
        self.doc_freqs: dict[str, int] = {}
        self.doc_lengths: list[int] = []
        self.avg_dl: float = 0.0
        self.inverted_index: dict[str, list[tuple[int, int]]] = {}  # term -> [(doc_idx, freq)]

    def add(self, chunk: CodeChunk) -> None:
        doc_idx = len(self.documents)
        self.documents.append(chunk)

        tokens = self._tokenize(chunk.content)
        self.doc_lengths.append(len(tokens))
        self.avg_dl = sum(self.doc_lengths) / len(self.doc_lengths)

        # Count term frequencies
        term_freqs: dict[str, int] = {}
        for token in tokens:
            term_freqs[token] = term_freqs.get(token, 0) + 1

        # Update inverted index
        for term, freq in term_freqs.items():
            if term not in self.inverted_index:
                self.inverted_index[term] = []
                self.doc_freqs[term] = 0
            self.inverted_index[term].append((doc_idx, freq))
            self.doc_freqs[term] += 1

    def search(self, query: str, top_k: int = 10) -> list[tuple[CodeChunk, float]]:
        query_tokens = self._tokenize(query)
        scores: dict[int, float] = {}
        n = len(self.documents)

        for token in query_tokens:
            if token not in self.inverted_index:
                continue
            df = self.doc_freqs[token]
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1)

            for doc_idx, tf in self.inverted_index[token]:
                dl = self.doc_lengths[doc_idx]
                tf_norm = (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
                )
                scores[doc_idx] = scores.get(doc_idx, 0) + idf * tf_norm

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.documents[idx], score) for idx, score in ranked]

    def _tokenize(self, text: str) -> list[str]:
        # Code-specific tokenization
        # Split camelCase: processData -> [process, data]
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        # Split snake_case: process_data -> [process, data]
        text = text.replace("_", " ").replace(".", " ").replace("::", " ")
        # Lowercase and split
        tokens = text.lower().split()
        # Remove very short tokens and common keywords
        stop_words = {"def", "class", "import", "from", "return", "self", "the", "a", "is"}
        return [t for t in tokens if len(t) > 1 and t not in stop_words]

class HybridCodeSearch:
    # Combine lexical and semantic search with RRF fusion
    # Trade-off: hybrid is slower but catches both exact matches
    # and semantic similarity — neither alone is sufficient

    def __init__(self, rrf_k: int = 60):
        self.vector_index = VectorIndex()
        self.bm25_index = BM25Index()
        self.rrf_k = rrf_k  # RRF constant (higher = more weight to lower ranks)

    def index(self, chunks: list[CodeChunk]) -> None:
        for chunk in chunks:
            self.vector_index.add(chunk)
            self.bm25_index.add(chunk)

    def search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        lexical_weight: float = 0.4,
        semantic_weight: float = 0.6,
    ) -> list[tuple[CodeChunk, float]]:
        # Get results from both indexes
        lexical_results = self.bm25_index.search(query, top_k=top_k * 2)
        semantic_results = self.vector_index.search(query_embedding, top_k=top_k * 2)

        # RRF fusion
        # Therefore, a result ranked #1 in both gets highest score
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, CodeChunk] = {}

        for rank, (chunk, _) in enumerate(lexical_results, 1):
            cid = chunk.id
            rrf_scores[cid] = rrf_scores.get(cid, 0) + lexical_weight / (self.rrf_k + rank)
            chunk_map[cid] = chunk

        for rank, (chunk, _) in enumerate(semantic_results, 1):
            cid = chunk.id
            rrf_scores[cid] = rrf_scores.get(cid, 0) + semantic_weight / (self.rrf_k + rank)
            chunk_map[cid] = chunk

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(chunk_map[cid], score) for cid, score in ranked]

# --- Demo ---

def demo_code_search():
    chunker = CodeChunker()
    search = HybridCodeSearch()

    # Index some sample code
    sample = '''
def validate_email(email: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def send_notification(user_id: int, message: str) -> None:
    # Send push notification to user
    pass

class UserRepository:
    def find_by_id(self, user_id: int):
        pass
    def find_by_email(self, email: str):
        pass
'''
    chunks = chunker.chunk_python("user_service.py", sample)
    search.index(chunks)

    # Lexical search works for exact names
    results = search.bm25_index.search("validate email", top_k=3)
    print("Lexical search for 'validate email':")
    for chunk, score in results:
        print(f"  {chunk.name} ({chunk.file_path}:{chunk.start_line}) score={score:.3f}")

    print(f"\nIndexed {len(chunks)} chunks from sample code")

demo_code_search()
```

## Summary and Key Takeaways

- **Semantic code search** finds code by intent ("email validation") not just keywords — essential for large codebases
- **Chunk at semantic boundaries** (functions, classes) not fixed sizes — a **common mistake** is using text splitters designed for prose
- **Code tokenization** must handle camelCase, snake_case, and language-specific delimiters — standard NLP tokenizers fail on code
- **Hybrid search** (BM25 + embeddings + RRF fusion) outperforms either approach alone — lexical catches exact names, semantic catches intent
- The **trade-off** of chunk size: smaller chunks are more precise but lose context; overlap helps but increases index size
- **Cross-language search** requires language-agnostic embedding models (CodeBERT, StarEncoder) trained on multiple programming languages
- The **pitfall** of pure semantic search is missing exact symbol names — always include lexical search for function/class name queries
- **Best practice**: include import statements in module-level chunks — they reveal which libraries and patterns a file uses"""
    ),
]
