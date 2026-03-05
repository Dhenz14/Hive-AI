"""P0 Batch: Agentic AI workflows, MCP, chain-of-thought, self-play."""

PAIRS = [
    (
        "Model Context Protocol (MCP) architecture",
        "Explain the Model Context Protocol (MCP) — what problem does it solve, how does its client-server architecture work, and how do you build an MCP server that exposes tools to any LLM client? Show complete working code.",
        """## Model Context Protocol (MCP): The USB-C of AI Tool Integration

### The Problem MCP Solves

Before MCP, every AI application reinvented tool integration. Claude needed custom code to call APIs. ChatGPT needed plugins with a different spec. Every LLM framework (LangChain, LlamaIndex, CrewAI) had its own tool definition format. This meant: N models × M tools = N×M integrations.

MCP standardizes this into a **single protocol**. Any MCP-compatible client (Claude Desktop, VS Code, custom apps) can connect to any MCP server (database, API, filesystem) through a uniform interface. Now it's N + M integrations instead of N×M.

### Architecture

```
┌──────────────┐     stdio/SSE      ┌──────────────┐
│  MCP Client  │ ◄───────────────► │  MCP Server  │
│ (Claude, IDE) │   JSON-RPC 2.0    │ (your tools) │
└──────────────┘                    └──────────────┘
```

The protocol uses JSON-RPC 2.0 over either stdio (local processes) or Server-Sent Events (remote). Three core primitives:

1. **Tools** — Functions the LLM can call (like `query_database`, `create_file`)
2. **Resources** — Read-only data the LLM can access (like file contents, DB schemas)
3. **Prompts** — Reusable prompt templates with parameters

### Building an MCP Server in Python

```python
# mcp_weather_server.py — A complete MCP server exposing weather tools
import json
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create the server instance
server = Server("weather-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    \"\"\"Declare what tools this server provides.\"\"\"
    return [
        Tool(
            name="get_weather",
            description="Get current weather for a city. Returns temperature, conditions, and humidity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'London' or 'Tokyo'",
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "default": "celsius",
                    },
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="get_forecast",
            description="Get 5-day weather forecast for a city.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 5},
                },
                "required": ["city"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    \"\"\"Handle tool invocations from the LLM client.\"\"\"
    if name == "get_weather":
        city = arguments["city"]
        units = arguments.get("units", "celsius")
        # In production, call a real weather API
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.weatherapi.com/v1/current.json",
                params={"key": "YOUR_KEY", "q": city},
            )
            data = resp.json()
        current = data["current"]
        temp = current["temp_c"] if units == "celsius" else current["temp_f"]
        return [TextContent(
            type="text",
            text=json.dumps({
                "city": city,
                "temperature": temp,
                "units": units,
                "condition": current["condition"]["text"],
                "humidity": current["humidity"],
            }, indent=2),
        )]

    elif name == "get_forecast":
        city = arguments["city"]
        days = arguments.get("days", 5)
        # Simplified forecast response
        return [TextContent(
            type="text",
            text=f"5-day forecast for {city}: [Mock data — replace with real API call]",
        )]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    \"\"\"Run the MCP server over stdio.\"\"\"
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Connecting to Claude Desktop

Add this to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["path/to/mcp_weather_server.py"]
    }
  }
}
```

Claude will now see and can call `get_weather` and `get_forecast` as tools during conversation.

### Why MCP Matters for AI Self-Improvement

The key insight is **composability**. A single MCP server can be used by Claude, by a custom agent, by an IDE plugin, or by another AI system. This means the tool ecosystem grows once and benefits everyone. For AI self-improvement specifically, an MCP server could expose:

- Training data management tools (add/score/dedup pairs)
- Model evaluation tools (run benchmarks, compare results)
- Knowledge graph query tools (search, add triples)

The LLM doesn't need custom code for each — it just uses the standard MCP protocol to call whatever tools are available.""",
    ),

    (
        "ReAct agent pattern implementation",
        "Implement the ReAct (Reasoning + Acting) agent pattern from scratch in Python. Show how the agent interleaves thinking and tool use to solve multi-step problems, with a complete working example.",
        """## ReAct: Teaching AI to Think Before It Acts

### Why ReAct Exists

The fundamental problem with naive LLM tool use is that the model either **thinks** (generates text) or **acts** (calls tools), but doesn't interleave them. ReAct (Yao et al., 2023) solves this by forcing the model to alternate between:

1. **Thought** — Reason about what to do next and why
2. **Action** — Call a tool with specific arguments
3. **Observation** — Process the tool's result

This interleaving is critical because each observation informs the next thought. Without it, the agent plans everything upfront and can't adapt when intermediate results are unexpected.

### The Core Loop

```python
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    parameters: dict = field(default_factory=dict)


class ReActAgent:
    \"\"\"
    ReAct agent that interleaves reasoning and tool use.

    The key design decision is the structured output format.
    We force the LLM to emit Thought/Action/Action Input on
    separate lines, which makes parsing reliable. Free-form
    output leads to brittle regex parsing and silent failures.
    \"\"\"

    SYSTEM_PROMPT = \"\"\"You are a helpful AI assistant that solves problems step by step.

You have access to these tools:
{tool_descriptions}

To use a tool, respond with EXACTLY this format:
Thought: [your reasoning about what to do next]
Action: [tool name]
Action Input: [JSON arguments]

When you have the final answer, respond with:
Thought: [your final reasoning]
Final Answer: [your answer]

Important: ALWAYS start with a Thought. Never skip reasoning.\"\"\"

    def __init__(self, llm_fn: Callable[[str], str], tools: list[Tool], max_steps: int = 10):
        self.llm = llm_fn
        self.tools = {t.name: t for t in tools}
        self.max_steps = max_steps

    def _build_system_prompt(self) -> str:
        descriptions = "\\n".join(
            f"- {t.name}: {t.description}" for t in self.tools.values()
        )
        return self.SYSTEM_PROMPT.format(tool_descriptions=descriptions)

    def _parse_response(self, text: str) -> dict:
        \"\"\"
        Parse the LLM's structured output into thought/action/input.

        Why not use JSON mode? Because ReAct needs the model to
        think in natural language first, then emit structured action.
        Forcing full JSON kills the reasoning quality.
        \"\"\"
        result = {"thought": "", "action": None, "action_input": None, "final_answer": None}

        thought_match = re.search(r"Thought:\\s*(.+?)(?=\\n(?:Action|Final))", text, re.DOTALL)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        final_match = re.search(r"Final Answer:\\s*(.+)", text, re.DOTALL)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return result

        action_match = re.search(r"Action:\\s*(.+?)\\n", text)
        input_match = re.search(r"Action Input:\\s*(.+)", text, re.DOTALL)
        if action_match:
            result["action"] = action_match.group(1).strip()
        if input_match:
            raw = input_match.group(1).strip()
            try:
                result["action_input"] = json.loads(raw)
            except json.JSONDecodeError:
                result["action_input"] = {"query": raw}

        return result

    def run(self, question: str) -> str:
        \"\"\"
        Execute the ReAct loop until a final answer or max steps.

        Each iteration: LLM thinks → calls tool → observes result.
        The full trajectory is kept in the prompt so the LLM can
        reason about ALL previous observations, not just the last one.
        \"\"\"
        messages = [self._build_system_prompt(), f"Question: {question}"]
        trajectory = []

        for step in range(self.max_steps):
            prompt = "\\n\\n".join(messages + trajectory)
            response = self.llm(prompt)
            parsed = self._parse_response(response)

            if parsed["final_answer"]:
                return parsed["final_answer"]

            if parsed["action"] and parsed["action"] in self.tools:
                tool = self.tools[parsed["action"]]
                try:
                    observation = tool.func(**parsed["action_input"])
                except Exception as e:
                    observation = f"Error: {e}"

                trajectory.append(
                    f"Thought: {parsed['thought']}\\n"
                    f"Action: {parsed['action']}\\n"
                    f"Action Input: {json.dumps(parsed['action_input'])}\\n"
                    f"Observation: {observation}"
                )
            else:
                trajectory.append(f"Thought: {parsed['thought']}\\n"
                                  f"Observation: Tool '{parsed['action']}' not found. Available: {list(self.tools.keys())}")

        return "Max steps reached without a final answer."
```

### Complete Working Example

```python
# Define tools
def search_web(query: str) -> str:
    \"\"\"Simulated web search.\"\"\"
    knowledge = {
        "python creator": "Guido van Rossum created Python in 1991.",
        "rust creator": "Graydon Hoare created Rust. Version 1.0 released in 2015.",
        "guido van rossum age": "Guido van Rossum was born January 31, 1956.",
    }
    for key, value in knowledge.items():
        if key in query.lower():
            return value
    return f"No results found for: {query}"


def calculate(expression: str) -> str:
    \"\"\"Safe math evaluation.\"\"\"
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return "Error: only numeric expressions allowed"
    try:
        return str(eval(expression))  # Safe: only numbers and operators
    except Exception as e:
        return f"Calculation error: {e}"


tools = [
    Tool(name="search", description="Search for factual information", func=search_web),
    Tool(name="calculate", description="Evaluate a math expression", func=calculate),
]


def mock_llm(prompt: str) -> str:
    \"\"\"Simulate LLM responses for demonstration.\"\"\"
    if "Question:" in prompt and "Observation:" not in prompt:
        return ("Thought: I need to find out who created Python and when.\\n"
                "Action: search\\nAction Input: {\\"query\\": \\"python creator\\"}")
    elif "1991" in prompt and "age" not in prompt.split("Observation:")[-1]:
        return ("Thought: Python was created in 1991. Now I need Guido's birth year to calculate his age.\\n"
                "Action: search\\nAction Input: {\\"query\\": \\"Guido van Rossum age\\"}")
    elif "1956" in prompt:
        return ("Thought: Guido was born in 1956. Current year is 2026. Let me calculate.\\n"
                "Action: calculate\\nAction Input: {\\"expression\\": \\"2026 - 1956\\"}")
    else:
        return ("Thought: I now have all the information.\\n"
                "Final Answer: Python was created by Guido van Rossum in 1991. He is currently 70 years old (born 1956).")


agent = ReActAgent(llm_fn=mock_llm, tools=tools)
answer = agent.run("Who created Python, and how old are they now?")
print(answer)
# Output: Python was created by Guido van Rossum in 1991. He is currently 70 years old (born 1956).
```

### Why ReAct Beats Plan-then-Execute

The critical difference: **plan-then-execute** generates all steps upfront, then runs them. If step 2's result changes what step 3 should be, the plan is already wrong. ReAct re-reasons after every observation, so it naturally adapts. The tradeoff is more LLM calls (one per step), but the accuracy gain on multi-hop questions is 20-30% in benchmarks.""",
    ),

    (
        "multi-agent collaboration patterns",
        "How do you design a system where multiple AI agents collaborate to solve complex tasks? Show the key patterns (supervisor, debate, assembly line) with working Python implementations and explain when to use each.",
        """## Multi-Agent Collaboration: Three Patterns That Actually Work

### Why Multiple Agents?

A single LLM prompt has a fixed context window and a single perspective. For complex tasks — writing a full application, researching a nuanced topic, reviewing code — splitting work across specialized agents produces better results because:

1. **Specialization** — Each agent has a focused system prompt and toolset
2. **Parallelism** — Independent subtasks run concurrently
3. **Quality through disagreement** — Multiple perspectives catch errors

### Pattern 1: Supervisor (Orchestrator-Worker)

One agent decides what to do; workers execute. Best for **decomposable tasks** where a human would delegate to a team.

```python
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class AgentResult:
    agent_name: str
    task: str
    result: str
    confidence: float = 1.0


class SupervisorAgent:
    \"\"\"
    Orchestrator that decomposes tasks and delegates to specialists.

    Why a supervisor instead of letting agents self-organize?
    Because LLMs are bad at coordination but good at following
    specific instructions. The supervisor pattern plays to this
    strength: one agent plans, others execute narrow tasks.
    \"\"\"

    def __init__(self, llm_fn, workers: dict[str, Callable]):
        self.llm = llm_fn
        self.workers = workers

    async def solve(self, task: str) -> str:
        # Step 1: Decompose the task
        plan_prompt = (
            f"Break this task into subtasks. For each, specify which worker to use.\\n"
            f"Available workers: {list(self.workers.keys())}\\n"
            f"Task: {task}\\n"
            f"Reply as JSON: [{{\\"worker\\": \\"name\\", \\"subtask\\": \\"description\\"}}]"
        )
        plan = self.llm(plan_prompt)

        import json
        subtasks = json.loads(plan)

        # Step 2: Execute subtasks (parallel when independent)
        results = await asyncio.gather(*[
            self._run_worker(s["worker"], s["subtask"])
            for s in subtasks
        ])

        # Step 3: Synthesize results
        synthesis_prompt = (
            f"Original task: {task}\\n\\n"
            f"Worker results:\\n" +
            "\\n".join(f"- {r.agent_name}: {r.result}" for r in results) +
            f"\\n\\nSynthesize a final answer."
        )
        return self.llm(synthesis_prompt)

    async def _run_worker(self, worker_name: str, subtask: str) -> AgentResult:
        if worker_name not in self.workers:
            return AgentResult(worker_name, subtask, f"Unknown worker: {worker_name}", 0.0)
        result = await self.workers[worker_name](subtask)
        return AgentResult(worker_name, subtask, result)
```

### Pattern 2: Debate (Adversarial Collaboration)

Two+ agents argue opposing positions; a judge synthesizes. Best for **decisions requiring nuance** — architecture choices, code review, risk assessment.

```python
class DebateAgent:
    \"\"\"
    Two agents debate; a judge picks the stronger argument.

    Why debate works: LLMs have a sycophancy bias — they agree
    with the user. By forcing one agent to argue FOR and another
    AGAINST, you counteract this bias and surface real tradeoffs.
    \"\"\"

    def __init__(self, llm_fn, rounds: int = 3):
        self.llm = llm_fn
        self.rounds = rounds

    def debate(self, question: str) -> str:
        pro_history = []
        con_history = []

        for round_num in range(self.rounds):
            # Pro agent argues FOR
            pro_prompt = (
                f"You are arguing FOR this position: {question}\\n"
                f"Previous arguments:\\n{self._format_history(pro_history, con_history)}\\n"
                f"Make your strongest argument. Address the opponent's points."
            )
            pro_arg = self.llm(pro_prompt)
            pro_history.append(pro_arg)

            # Con agent argues AGAINST
            con_prompt = (
                f"You are arguing AGAINST this position: {question}\\n"
                f"Previous arguments:\\n{self._format_history(pro_history, con_history)}\\n"
                f"Make your strongest counterargument. Address the opponent's points."
            )
            con_arg = self.llm(con_prompt)
            con_history.append(con_arg)

        # Judge synthesizes
        judge_prompt = (
            f"Question: {question}\\n\\n"
            f"FOR arguments:\\n" + "\\n".join(f"{i+1}. {a}" for i, a in enumerate(pro_history)) +
            f"\\n\\nAGAINST arguments:\\n" + "\\n".join(f"{i+1}. {a}" for i, a in enumerate(con_history)) +
            f"\\n\\nAs a neutral judge, which position is stronger? Why? What nuances did both sides miss?"
        )
        return self.llm(judge_prompt)

    def _format_history(self, pro: list, con: list) -> str:
        lines = []
        for i in range(max(len(pro), len(con))):
            if i < len(pro):
                lines.append(f"PRO (round {i+1}): {pro[i]}")
            if i < len(con):
                lines.append(f"CON (round {i+1}): {con[i]}")
        return "\\n".join(lines) if lines else "(No previous arguments)"
```

### Pattern 3: Assembly Line (Pipeline)

Each agent transforms the output and passes it to the next. Best for **sequential workflows** — research → write → review → edit.

```python
class PipelineAgent:
    \"\"\"
    Assembly line: each stage transforms and passes forward.

    Why pipeline over supervisor? When stages are naturally
    sequential and each stage's output IS the next stage's input.
    Supervisor is better when subtasks are independent.
    \"\"\"

    def __init__(self, stages: list[tuple[str, Callable[[str], str]]]):
        self.stages = stages  # (name, transform_fn) pairs

    def run(self, initial_input: str) -> dict:
        current = initial_input
        trace = {"input": initial_input, "stages": []}

        for name, transform in self.stages:
            result = transform(current)
            trace["stages"].append({"name": name, "input": current[:200], "output": result[:200]})
            current = result

        trace["final_output"] = current
        return trace


# Example: Research → Write → Review → Edit pipeline
def research(topic: str) -> str:
    return f"Key facts about {topic}: [research results]"

def write(research: str) -> str:
    return f"Article based on: {research}\\n[draft content]"

def review(draft: str) -> str:
    return f"Review of draft: Strengths: clear structure. Weaknesses: needs more examples.\\n{draft}"

def edit(reviewed: str) -> str:
    return f"Final edited version with examples added.\\n{reviewed}"

pipeline = PipelineAgent([
    ("researcher", research),
    ("writer", write),
    ("reviewer", review),
    ("editor", edit),
])
result = pipeline.run("quantum computing")
```

### When to Use Each Pattern

| Pattern | Best For | Tradeoff |
|---------|----------|----------|
| **Supervisor** | Decomposable tasks, parallel subtasks | Higher latency (planning step), but parallel execution |
| **Debate** | Decisions, reviews, risk assessment | Most expensive (2×rounds LLM calls), but highest quality |
| **Pipeline** | Sequential workflows, content production | Fastest for sequential work, but no parallelism |

The common mistake is over-engineering: most tasks don't need multi-agent. Use a single agent with tools first. Only add agents when a single prompt consistently fails because the task requires multiple perspectives or exceeds context limits.""",
    ),

    (
        "chain-of-thought and test-time compute scaling",
        "Explain chain-of-thought prompting and test-time compute scaling — why does 'thinking longer' improve LLM accuracy? Show the techniques (CoT, self-consistency, tree-of-thought) with working Python implementations.",
        """## Chain-of-Thought: Why Thinking Longer Produces Better Answers

### The Core Insight

LLMs are next-token predictors. When you ask "What is 17 × 24?", the model predicts the answer token directly — which often fails because multiplication isn't a single pattern-match. But if you ask "Think step by step", the model generates intermediate tokens (17 × 20 = 340, 17 × 4 = 68, 340 + 68 = 408) that **carry information forward** through the computation.

This is test-time compute scaling: spending more inference tokens to get better accuracy. The key finding from research (Wei et al. 2022, OpenAI o1 2024) is that accuracy scales with the amount of reasoning, not just model size.

### Technique 1: Basic Chain-of-Thought

```python
def basic_cot(llm_fn, question: str) -> str:
    \"\"\"
    Zero-shot CoT: just add 'think step by step'.

    Why this works: the intermediate tokens create a 'scratchpad'
    in the model's context. Each step's output becomes input for
    the next step, allowing multi-hop reasoning that a single
    forward pass can't do.
    \"\"\"
    prompt = f"{question}\\n\\nThink step by step, then give your final answer."
    return llm_fn(prompt)


def few_shot_cot(llm_fn, question: str) -> str:
    \"\"\"
    Few-shot CoT: provide examples of reasoning chains.

    More reliable than zero-shot because the examples teach
    the model the expected reasoning FORMAT, not just that
    it should reason.
    \"\"\"
    examples = \"\"\"
Q: If a store has 3 shelves with 8 books each, and 5 books are sold, how many remain?
A: Let me work through this step by step.
Step 1: Total books = 3 shelves x 8 books = 24 books
Step 2: Books remaining = 24 - 5 sold = 19 books
Final answer: 19

Q: A train travels 120 km in 2 hours, then 90 km in 1.5 hours. What's the average speed?
A: Let me work through this step by step.
Step 1: Total distance = 120 + 90 = 210 km
Step 2: Total time = 2 + 1.5 = 3.5 hours
Step 3: Average speed = 210 / 3.5 = 60 km/h
Final answer: 60 km/h
\"\"\"
    prompt = f"{examples}\\nQ: {question}\\nA: Let me work through this step by step."
    return llm_fn(prompt)
```

### Technique 2: Self-Consistency (Majority Voting)

```python
import collections


def self_consistency(llm_fn, question: str, n_samples: int = 5, temperature: float = 0.7) -> str:
    \"\"\"
    Sample multiple reasoning chains, take majority vote on final answer.

    Why this works: different reasoning paths can lead to different
    answers. Correct answers tend to be reachable by MORE paths than
    incorrect ones. So the majority vote filters out reasoning errors.

    The tradeoff: n_samples × cost, but accuracy gains of 5-15%
    on math/logic tasks. Diminishing returns beyond ~10 samples.
    \"\"\"
    answers = []

    for i in range(n_samples):
        response = llm_fn(
            f"{question}\\nThink step by step, then give your final answer on the last line.",
            temperature=temperature,
        )
        # Extract the final answer (last line or after "Final answer:")
        lines = response.strip().split("\\n")
        final = lines[-1].strip()
        # Normalize: extract just the number/value
        import re
        numbers = re.findall(r"[\\d,]+\\.?\\d*", final)
        if numbers:
            answers.append(numbers[-1])
        else:
            answers.append(final)

    # Majority vote
    counter = collections.Counter(answers)
    best_answer, count = counter.most_common(1)[0]
    confidence = count / n_samples

    return f"{best_answer} (confidence: {confidence:.0%}, {count}/{n_samples} chains agreed)"
```

### Technique 3: Tree-of-Thought (Branching Search)

```python
from dataclasses import dataclass, field
import heapq


@dataclass
class ThoughtNode:
    state: str          # Current reasoning state
    steps: list = field(default_factory=list)  # Steps taken so far
    score: float = 0.0  # LLM-evaluated quality of this path

    def __lt__(self, other):
        return self.score > other.score  # Max-heap: higher scores first


def tree_of_thought(llm_fn, question: str, max_depth: int = 4, beam_width: int = 3) -> str:
    \"\"\"
    Tree-of-Thought: explore multiple reasoning branches, prune bad ones.

    Why ToT beats linear CoT: when the first reasoning step is wrong,
    linear CoT can't recover. ToT generates MULTIPLE possible first
    steps, evaluates each, and only expands the promising ones.
    This is beam search over reasoning paths.

    Cost: beam_width × max_depth LLM calls for generation
          + beam_width × max_depth calls for evaluation
    Use when: the problem has clear dead-ends that can be detected
    early (puzzles, planning, math proofs).
    \"\"\"
    root = ThoughtNode(state=question)
    beam = [root]

    for depth in range(max_depth):
        candidates = []

        for node in beam:
            # Generate possible next steps
            gen_prompt = (
                f"Problem: {question}\\n"
                f"Steps so far: {node.steps}\\n"
                f"Generate 3 different possible next steps. "
                f"Format: STEP1: ...\\nSTEP2: ...\\nSTEP3: ..."
            )
            response = llm_fn(gen_prompt)

            # Parse the generated steps
            for line in response.split("\\n"):
                line = line.strip()
                if line.startswith(("STEP", "1:", "2:", "3:")):
                    step_text = line.split(":", 1)[-1].strip()
                    if step_text:
                        new_state = f"{node.state}\\n{step_text}"
                        child = ThoughtNode(
                            state=new_state,
                            steps=node.steps + [step_text],
                        )

                        # Evaluate this path
                        eval_prompt = (
                            f"Problem: {question}\\n"
                            f"Reasoning path: {child.steps}\\n"
                            f"Rate this reasoning path from 0.0 to 1.0. "
                            f"Is it making progress toward the answer? "
                            f"Reply with just the number."
                        )
                        score_text = llm_fn(eval_prompt)
                        try:
                            child.score = float(score_text.strip()[:4])
                        except ValueError:
                            child.score = 0.5
                        candidates.append(child)

        # Keep top-k candidates (beam search)
        candidates.sort(key=lambda c: c.score, reverse=True)
        beam = candidates[:beam_width]

        # Early termination if top candidate is confident
        if beam and beam[0].score > 0.95:
            break

    # Final answer from the best path
    best = beam[0] if beam else root
    final_prompt = (
        f"Problem: {question}\\n"
        f"Reasoning steps: {best.steps}\\n"
        f"Based on this reasoning, what is the final answer?"
    )
    return llm_fn(final_prompt)
```

### Scaling Laws for Test-Time Compute

The key finding: **you can trade model size for inference compute**. A smaller model with 10× more thinking tokens can match a larger model's accuracy. This has practical implications:

```python
# Cost comparison for equivalent accuracy
STRATEGIES = {
    "large_model_direct":  {"model": "70B", "tokens": 100,   "cost_ratio": 1.0},
    "small_model_cot":     {"model": "7B",  "tokens": 500,   "cost_ratio": 0.3},
    "small_model_sc5":     {"model": "7B",  "tokens": 2500,  "cost_ratio": 1.5},
    "small_model_tot":     {"model": "7B",  "tokens": 5000,  "cost_ratio": 3.0},
}
# For many tasks, small_model_cot gives the best cost/accuracy tradeoff.
# Self-consistency is worth it only for high-stakes decisions.
# ToT is only worth it for problems with clear prunable dead-ends.
```

The mental model: CoT is greedy search, self-consistency is random sampling, ToT is beam search. Choose based on how much you're willing to spend for how much accuracy gain.""",
    ),

    (
        "self-play for code model improvement",
        "Explain self-play techniques for improving code generation models. How can a model generate its own training data through execution feedback, adversarial generation, and debate? Show practical implementations.",
        """## Self-Play for Code Models: The Model Trains Itself

### Why Self-Play Works for Code

Code has a unique property: **you can verify it automatically**. Unlike natural language where quality is subjective, code either runs correctly or it doesn't. This means a model can:

1. Generate candidate solutions
2. Execute them against test cases
3. Use pass/fail as a reward signal
4. Train on the successful trajectories

This is fundamentally different from training on static datasets — the model discovers solutions the dataset never contained.

### Technique 1: Execution-Guided Self-Training

```python
import subprocess
import tempfile
import json
from dataclasses import dataclass


@dataclass
class SelfPlayResult:
    instruction: str
    solution: str
    test_code: str
    passed: bool
    error: str = ""
    execution_time_ms: float = 0.0


def execute_python_safely(code: str, timeout: int = 10) -> tuple[bool, str]:
    \"\"\"Run Python code in an isolated subprocess with timeout.\"\"\"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["python", f.name],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout: code took too long"
        except Exception as e:
            return False, str(e)


def self_play_round(llm_fn, topic: str, n_attempts: int = 5) -> list[SelfPlayResult]:
    \"\"\"
    One round of self-play:
    1. Model generates a coding challenge
    2. Model generates test cases for it
    3. Model attempts to solve it (multiple tries)
    4. Solutions are executed and verified
    5. Only passing solutions become training data

    Why generate the challenge too? Because the model learns to
    create HARDER problems over time. Easy problems don't produce
    useful training data — the model already knows how to solve them.
    \"\"\"
    # Step 1: Generate a challenge
    challenge_prompt = (
        f"Create a Python coding challenge about {topic}.\\n"
        f"Requirements:\\n"
        f"- Function signature with type hints\\n"
        f"- Clear description of expected behavior\\n"
        f"- At least 3 edge cases\\n\\n"
        f"Format:\\n"
        f"FUNCTION: def function_name(args) -> return_type\\n"
        f"DESCRIPTION: what it should do\\n"
        f"EXAMPLES: input -> output pairs"
    )
    challenge = llm_fn(challenge_prompt)

    # Step 2: Generate test cases
    test_prompt = (
        f"Write pytest test cases for this challenge:\\n{challenge}\\n\\n"
        f"Write at least 8 test cases covering:\\n"
        f"- Normal inputs\\n- Edge cases (empty, None, zero)\\n"
        f"- Large inputs\\n- Error conditions\\n\\n"
        f"Format as a complete pytest file."
    )
    test_code = llm_fn(test_prompt)

    # Step 3: Multiple solution attempts at different temperatures
    results = []
    for attempt in range(n_attempts):
        solve_prompt = (
            f"Solve this challenge. Write ONLY the Python function, nothing else.\\n\\n"
            f"{challenge}"
        )
        solution = llm_fn(solve_prompt, temperature=0.3 + attempt * 0.15)

        # Step 4: Execute solution + tests together
        combined_code = f"{solution}\\n\\n{test_code}"
        passed, output = execute_python_safely(combined_code)

        results.append(SelfPlayResult(
            instruction=challenge,
            solution=solution,
            test_code=test_code,
            passed=passed,
            error=output if not passed else "",
        ))

    return results


def self_play_loop(llm_fn, topics: list[str], rounds: int = 10) -> list[dict]:
    \"\"\"
    Multi-round self-play that produces training pairs.

    The key insight: we keep BOTH passing and failing solutions.
    Passing solutions become positive training data.
    Failing solutions (with the error) become debugging training data:
      instruction = 'Fix this code: [broken code]\\nError: [error message]'
      response = [working solution]

    This teaches the model both how to write code AND how to debug it.
    \"\"\"
    training_pairs = []

    for round_num in range(rounds):
        for topic in topics:
            results = self_play_round(llm_fn, topic)

            passing = [r for r in results if r.passed]
            failing = [r for r in results if not r.passed]

            # Positive pairs: challenge -> working solution
            for r in passing:
                training_pairs.append({
                    "instruction": r.instruction,
                    "response": r.solution,
                    "source": "self_play_positive",
                    "quality": 0.9,
                })

            # Debug pairs: broken code + error -> working solution
            if passing and failing:
                best_solution = passing[0].solution
                for r in failing:
                    debug_instruction = (
                        f"Debug and fix this Python code:\\n\\n"
                        f"```python\\n{r.solution}\\n```\\n\\n"
                        f"Error: {r.error[:500]}"
                    )
                    training_pairs.append({
                        "instruction": debug_instruction,
                        "response": best_solution,
                        "source": "self_play_debug",
                        "quality": 0.85,
                    })

    return training_pairs
```

### Technique 2: Adversarial Self-Play

```python
def adversarial_self_play(llm_fn, domain: str) -> list[dict]:
    \"\"\"
    Two roles: Generator creates increasingly hard problems,
    Solver tries to solve them. The Generator learns to find
    the Solver's weak spots.

    This is how AlphaGo improved: by playing against itself
    and discovering strategies no human had seen. For code,
    the Generator discovers edge cases and problem types
    that expose the Solver's weaknesses.
    \"\"\"
    difficulty_prompt = (
        f"You are an adversarial problem creator for {domain}.\\n"
        f"Create a problem that is solvable but tricky. Focus on:\\n"
        f"- Subtle edge cases\\n"
        f"- Performance traps (O(n^2) vs O(n) matters)\\n"
        f"- Off-by-one errors\\n"
        f"- Type coercion surprises\\n\\n"
        f"The problem MUST be solvable in under 50 lines of Python."
    )

    problem = llm_fn(difficulty_prompt)
    solution = llm_fn(f"Solve this problem:\\n{problem}")
    test_code = llm_fn(f"Write exhaustive pytest tests for:\\n{problem}")

    combined = f"{solution}\\n\\n{test_code}"
    passed, output = execute_python_safely(combined)

    return [{
        "problem": problem,
        "solution": solution,
        "passed": passed,
        "error": output if not passed else "",
    }]
```

### When Self-Play Produces Diminishing Returns

Self-play has a ceiling: the model can't generate problems harder than it can solve. After enough rounds, it starts generating the same types of problems. Two mitigations:

1. **Curriculum difficulty escalation** — Force harder constraints each round
2. **External verification** — Use a stronger model or formal verification to check solutions the base model can't verify

The practical sweet spot is 50-100 rounds of self-play before switching to a different improvement technique (like distillation from a stronger model or human-curated challenges).""",
    ),

    (
        "vLLM and inference engine architecture",
        "Explain how modern LLM inference engines like vLLM work — PagedAttention, continuous batching, speculative decoding. Why are they 10-24x faster than naive inference? Show the key data structures and algorithms.",
        """## LLM Inference Engines: Why vLLM is 10-24× Faster

### The Bottleneck: KV Cache Memory

Every transformer layer stores key-value pairs for all previous tokens. For a 13B model with 2048 context, a single request's KV cache is ~1.7GB. With naive serving, you pre-allocate this for every request, even if the actual sequence is 50 tokens. This wastes 97% of GPU memory.

### PagedAttention: Virtual Memory for KV Cache

vLLM's key innovation is treating KV cache like an OS treats RAM — using paging.

```python
from dataclasses import dataclass, field
import numpy as np


@dataclass
class KVBlock:
    \"\"\"
    A fixed-size block of KV cache entries (like a memory page).

    Why fixed-size blocks? Same reason OS pages are fixed: it
    eliminates external fragmentation. Any free block can hold
    any sequence's data. Without this, you get memory holes that
    can't be used — which is exactly what naive pre-allocation does.
    \"\"\"
    block_id: int
    block_size: int = 16  # tokens per block
    data: np.ndarray = None  # Shape: [2, num_heads, block_size, head_dim]
    ref_count: int = 0       # For copy-on-write sharing

    def __post_init__(self):
        if self.data is None:
            # Allocate on GPU in practice; numpy for illustration
            self.data = np.zeros((2, 32, self.block_size, 128), dtype=np.float16)


class BlockAllocator:
    \"\"\"
    Manages a pool of KV cache blocks — like an OS page allocator.

    Pre-allocates ALL GPU memory as blocks at startup.
    Sequences request blocks as they grow, return them when done.
    This achieves near-zero waste: only the last block per sequence
    may have unused slots.
    \"\"\"

    def __init__(self, num_blocks: int, block_size: int = 16):
        self.block_size = block_size
        self.free_blocks: list[KVBlock] = [
            KVBlock(block_id=i, block_size=block_size) for i in range(num_blocks)
        ]
        self.used_blocks: dict[int, KVBlock] = {}

    def allocate(self) -> KVBlock:
        if not self.free_blocks:
            raise MemoryError("KV cache full — need to preempt a sequence")
        block = self.free_blocks.pop()
        block.ref_count = 1
        self.used_blocks[block.block_id] = block
        return block

    def free(self, block: KVBlock):
        block.ref_count -= 1
        if block.ref_count <= 0:
            del self.used_blocks[block.block_id]
            block.data.fill(0)
            self.free_blocks.append(block)

    def fork(self, block: KVBlock) -> KVBlock:
        \"\"\"
        Copy-on-write: share a block between sequences.

        Why COW? Beam search creates N copies of a sequence.
        Without COW, each copy duplicates the entire KV cache.
        With COW, they share blocks until they diverge —
        reducing memory N× for beam search.
        \"\"\"
        block.ref_count += 1
        return block

    @property
    def utilization(self) -> float:
        total = len(self.free_blocks) + len(self.used_blocks)
        return len(self.used_blocks) / total if total else 0.0
```

### Continuous Batching: No Wasted GPU Cycles

Naive batching waits for ALL sequences in a batch to finish before starting new ones. If one sequence generates 500 tokens and another generates 10, the GPU sits idle for 490 steps waiting for the long one.

```python
from collections import deque
from enum import Enum


class SeqStatus(Enum):
    WAITING = "waiting"      # In queue, not yet started
    RUNNING = "running"      # Actively generating tokens
    FINISHED = "finished"    # Hit EOS or max length
    PREEMPTED = "preempted"  # Swapped out due to memory pressure


@dataclass
class Sequence:
    seq_id: int
    prompt_tokens: list[int]
    output_tokens: list[int] = field(default_factory=list)
    status: SeqStatus = SeqStatus.WAITING
    kv_blocks: list[KVBlock] = field(default_factory=list)
    max_tokens: int = 512


class ContinuousBatchScheduler:
    \"\"\"
    Iteration-level scheduling: after EACH token generation step,
    check if any sequence finished. If so, immediately start a
    new one from the waiting queue.

    Why this matters: with static batching of batch_size=32,
    throughput is limited by the LONGEST sequence. With continuous
    batching, short sequences free their slots immediately,
    keeping the GPU saturated. This alone gives 2-5× throughput.
    \"\"\"

    def __init__(self, max_batch_size: int, allocator: BlockAllocator):
        self.max_batch_size = max_batch_size
        self.allocator = allocator
        self.waiting: deque[Sequence] = deque()
        self.running: list[Sequence] = []

    def add_request(self, prompt_tokens: list[int], max_tokens: int = 512):
        seq = Sequence(
            seq_id=id(prompt_tokens),
            prompt_tokens=prompt_tokens,
            max_tokens=max_tokens,
        )
        self.waiting.append(seq)

    def schedule_step(self) -> list[Sequence]:
        \"\"\"
        Called before each forward pass. Returns the batch to process.

        Key decisions:
        1. Admit new sequences if there's room
        2. Preempt low-priority sequences if memory is tight
        3. Remove finished sequences
        \"\"\"
        # Remove finished sequences, free their blocks
        finished = [s for s in self.running if s.status == SeqStatus.FINISHED]
        for seq in finished:
            for block in seq.kv_blocks:
                self.allocator.free(block)
            self.running.remove(seq)

        # Admit waiting sequences
        while self.waiting and len(self.running) < self.max_batch_size:
            seq = self.waiting.popleft()
            # Allocate initial KV blocks for the prompt
            blocks_needed = (len(seq.prompt_tokens) + self.allocator.block_size - 1) // self.allocator.block_size
            try:
                seq.kv_blocks = [self.allocator.allocate() for _ in range(blocks_needed)]
                seq.status = SeqStatus.RUNNING
                self.running.append(seq)
            except MemoryError:
                # Memory pressure: put it back and stop admitting
                self.waiting.appendleft(seq)
                break

        return self.running

    def process_outputs(self, tokens: list[tuple[int, int]]):
        \"\"\"Process generated tokens: (seq_id, token_id) pairs.\"\"\"
        for seq in self.running:
            for sid, token in tokens:
                if sid == seq.seq_id:
                    seq.output_tokens.append(token)
                    # Check if done
                    if token == 2 or len(seq.output_tokens) >= seq.max_tokens:  # EOS=2
                        seq.status = SeqStatus.FINISHED
                    # Allocate new block if current one is full
                    total_tokens = len(seq.prompt_tokens) + len(seq.output_tokens)
                    blocks_needed = (total_tokens + self.allocator.block_size - 1) // self.allocator.block_size
                    while len(seq.kv_blocks) < blocks_needed:
                        try:
                            seq.kv_blocks.append(self.allocator.allocate())
                        except MemoryError:
                            seq.status = SeqStatus.PREEMPTED
                            break
```

### Speculative Decoding: Draft-then-Verify

```python
def speculative_decode(
    draft_model_fn,   # Small, fast model (e.g., 1B)
    target_model_fn,  # Large, accurate model (e.g., 70B)
    prompt: list[int],
    gamma: int = 5,   # Number of draft tokens per step
) -> list[int]:
    \"\"\"
    Speculative decoding: draft model proposes gamma tokens,
    target model verifies all at once in a single forward pass.

    Why this works: the target model's forward pass takes the
    same time for 1 token or gamma tokens (it's memory-bound,
    not compute-bound). So if the draft model's guesses are
    mostly correct (70-90% acceptance rate), you get gamma×
    speedup for free.

    Typical speedup: 2-3× for well-matched draft/target pairs.
    \"\"\"
    output = list(prompt)

    while True:
        # Draft: generate gamma tokens with the small model
        draft_tokens = []
        draft_probs = []
        for _ in range(gamma):
            token, prob = draft_model_fn(output + draft_tokens)
            draft_tokens.append(token)
            draft_probs.append(prob)

        # Verify: run target model on ALL draft tokens at once
        # This is ONE forward pass, not gamma forward passes
        target_probs = target_model_fn(output, draft_tokens)

        # Accept/reject each draft token
        accepted = 0
        for i in range(gamma):
            # Acceptance probability: min(1, target_prob / draft_prob)
            acceptance = min(1.0, target_probs[i] / max(draft_probs[i], 1e-10))
            import random
            if random.random() < acceptance:
                output.append(draft_tokens[i])
                accepted += 1
            else:
                # Reject: sample from adjusted distribution and stop
                # This ensures the output distribution matches the target
                output.append(sample_adjusted(target_probs[i], draft_probs[i]))
                break

        if output[-1] == 2:  # EOS
            break

    return output
```

### Performance Comparison

| Technique | Speedup | Memory Saving | Implementation Complexity |
|-----------|---------|---------------|--------------------------|
| PagedAttention | 1× (enables others) | 55-95% waste eliminated | High |
| Continuous Batching | 2-5× throughput | Moderate | Medium |
| Speculative Decoding | 2-3× latency | Slight increase (draft model) | Medium |
| Combined (vLLM) | **10-24× vs naive** | **Near-optimal** | **High** |

The 10-24× number comes from the combination: PagedAttention allows more concurrent sequences, continuous batching keeps the GPU saturated, and speculative decoding reduces per-token latency.""",
    ),
]
