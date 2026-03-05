"""Structured outputs and tool use — LLM function calling, JSON mode, and constrained generation."""

PAIRS = [
    (
        "ai/structured-outputs",
        "Show structured output patterns for LLMs: JSON mode, Pydantic schema enforcement, constrained generation, and reliable extraction.",
        '''Structured outputs from LLMs — reliable JSON and typed responses:

```python
from pydantic import BaseModel, Field
from openai import OpenAI
from anthropic import Anthropic
import json
from enum import Enum
from typing import Literal


# === Pydantic schema for structured extraction ===

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CodeIssue(BaseModel):
    """A single issue found during code review."""
    file: str = Field(description="File path where issue was found")
    line: int = Field(description="Line number")
    severity: Severity
    category: Literal["bug", "security", "performance", "style", "logic"]
    description: str = Field(description="What the issue is", max_length=200)
    fix: str = Field(description="Suggested fix as code snippet")


class CodeReview(BaseModel):
    """Structured code review result."""
    summary: str = Field(description="One-sentence summary of the review")
    issues: list[CodeIssue] = Field(default_factory=list)
    approval: Literal["approve", "request_changes", "needs_discussion"]
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the review")


# === OpenAI Structured Outputs (response_format) ===

def review_code_openai(code: str, filename: str) -> CodeReview:
    """Extract structured code review using OpenAI's JSON schema mode."""
    client = OpenAI()

    response = client.responses.create(
        model="gpt-4.1",
        input=[
            {"role": "system", "content": "You are a senior code reviewer. Analyze the code and provide structured feedback."},
            {"role": "user", "content": f"Review this code from {filename}:\\n\\n```\\n{code}\\n```"},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "code_review",
                "schema": CodeReview.model_json_schema(),
                "strict": True,  # Guarantees valid JSON matching schema
            }
        },
    )

    # Parse guaranteed-valid JSON into Pydantic model
    return CodeReview.model_validate_json(response.output_text)


# === Anthropic tool_use for structured extraction ===

def review_code_anthropic(code: str, filename: str) -> CodeReview:
    """Use Anthropic's tool_use to extract structured data."""
    client = Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[{
            "name": "submit_review",
            "description": "Submit structured code review results",
            "input_schema": CodeReview.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": "submit_review"},
        messages=[{
            "role": "user",
            "content": f"Review this code from {filename}:\\n\\n```\\n{code}\\n```",
        }],
    )

    # Extract tool call result
    for block in response.content:
        if block.type == "tool_use":
            return CodeReview.model_validate(block.input)

    raise ValueError("No tool use in response")


# === Constrained generation with outlines ===

def review_code_local(code: str, filename: str) -> CodeReview:
    """Use outlines for guaranteed schema-conforming generation from local models."""
    import outlines
    from outlines import models, generate

    model = models.transformers("Qwen/Qwen3.5-9B")

    # Constrained generation: token-level enforcement of JSON schema
    generator = generate.json(model, CodeReview)

    prompt = f"""Review this code from {filename} and provide structured feedback.

```
{code}
```

Output your review as JSON:"""

    review = generator(prompt)  # Always valid CodeReview
    return review


# === Retry with validation ===

def extract_with_retry(
    prompt: str,
    schema: type[BaseModel],
    max_retries: int = 3,
    model: str = "gpt-4.1-mini",
) -> BaseModel:
    """Extract structured data with validation and retry."""
    client = OpenAI()
    errors = []

    for attempt in range(max_retries):
        messages = [{"role": "user", "content": prompt}]

        # On retry, include previous errors for self-correction
        if errors:
            error_context = "\\n".join(f"Attempt {i+1} error: {e}" for i, e in enumerate(errors))
            messages.append({
                "role": "user",
                "content": f"Previous attempts failed:\\n{error_context}\\nPlease fix and try again.",
            })

        try:
            response = client.responses.create(
                model=model,
                input=messages,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "extraction",
                        "schema": schema.model_json_schema(),
                        "strict": True,
                    }
                },
            )
            return schema.model_validate_json(response.output_text)

        except Exception as e:
            errors.append(str(e))

    raise ValueError(f"Failed after {max_retries} attempts: {errors}")


# === Streaming structured output ===

async def stream_structured(prompt: str) -> dict:
    """Stream JSON output with incremental parsing."""
    from openai import AsyncOpenAI
    import partial_json_parser

    client = AsyncOpenAI()
    buffer = ""

    stream = await client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
        stream=True,
    )

    async for event in stream:
        if hasattr(event, "delta") and event.delta:
            buffer += event.delta
            # Parse partial JSON as it streams in
            try:
                partial = partial_json_parser.loads(buffer)
                yield partial  # Emit partial result for progressive UI
            except Exception:
                pass  # Incomplete JSON, wait for more tokens

    return json.loads(buffer)
```

Structured output comparison:

| Method | Guarantee | Latency | Local models |
|--------|-----------|---------|-------------|
| **JSON schema mode** | 100% valid | Normal | No (API only) |
| **tool_use** | 100% valid | Normal | Some |
| **JSON mode** | Valid JSON, no schema | Normal | Some |
| **outlines** | 100% valid | +10-20% | Yes |
| **Prompt + parse** | ~90% valid | Normal | Yes |

Key patterns:
1. **Schema as Pydantic model** — define output structure with types, constraints, and descriptions; auto-generate JSON Schema
2. **Strict mode** — OpenAI guarantees output matches schema exactly (constrained decoding)
3. **tool_use for extraction** — Anthropic's tool_use with `tool_choice` forces structured output through function calling
4. **outlines for local models** — token-level grammar constraints ensure valid JSON from any model
5. **Retry with error context** — on validation failure, feed errors back to model for self-correction'''
    ),
    (
        "ai/llm-tool-use",
        "Show LLM tool use and function calling patterns: tool definitions, multi-step chains, parallel tool calls, and agentic loops.",
        '''LLM tool use — function calling and agentic execution:

```python
import json
import asyncio
from typing import Any, Callable
from dataclasses import dataclass, field
from anthropic import Anthropic


# === Tool Registry ===

@dataclass
class Tool:
    """Registered tool with schema and implementation."""
    name: str
    description: str
    parameters: dict          # JSON Schema for parameters
    function: Callable        # Actual implementation
    requires_confirmation: bool = False  # Safety gate


class ToolRegistry:
    """Registry of available tools with schema generation."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        requires_confirmation: bool = False,
    ):
        """Decorator to register a tool function."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                function=func,
                requires_confirmation=requires_confirmation,
            )
            return func
        return decorator

    def get_schemas(self) -> list[dict]:
        """Get tool schemas for API call."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": list(tool.parameters.keys()),
                },
            }
            for tool in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return tool.function(**arguments)


# === Define tools ===

tools = ToolRegistry()


@tools.register(
    name="search_codebase",
    description="Search the codebase for files matching a pattern or containing specific text",
    parameters={
        "query": {"type": "string", "description": "Search query (regex supported)"},
        "file_pattern": {"type": "string", "description": "Glob pattern for files, e.g. '*.py'"},
    },
)
def search_codebase(query: str, file_pattern: str = "**/*") -> dict:
    import subprocess
    result = subprocess.run(
        ["rg", "--json", "-g", file_pattern, query],
        capture_output=True, text=True, timeout=30,
    )
    matches = []
    for line in result.stdout.strip().split("\\n"):
        if not line:
            continue
        data = json.loads(line)
        if data.get("type") == "match":
            matches.append({
                "file": data["data"]["path"]["text"],
                "line": data["data"]["line_number"],
                "text": data["data"]["lines"]["text"].strip(),
            })
    return {"matches": matches[:20], "total": len(matches)}


@tools.register(
    name="read_file",
    description="Read the contents of a file",
    parameters={
        "path": {"type": "string", "description": "Path to the file to read"},
    },
)
def read_file(path: str) -> dict:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}
    if p.stat().st_size > 100_000:
        return {"error": "File too large (>100KB)"}
    return {"content": p.read_text(), "size": p.stat().st_size}


@tools.register(
    name="run_tests",
    description="Run test suite and return results",
    parameters={
        "test_path": {"type": "string", "description": "Path to test file or directory"},
    },
)
def run_tests(test_path: str) -> dict:
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", test_path, "--tb=short", "-q"],
        capture_output=True, text=True, timeout=120,
    )
    return {
        "passed": result.returncode == 0,
        "stdout": result.stdout[-2000:],  # Last 2K chars
        "stderr": result.stderr[-1000:],
    }


# === Agentic Tool-Use Loop ===

class Agent:
    """LLM agent with tool-use loop.

    Flow:
    1. Send user message + tool schemas to LLM
    2. If LLM returns tool_use blocks, execute tools
    3. Send tool results back to LLM
    4. Repeat until LLM responds with text (no tool calls)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        model: str = "claude-sonnet-4-6",
        max_turns: int = 20,
        system_prompt: str = "You are a helpful coding assistant with access to tools.",
    ):
        self.client = Anthropic()
        self.registry = registry
        self.model = model
        self.max_turns = max_turns
        self.system_prompt = system_prompt

    def run(self, user_message: str) -> str:
        """Execute agentic loop until completion."""
        messages = [{"role": "user", "content": user_message}]
        tool_schemas = self.registry.get_schemas()

        for turn in range(self.max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=tool_schemas,
                messages=messages,
            )

            # Check if we're done (no tool use, just text)
            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            # Process tool calls
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({json.dumps(block.input)[:100]})")

                    try:
                        result = self.registry.execute(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        })
                    except Exception as e:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        })

            messages.append({"role": "user", "content": tool_results})

        return "Max turns reached without completion."

    def _extract_text(self, response) -> str:
        return "\\n".join(
            block.text for block in response.content
            if hasattr(block, "text")
        )


# === Usage ===

agent = Agent(registry=tools)

# Single tool call
result = agent.run("Find all Python files that import asyncio")

# Multi-step reasoning (agent decides which tools to use and in what order)
result = agent.run(
    "Find the bug in the authentication middleware. "
    "Look at the auth files, understand the flow, "
    "run the tests to see what fails, and explain the fix."
)
```

Tool use patterns:

| Pattern | Description | Example |
|---------|-------------|---------|
| **Single tool** | One function call | "What time is it?" → get_time() |
| **Sequential** | Chain of dependent calls | search → read → analyze |
| **Parallel** | Independent calls at once | read file A + read file B |
| **Conditional** | Tool choice based on prior results | if tests fail → read error → fix |
| **Recursive** | Tool triggers another agent | code review agent → test agent |

Key patterns:
1. **Tool registry** — centralized schema + implementation mapping; auto-generates API-compatible schemas
2. **Agentic loop** — keep calling LLM until `stop_reason == "end_turn"` (no more tool calls needed)
3. **Error as tool result** — return errors as tool results with `is_error: True`; LLM can self-correct
4. **Safety gates** — `requires_confirmation` flag for destructive tools; prompt user before executing
5. **Result truncation** — limit tool output size to prevent context overflow; LLM can request more detail'''
    ),
]
