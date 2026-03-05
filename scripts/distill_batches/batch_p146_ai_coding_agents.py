"""AI coding agents 2026 — agentic coding, AI code review, and reasoning models."""

PAIRS = [
    (
        "ai/agentic-coding-patterns",
        "Show agentic AI coding patterns: tool-use loops, code generation with verification, multi-step planning, and sandboxed execution.",
        '''Agentic AI coding patterns:

```python
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable
from pathlib import Path
import ast


# --- The Agentic Coding Loop ---
#
# 1. Understand task (plan)
# 2. Read relevant code (explore)
# 3. Write code changes (act)
# 4. Run tests / verify (verify)
# 5. If tests fail → analyze error → go to step 3
# 6. If tests pass → summarize changes (done)


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""


@dataclass
class AgentState:
    task: str
    plan: list[str] = field(default_factory=list)
    files_read: dict[str, str] = field(default_factory=dict)
    files_written: dict[str, str] = field(default_factory=dict)
    test_results: list[dict] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10


class CodingAgent:
    """AI coding agent with tool use and verification."""

    def __init__(self, llm_fn: Callable, workspace: Path):
        self.llm = llm_fn
        self.workspace = workspace
        self.tools = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "run_command": self.run_command,
            "search_code": self.search_code,
            "run_tests": self.run_tests,
            "lint_code": self.lint_code,
        }

    def read_file(self, path: str) -> ToolResult:
        """Read a file from the workspace."""
        full_path = self.workspace / path
        if not full_path.exists():
            return ToolResult(False, "", f"File not found: {path}")
        content = full_path.read_text()
        return ToolResult(True, content)

    def write_file(self, path: str, content: str) -> ToolResult:
        """Write content to a file."""
        full_path = self.workspace / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate Python syntax before writing
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                return ToolResult(
                    False, "", f"Syntax error: {e.msg} (line {e.lineno})"
                )

        full_path.write_text(content)
        return ToolResult(True, f"Wrote {len(content)} bytes to {path}")

    def run_command(self, command: str, timeout: int = 30) -> ToolResult:
        """Run a shell command in the workspace."""
        # Security: block dangerous commands
        blocked = ["rm -rf /", "sudo", "curl | sh", "wget | bash"]
        if any(b in command for b in blocked):
            return ToolResult(False, "", "Command blocked for safety")

        try:
            result = subprocess.run(
                command, shell=True, cwd=self.workspace,
                capture_output=True, text=True, timeout=timeout,
            )
            return ToolResult(
                result.returncode == 0,
                result.stdout,
                result.stderr,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out ({timeout}s)")

    def search_code(self, pattern: str, glob: str = "*.py") -> ToolResult:
        """Search for pattern in workspace files."""
        results = []
        for path in self.workspace.rglob(glob):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                content = path.read_text()
                for i, line in enumerate(content.splitlines(), 1):
                    if pattern.lower() in line.lower():
                        rel = path.relative_to(self.workspace)
                        results.append(f"{rel}:{i}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
        return ToolResult(True, "\n".join(results[:50]))

    def run_tests(self, test_path: str = "") -> ToolResult:
        """Run pytest and return results."""
        cmd = f"python -m pytest {test_path} -v --tb=short -q"
        return self.run_command(cmd, timeout=60)

    def lint_code(self, path: str) -> ToolResult:
        """Run ruff linter on file."""
        return self.run_command(f"ruff check {path}")

    def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return ToolResult(False, "", f"Unknown tool: {tool_name}")
        return self.tools[tool_name](**kwargs)

    async def solve(self, task: str) -> dict:
        """Main agent loop: plan → act → verify → iterate."""
        state = AgentState(task=task)

        # Step 1: Plan
        plan_prompt = f"""Task: {task}

Available tools: {list(self.tools.keys())}

Create a step-by-step plan to complete this task.
Start by reading relevant files to understand the codebase."""

        plan_response = await self.llm(plan_prompt)
        state.plan = parse_plan(plan_response)

        # Step 2: Execute plan with tool-use loop
        messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": plan_prompt})

        while state.iteration < state.max_iterations:
            state.iteration += 1

            # Get next action from LLM
            response = await self.llm(messages)

            # Parse tool calls from response
            tool_calls = parse_tool_calls(response)

            if not tool_calls:
                # No more tool calls — agent is done
                break

            # Execute each tool call
            for call in tool_calls:
                result = self.execute_tool(call["name"], **call["args"])
                messages.append({
                    "role": "tool",
                    "name": call["name"],
                    "content": result.output if result.success else result.error,
                })

                # Track state
                if call["name"] == "read_file":
                    state.files_read[call["args"]["path"]] = result.output
                elif call["name"] == "write_file":
                    state.files_written[call["args"]["path"]] = call["args"]["content"]
                elif call["name"] == "run_tests":
                    state.test_results.append({
                        "iteration": state.iteration,
                        "passed": result.success,
                        "output": result.output,
                    })

            # If tests passed, we might be done
            if state.test_results and state.test_results[-1]["passed"]:
                # Verify with lint
                for path in state.files_written:
                    lint_result = self.lint_code(path)
                    if not lint_result.success:
                        messages.append({
                            "role": "user",
                            "content": f"Lint errors in {path}: {lint_result.error}. Fix them.",
                        })
                        continue

                break  # All good!

        return {
            "task": task,
            "iterations": state.iteration,
            "files_changed": list(state.files_written.keys()),
            "tests_passed": (
                state.test_results[-1]["passed"]
                if state.test_results else False
            ),
        }


AGENT_SYSTEM_PROMPT = """You are a coding agent. You solve programming tasks
by reading code, writing changes, and running tests.

Rules:
1. Always read relevant files before making changes
2. Make minimal, focused changes
3. Run tests after every change
4. If tests fail, analyze the error and fix it
5. Never modify test files unless explicitly asked

Respond with tool calls in JSON format:
{"tool": "read_file", "args": {"path": "src/utils.py"}}
"""
```

Agentic coding patterns:
1. **Plan → Act → Verify loop** — understand task, make changes, run tests, iterate on failures
2. **Sandboxed execution** — `subprocess.run` with timeout and command blocking
3. **AST validation** — parse Python before writing to catch syntax errors immediately
4. **State tracking** — record files read/written and test results per iteration
5. **Max iterations** — hard cap prevents infinite loops on unsolvable problems'''
    ),
    (
        "ai/ai-code-review",
        "Show AI-powered code review patterns: PR analysis, security scanning, style enforcement, and actionable feedback.",
        '''AI-powered code review patterns:

```python
import subprocess
from dataclasses import dataclass
from typing import Callable
from pathlib import Path
import json
import re


@dataclass
class ReviewComment:
    file: str
    line: int
    severity: str  # "critical" | "warning" | "suggestion" | "praise"
    category: str  # "security" | "performance" | "style" | "logic" | "testing"
    message: str
    suggestion: str = ""  # Suggested fix


class AICodeReviewer:
    """Automated code review using LLM analysis."""

    def __init__(self, llm_fn: Callable):
        self.llm = llm_fn

    async def review_pr(self, diff: str, context: dict = None) -> list[ReviewComment]:
        """Review a pull request diff."""
        comments = []

        # Parse diff into per-file changes
        file_diffs = self.parse_diff(diff)

        for file_path, changes in file_diffs.items():
            # Skip non-code files
            if not file_path.endswith((".py", ".ts", ".js", ".tsx", ".jsx")):
                continue

            # Run targeted analysis passes
            file_comments = await self.analyze_file(file_path, changes, context)
            comments.extend(file_comments)

        # Deduplicate and prioritize
        comments = self.deduplicate(comments)
        comments.sort(key=lambda c: {
            "critical": 0, "warning": 1, "suggestion": 2, "praise": 3,
        }.get(c.severity, 4))

        return comments

    async def analyze_file(
        self, file_path: str, changes: str, context: dict,
    ) -> list[ReviewComment]:
        """Multi-pass analysis of a single file's changes."""
        comments = []

        # Pass 1: Security review
        security_prompt = f"""Review this code diff for security issues.
Look for: SQL injection, XSS, command injection, path traversal,
hardcoded secrets, insecure deserialization, SSRF, auth bypass.

File: {file_path}
Diff:
{changes}

Return JSON array of issues found. Each issue:
{{"line": int, "severity": "critical"|"warning", "message": str, "suggestion": str}}
Return empty array [] if no issues."""

        security_response = await self.llm(security_prompt)
        for issue in parse_json_array(security_response):
            comments.append(ReviewComment(
                file=file_path,
                line=issue.get("line", 0),
                severity=issue.get("severity", "warning"),
                category="security",
                message=issue["message"],
                suggestion=issue.get("suggestion", ""),
            ))

        # Pass 2: Logic and correctness
        logic_prompt = f"""Review this code diff for logic errors and bugs.
Look for: off-by-one errors, null/None handling, race conditions,
resource leaks, error handling gaps, edge cases.

File: {file_path}
Diff:
{changes}

Return JSON array. Each issue:
{{"line": int, "severity": "critical"|"warning", "message": str, "suggestion": str}}"""

        logic_response = await self.llm(logic_prompt)
        for issue in parse_json_array(logic_response):
            comments.append(ReviewComment(
                file=file_path,
                line=issue.get("line", 0),
                severity=issue.get("severity", "warning"),
                category="logic",
                message=issue["message"],
                suggestion=issue.get("suggestion", ""),
            ))

        # Pass 3: Performance
        perf_prompt = f"""Review for performance issues.
Look for: N+1 queries, unnecessary copies, missing indexes,
unbounded loops, synchronous I/O in async context.

File: {file_path}
Diff:
{changes}

Return JSON array of issues."""

        perf_response = await self.llm(perf_prompt)
        for issue in parse_json_array(perf_response):
            comments.append(ReviewComment(
                file=file_path,
                line=issue.get("line", 0),
                severity="suggestion",
                category="performance",
                message=issue["message"],
                suggestion=issue.get("suggestion", ""),
            ))

        return comments

    def parse_diff(self, diff: str) -> dict[str, str]:
        """Parse unified diff into per-file changes."""
        files = {}
        current_file = None
        current_diff = []

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                if current_file:
                    files[current_file] = "\n".join(current_diff)
                match = re.search(r"b/(.+)$", line)
                current_file = match.group(1) if match else None
                current_diff = []
            elif current_file:
                current_diff.append(line)

        if current_file:
            files[current_file] = "\n".join(current_diff)

        return files

    def deduplicate(self, comments: list[ReviewComment]) -> list[ReviewComment]:
        """Remove duplicate comments on the same line."""
        seen = set()
        unique = []
        for c in comments:
            key = (c.file, c.line, c.category)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def format_github_review(self, comments: list[ReviewComment]) -> str:
        """Format as GitHub PR review body."""
        if not comments:
            return "LGTM! No issues found."

        critical = [c for c in comments if c.severity == "critical"]
        warnings = [c for c in comments if c.severity == "warning"]
        suggestions = [c for c in comments if c.severity == "suggestion"]

        body = "## AI Code Review\n\n"

        if critical:
            body += f"### Critical Issues ({len(critical)})\n"
            for c in critical:
                body += f"- **{c.file}:{c.line}** [{c.category}] {c.message}\n"
                if c.suggestion:
                    body += f"  > Suggestion: {c.suggestion}\n"

        if warnings:
            body += f"\n### Warnings ({len(warnings)})\n"
            for c in warnings:
                body += f"- **{c.file}:{c.line}** [{c.category}] {c.message}\n"

        if suggestions:
            body += f"\n### Suggestions ({len(suggestions)})\n"
            for c in suggestions:
                body += f"- **{c.file}:{c.line}** {c.message}\n"

        verdict = "REQUEST_CHANGES" if critical else "COMMENT"
        body += f"\n---\nVerdict: **{verdict}**"

        return body


def parse_json_array(text: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    try:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except json.JSONDecodeError:
        pass
    return []
```

AI code review patterns:
1. **Multi-pass analysis** — separate security, logic, and performance passes for focused review
2. **Severity levels** — critical (must fix), warning (should fix), suggestion (could improve)
3. **Actionable suggestions** — each comment includes a concrete fix, not just the problem
4. **Diff-aware** — review only changed lines, not entire files
5. **GitHub integration** — format as PR review with REQUEST_CHANGES or COMMENT verdict'''
    ),
    (
        "ai/reasoning-models-extended-thinking",
        "Show reasoning model patterns: extended thinking, chain-of-thought steering, thinking budgets, and when to use reasoning vs standard models.",
        '''Reasoning model patterns:

```python
import anthropic
from openai import OpenAI
from typing import Literal


# --- When to Use Reasoning Models ---
#
# USE reasoning models (Claude thinking, o1/o3) for:
#   - Multi-step math and logic
#   - Complex code generation (algorithms, system design)
#   - Tasks requiring planning and backtracking
#   - Ambiguous instructions needing interpretation
#   - Analysis with many constraints
#
# DON'T USE for:
#   - Simple Q&A, summarization, translation
#   - Code formatting, refactoring, typo fixes
#   - Tasks where speed matters more than accuracy
#   - High-volume batch processing


# --- Claude Extended Thinking ---

client = anthropic.Anthropic()

def solve_with_thinking(
    prompt: str,
    budget_tokens: int = 10000,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Use Claude's extended thinking for complex problems."""
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": budget_tokens,  # How much thinking to allow
        },
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse thinking and response
    thinking_text = ""
    answer_text = ""
    for block in response.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            answer_text = block.text

    return {
        "thinking": thinking_text,
        "answer": answer_text,
        "thinking_tokens": response.usage.thinking_tokens,
        "output_tokens": response.usage.output_tokens,
    }


# --- Adaptive thinking budget ---

def adaptive_thinking(prompt: str, difficulty: str = "auto") -> dict:
    """Adjust thinking budget based on task difficulty."""

    if difficulty == "auto":
        difficulty = classify_difficulty(prompt)

    budgets = {
        "easy": 1024,       # Quick reasoning
        "medium": 5000,     # Moderate planning
        "hard": 16000,      # Deep analysis
        "very_hard": 32000, # Maximum reasoning
    }

    budget = budgets.get(difficulty, 5000)
    return solve_with_thinking(prompt, budget_tokens=budget)


def classify_difficulty(prompt: str) -> str:
    """Estimate problem difficulty for budget allocation."""
    indicators = {
        "hard": [
            "algorithm", "optimize", "prove", "design a system",
            "concurrent", "distributed", "NP-hard",
        ],
        "medium": [
            "implement", "refactor", "explain why", "compare",
            "debug", "analyze",
        ],
        "easy": [
            "what is", "how to", "convert", "format",
            "simple", "basic",
        ],
    }

    prompt_lower = prompt.lower()
    for level in ["hard", "medium", "easy"]:
        if any(kw in prompt_lower for kw in indicators[level]):
            return level

    return "medium"


# --- Structured reasoning with tools ---

def solve_with_tools(
    prompt: str,
    tools: list[dict],
) -> dict:
    """Reasoning model + tool use for verified answers."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        thinking={"type": "enabled", "budget_tokens": 10000},
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    # The model thinks through the problem, then decides
    # which tools to call and in what order.
    # Thinking happens BEFORE tool calls, so the model
    # plans its approach first.

    return response


# --- OpenAI o1/o3 reasoning ---

openai_client = OpenAI()

def solve_with_o1(
    prompt: str,
    reasoning_effort: Literal["low", "medium", "high"] = "medium",
) -> dict:
    """Use OpenAI reasoning models."""

    response = openai_client.chat.completions.create(
        model="o3-mini",
        reasoning_effort=reasoning_effort,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "answer": response.choices[0].message.content,
        "reasoning_tokens": response.usage.completion_tokens_details.reasoning_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


# --- Routing: reasoning vs standard model ---

async def smart_route(
    prompt: str,
    standard_fn,
    reasoning_fn,
    threshold: float = 0.6,
) -> dict:
    """Route to reasoning or standard model based on complexity."""

    complexity = estimate_complexity(prompt)

    if complexity > threshold:
        # Complex: use reasoning model
        result = await reasoning_fn(prompt)
        result["model_type"] = "reasoning"
        result["complexity"] = complexity
    else:
        # Simple: use standard model (faster, cheaper)
        result = await standard_fn(prompt)
        result["model_type"] = "standard"
        result["complexity"] = complexity

    return result


def estimate_complexity(prompt: str) -> float:
    """Estimate prompt complexity (0-1)."""
    score = 0.0

    # Length-based (longer prompts tend to be more complex)
    if len(prompt) > 500:
        score += 0.2

    # Multi-step indicators
    step_words = ["then", "after that", "next", "finally", "step"]
    score += min(0.3, sum(0.1 for w in step_words if w in prompt.lower()))

    # Technical complexity
    complex_terms = [
        "algorithm", "optimize", "concurrent", "distributed",
        "prove", "derive", "analyze complexity", "tradeoff",
    ]
    score += min(0.3, sum(0.1 for t in complex_terms if t in prompt.lower()))

    # Question complexity
    if prompt.count("?") > 2:
        score += 0.1
    if "why" in prompt.lower() or "how" in prompt.lower():
        score += 0.1

    return min(score, 1.0)
```

Reasoning model patterns:
1. **Extended thinking** — `thinking.budget_tokens` controls how much reasoning the model does
2. **Adaptive budgets** — allocate more thinking tokens to harder problems
3. **Complexity routing** — send easy tasks to standard models, hard tasks to reasoning models
4. **Think-then-act** — reasoning happens before tool calls, enabling planned tool use
5. **Cost efficiency** — reasoning tokens cost more; reserve them for problems that need depth'''
    ),
]
