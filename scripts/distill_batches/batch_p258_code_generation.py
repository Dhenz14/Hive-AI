"""AI code generation — code completion, infilling, code review, and code search."""

PAIRS = [
    (
        "ai/code-completion",
        "Show code completion patterns: FIM (Fill-in-the-Middle), prefix-suffix-middle format, and completion filtering/ranking.",
        '''Code completion with Fill-in-the-Middle:

```python
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class CompletionRequest:
    prefix: str      # Code before cursor
    suffix: str      # Code after cursor
    language: str
    max_tokens: int = 256
    temperature: float = 0.2
    stop_sequences: list[str] = None


@dataclass
class Completion:
    text: str
    score: float
    tokens_used: int


class FIMFormatter:
    """Format code for Fill-in-the-Middle (FIM) completion.

    FIM allows the model to see both code before AND after the cursor,
    producing much better completions than prefix-only.
    """

    # Token formats vary by model
    FORMATS = {
        "starcoder": {
            "prefix": "<fim_prefix>",
            "suffix": "<fim_suffix>",
            "middle": "<fim_middle>",
        },
        "codellama": {
            "prefix": "<PRE>",
            "suffix": " <SUF>",
            "middle": " <MID>",
        },
        "deepseek": {
            "prefix": "<|fim▁begin|>",
            "suffix": "<|fim▁hole|>",
            "middle": "<|fim▁end|>",
        },
    }

    def __init__(self, model_family: str = "starcoder"):
        self.tokens = self.FORMATS[model_family]

    def format_psm(self, prefix: str, suffix: str) -> str:
        """Prefix-Suffix-Middle format (most common)."""
        return (
            f"{self.tokens['prefix']}{prefix}"
            f"{self.tokens['suffix']}{suffix}"
            f"{self.tokens['middle']}"
        )

    def format_spm(self, prefix: str, suffix: str) -> str:
        """Suffix-Prefix-Middle format (alternative)."""
        return (
            f"{self.tokens['suffix']}{suffix}"
            f"{self.tokens['prefix']}{prefix}"
            f"{self.tokens['middle']}"
        )


class CompletionFilter:
    """Filter and rank code completions."""

    def __init__(self, language: str = "python"):
        self.language = language

    def filter_completion(self, completion: str, prefix: str, suffix: str) -> str:
        """Clean up raw completion text."""
        # Remove trailing whitespace
        completion = completion.rstrip()

        # Stop at natural boundaries
        stop_patterns = {
            "python": [r"\nclass ", r"\ndef ", r"\n\n\n"],
            "javascript": [r"\nfunction ", r"\nclass ", r"\nexport "],
            "typescript": [r"\ninterface ", r"\ntype ", r"\nfunction "],
        }

        for pattern in stop_patterns.get(self.language, []):
            match = re.search(pattern, completion)
            if match:
                completion = completion[:match.start()]

        # Ensure indentation matches context
        prefix_lines = prefix.split("\\n")
        if prefix_lines:
            current_indent = len(prefix_lines[-1]) - len(prefix_lines[-1].lstrip())
            completion_lines = completion.split("\\n")
            if completion_lines and not completion_lines[0].strip():
                # Remove leading blank line
                completion_lines = completion_lines[1:]

        return completion

    def rank_completions(self, completions: list[Completion],
                          prefix: str, suffix: str) -> list[Completion]:
        """Rank completions by quality signals."""
        scored = []
        for comp in completions:
            score = comp.score

            # Bonus for matching expected patterns
            if suffix.lstrip().startswith(")") and comp.text.count("(") <= comp.text.count(")"):
                score += 0.1  # Bracket matching

            # Penalty for very short or very long
            if len(comp.text.strip()) < 5:
                score -= 0.2
            if comp.tokens_used > 200:
                score -= 0.1

            # Bonus for syntactic correctness
            try:
                compile(prefix + comp.text + suffix, "<test>", "exec")
                score += 0.2  # Valid Python
            except SyntaxError:
                score -= 0.1

            scored.append(Completion(comp.text, score, comp.tokens_used))

        return sorted(scored, key=lambda c: c.score, reverse=True)
```

Key patterns:
1. **Fill-in-the-Middle** — model sees prefix AND suffix; much better than prefix-only completion
2. **PSM vs SPM** — Prefix-Suffix-Middle is standard; SPM works better for some models
3. **Stop sequences** — halt generation at natural code boundaries (new function, class, etc.)
4. **Syntax validation** — try compiling the completed code; rank valid completions higher
5. **Temperature** — low temperature (0.1-0.3) for completion; high (0.7+) for generation'''
    ),
    (
        "ai/code-review-ai",
        "Show AI-powered code review: diff analysis, bug detection, security scanning, and review comment generation.",
        '''AI-powered code review:

```python
from dataclasses import dataclass, field
from anthropic import Anthropic
import json


@dataclass
class ReviewComment:
    file: str
    line: int
    severity: str  # info, warning, error, critical
    category: str  # bug, security, performance, style, logic
    message: str
    suggestion: str = ""


@dataclass
class ReviewResult:
    comments: list[ReviewComment] = field(default_factory=list)
    summary: str = ""
    approval: str = "pending"  # approve, request_changes, comment


class AICodeReviewer:
    """Automated code review using LLMs."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def review_diff(self, diff: str, context: str = "") -> ReviewResult:
        """Review a git diff for issues."""
        system_prompt = """You are an expert code reviewer. Analyze the diff for:
1. Bugs and logic errors
2. Security vulnerabilities (injection, auth bypass, data exposure)
3. Performance issues (N+1 queries, unnecessary allocations, blocking calls)
4. Error handling gaps
5. Code clarity issues

For each issue found, provide:
- file path and line number
- severity (info/warning/error/critical)
- category (bug/security/performance/style/logic)
- clear description
- suggested fix

Output as JSON: {"comments": [...], "summary": "...", "approval": "approve|request_changes|comment"}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Review this diff:\\n\\n{diff}\\n\\n{'Context: ' + context if context else ''}",
            }],
        )

        try:
            data = json.loads(response.content[0].text)
            comments = [ReviewComment(**c) for c in data.get("comments", [])]
            return ReviewResult(
                comments=comments,
                summary=data.get("summary", ""),
                approval=data.get("approval", "comment"),
            )
        except (json.JSONDecodeError, TypeError):
            return ReviewResult(summary=response.content[0].text)

    def review_security(self, code: str, language: str) -> list[ReviewComment]:
        """Focused security review."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=f"You are a security expert reviewing {language} code. Find ALL security vulnerabilities. Output as JSON array of {{file, line, severity, category, message, suggestion}}.",
            messages=[{"role": "user", "content": code}],
        )

        try:
            data = json.loads(response.content[0].text)
            return [ReviewComment(**c) for c in data]
        except (json.JSONDecodeError, TypeError):
            return []

    def suggest_tests(self, code: str, language: str) -> str:
        """Suggest test cases for code."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"Write comprehensive test cases for this {language} code. Include edge cases, error cases, and boundary conditions.\\n\\n```{language}\\n{code}\\n```",
            }],
        )
        return response.content[0].text
```

Key patterns:
1. **Diff-focused review** — analyze only changed lines; reduces noise and cost
2. **Structured output** — JSON comments with file, line, severity, category; machine-parseable
3. **Specialized reviews** — separate security, performance, style reviews for depth
4. **Severity levels** — critical (security breach) > error (bug) > warning > info (style)
5. **Suggestion included** — every comment includes a fix suggestion; actionable feedback'''
    ),
    (
        "ai/code-search-semantic",
        "Show semantic code search: embedding code snippets, natural language queries to code, and code similarity detection.",
        '''Semantic code search with embeddings:

```python
import ast
import os
import numpy as np
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    type: str  # function, class, module
    name: str
    docstring: str = ""
    embedding: np.ndarray = None


class CodeParser:
    """Parse Python files into searchable chunks."""

    def parse_file(self, file_path: str) -> list[CodeChunk]:
        """Extract functions, classes, and their docstrings."""
        with open(file_path) as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return [CodeChunk(file_path, 1, source.count("\\n") + 1,
                            source, "module", Path(file_path).stem)]

        chunks = []
        lines = source.split("\\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_chunk(node, lines, file_path, "function")
                chunks.append(chunk)
            elif isinstance(node, ast.ClassDef):
                chunk = self._extract_chunk(node, lines, file_path, "class")
                chunks.append(chunk)

        if not chunks:
            chunks.append(CodeChunk(file_path, 1, len(lines),
                                   source, "module", Path(file_path).stem))

        return chunks

    def _extract_chunk(self, node, lines, file_path, node_type):
        start = node.lineno
        end = node.end_lineno or start
        content = "\\n".join(lines[start-1:end])
        docstring = ast.get_docstring(node) or ""

        return CodeChunk(
            file_path=file_path,
            start_line=start,
            end_line=end,
            content=content,
            type=node_type,
            name=node.name,
            docstring=docstring,
        )


class SemanticCodeSearch:
    """Search code using natural language queries."""

    def __init__(self, embed_fn):
        self.embed_fn = embed_fn
        self.chunks: list[CodeChunk] = []

    def index_directory(self, directory: str, extensions: list[str] = None):
        """Index all code files in a directory."""
        extensions = extensions or [".py"]
        parser = CodeParser()

        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.endswith(ext) for ext in extensions):
                    path = os.path.join(root, file)
                    chunks = parser.parse_file(path)
                    self.chunks.extend(chunks)

        # Compute embeddings
        texts = [self._chunk_to_text(c) for c in self.chunks]
        embeddings = self.embed_fn(texts)
        for chunk, emb in zip(self.chunks, embeddings):
            chunk.embedding = emb

    def _chunk_to_text(self, chunk: CodeChunk) -> str:
        """Convert code chunk to text for embedding."""
        parts = [f"{chunk.type}: {chunk.name}"]
        if chunk.docstring:
            parts.append(f"Description: {chunk.docstring}")
        parts.append(f"Code:\\n{chunk.content[:500]}")
        return "\\n".join(parts)

    def search(self, query: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Search code with natural language query."""
        query_emb = self.embed_fn([query])[0]

        scores = []
        for chunk in self.chunks:
            if chunk.embedding is not None:
                sim = np.dot(query_emb, chunk.embedding) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(chunk.embedding) + 1e-8
                )
                scores.append((chunk, float(sim)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def find_similar(self, code: str, top_k: int = 5) -> list[tuple[CodeChunk, float]]:
        """Find code similar to a given snippet."""
        code_emb = self.embed_fn([code])[0]
        scores = []
        for chunk in self.chunks:
            if chunk.embedding is not None:
                sim = np.dot(code_emb, chunk.embedding) / (
                    np.linalg.norm(code_emb) * np.linalg.norm(chunk.embedding) + 1e-8
                )
                scores.append((chunk, float(sim)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
```

Key patterns:
1. **AST parsing** — extract functions and classes with their docstrings; structured chunks
2. **Code-to-text** — combine name, docstring, and code for embedding; bridges NL-code gap
3. **Semantic search** — natural language queries find relevant code by meaning, not keywords
4. **Code similarity** — find duplicate or similar code patterns across codebase
5. **Embedding index** — precompute and store embeddings; fast retrieval at query time'''
    ),
]
