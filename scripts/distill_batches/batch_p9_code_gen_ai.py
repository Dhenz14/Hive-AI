"""p9 code gen ai"""

PAIRS = [
    (
        "ai-code-gen/ast-manipulation-code-transformation",
        "Explain AST-based code analysis and transformation including parsing source code into abstract syntax trees, visitor pattern traversal, automated refactoring operations, code generation from ASTs, and building custom linting rules with practical Python ast module examples",
        '''Abstract Syntax Trees are the foundation of every code intelligence tool -- linters, formatters, refactoring tools, and AI code generators all work with ASTs rather than raw text. This is critical **because** string manipulation is fragile (regex can't parse nested structures), while ASTs provide a structured, semantically meaningful representation of code. **Therefore**, understanding AST manipulation is essential for building reliable code tools.

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

        self.results.append({'''
    ),
    (
        "is_complex",
        "}) self.generic_visit(node)",
        '''visit_AsyncFunctionDef = visit_FunctionDef

class TypeAnnotationChecker(ast.NodeVisitor):
    # Check for missing type annotations
    # Common mistake: only checking function return types,
    # not parameter annotations

    def __init__(self):
        self.issues: list[dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Skip __init__ return type (always None)
        if node.name != "__init__" and node.returns is None:
            self.issues.append({'''
    ),
    (
        "line",
        "}) self.generic_visit(node) visit_AsyncFunctionDef = visit_FunctionDef def analyze_code(source: str) -> dict: tree = ast.parse(source)",
        '''complexity = ComplexityAnalyzer()
    complexity.visit(tree)

    types = TypeAnnotationChecker()
    types.visit(tree)

    return {'''
    ),
    (
        "complex_functions",
        "}",
        '''sample_code = textwrap.dedent("""
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
""")

report = analyze_code(sample_code)
for f in report["functions"]:
    print(f"  {f['name']}: complexity={f['complexity']}, complex={f['is_complex']}")
for issue in report["type_issues"]:
    print(f"  {issue['type']}: {issue.get('function', '')} {issue.get('param', '')}")
```

### AST Transformation: Automated Refactoring

**However**, AST analysis is only half the story. The real power comes from **transforming** ASTs -- rewriting code programmatically. The **trade-off** is that AST transformation loses formatting and comments (Python's ast module doesn't preserve them), so production tools use CST (Concrete Syntax Tree) libraries like `libcst` instead.

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
                    kw.arg == "file" for kw in node.value.keywords'''
    ),
    (
        "ai-code-gen/llm-code-generation-patterns",
        "Explain LLM-based code generation patterns including fill-in-the-middle completion, repository-level context gathering, test-driven generation, iterative refinement with compiler feedback, and code review automation with practical implementation examples",
        '''Modern code AI goes far beyond autocomplete. **Because** real software development involves understanding project structure, API contracts, test patterns, and coding conventions, effective code generation requires **repository-level context**. The challenge is fitting relevant context into the LLM's limited context window while maximizing signal-to-noise ratio.

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
            suffix=target_content[cursor_pos:],'''
    ),
    (
        "quote_style",
        "} def _find_test_file(self, source_file: str) -> Optional[str]: name = os.path.basename(source_file) test_name = f'test_{name}",
        '''for test_dir in ["tests", "test", "."]:
            test_path = os.path.join(
                os.path.dirname(source_file), test_dir, test_name'''
    ),
    (
        "code",
        "}) continue",
        '''test_result = self._run_tests(generated_code, test_code)

            result = GenerationResult(
                code=generated_code,
                passed=test_result["all_passed"],
                errors=test_result.get("failures", []),
                iterations=iteration + 1,
                tests_passed=test_result["passed"],
                tests_total=test_result["total"],'''
    ),
    (
        "code",
        "}) return best_result def _build_prompt(self, task: str, context: CodeContext, iteration: int) -> str: parts = [f'Task: {task}\n']",
        '''if context.related_files:
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
        # Placeholder -- in production, call Claude/GPT API
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
            (r"eval\(", "Avoid eval() -- use ast.literal_eval() for safe parsing"),
            (r"subprocess\..*shell=True", "Avoid shell=True -- use list args to prevent injection"),
            (r"password.*=.*['\"]", "Hardcoded password detected -- use environment variables"),
            (r"\.execute\(.*%s", "SQL injection risk -- use parameterized queries"),
            (r"pickle\.load", "Pickle deserialization is unsafe -- use JSON for untrusted data"),
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
                        category="style", message="TODO/FIXME found -- track in issue tracker",
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

- **Repository-level context** is essential for good code generation -- gather imports, related files, tests, and conventions
- **Extract signatures only** from related files to maximize context window utilization -- a **common mistake** is including full file contents
- **Iterative generation** (generate -> compile -> test -> fix) dramatically improves accuracy -- the LLM excels at fixing specific errors
- The **trade-off** of iteration count: more iterations = better results but higher latency and cost
- **Fill-in-the-middle** (prefix + suffix) gives better completions than prefix-only, because the model sees where the code is going
- **Automated code review** should combine fast rule-based checks (security, style) with slower LLM review (semantic issues)
- The **pitfall** of LLM code review is false positives -- always include confidence scores and let developers override
- **Best practice**: use temperature 0.2-0.4 for code generation -- 0 is deterministic but repetitive, higher values introduce errors'''
    ),
    (
        "ai-code-gen/code-embeddings-semantic-search",
        "Explain code embedding and semantic search techniques including code-specific embedding models, chunking strategies for source code, hybrid lexical and semantic search, cross-language code search, and building a codebase search engine with vector databases",
        '''Traditional text search (grep, ripgrep) finds exact or regex matches, but developers often search by **intent**: "function that validates email addresses" or "error handling for database connections." Semantic code search bridges this gap using **embedding models** trained on code. This matters **because** large codebases have thousands of files, and knowing what exists is half the battle of software development.

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
        # Common mistake: skipping imports -- they're crucial for understanding
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
    # -- split on camelCase, snake_case, dots, and colons

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
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)'''
    ),
]
