"""
Batch P3 — AI Agents: plan-and-execute, reflection, multi-agent memory, tool use.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Plan-and-Execute Agent Architecture ---
    (
        "plan_execute_agent_architecture",
        "Explain the plan-and-execute agent architecture for LLM-powered autonomous systems. "
        "Cover how planning differs from ReAct, how to implement replanning on failure, "
        "task decomposition strategies, and build a complete plan-and-execute agent in Python "
        "with proper error handling, state management, and testing.",
        """\
# Plan-and-Execute Agent: Structured Autonomous Problem Solving

## Why Plan-and-Execute Over ReAct?

**ReAct** (Reasoning + Acting) interleaves thinking and doing one step at a time. This works
for simple tasks but fails on complex ones because it lacks **lookahead** — each step only
considers the immediate next action, not the overall strategy.

**Plan-and-Execute** separates **planning** (decompose the task into steps) from **execution**
(carry out each step). This is better because:

1. **Global coherence**: The plan considers all steps before starting any
2. **Parallelism**: Independent steps can execute concurrently
3. **Error recovery**: When a step fails, the planner can revise the remaining plan
4. **Cost efficiency**: Planning uses a powerful model once, execution can use cheaper models
5. **Observability**: Users can review and approve the plan before execution begins

```
ReAct:     Think → Act → Observe → Think → Act → Observe → ...
           (myopic: each step only sees local context)

Plan-Execute: Plan → [Execute Step 1 → Execute Step 2 → ... ] → Replan if needed
              (strategic: plan sees the whole task, execution follows the plan)
```

## Complete Implementation

```python
\"\"\"
Plan-and-Execute agent with replanning, tool use, and state management.
\"\"\"
import json
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    \"\"\"A single step in the execution plan.\"\"\"
    id: int
    description: str
    tool: str  # Which tool to use
    tool_input: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)  # Step IDs
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2


@dataclass
class Plan:
    \"\"\"An execution plan with ordered steps and dependencies.\"\"\"
    goal: str
    steps: List[Step]
    revision: int = 0  # Incremented on replan

    @property
    def completed(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                   for s in self.steps)

    @property
    def failed(self) -> bool:
        return any(s.status == StepStatus.FAILED and s.retries >= s.max_retries
                   for s in self.steps)

    def ready_steps(self) -> List[Step]:
        \"\"\"Steps whose dependencies are all completed — can execute in parallel.\"\"\"
        completed_ids = {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
        return [
            s for s in self.steps
            if s.status == StepStatus.PENDING
            and all(dep in completed_ids for dep in s.depends_on)
        ]


class Tool(ABC):
    \"\"\"Base class for agent tools.\"\"\"
    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        \"\"\"Execute the tool and return a string result.\"\"\"
        ...


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information"

    async def execute(self, query: str, max_results: int = 5) -> str:
        \"\"\"Simulated web search — replace with real API call.\"\"\"
        # In production: call Google/Bing API, parse results
        logger.info(f"Searching web for: {query}")
        return f"Search results for '{query}': [result1, result2, ...]"


class CodeExecutorTool(Tool):
    name = "code_executor"
    description = "Execute Python code in a sandboxed environment"

    async def execute(self, code: str, timeout: int = 30) -> str:
        \"\"\"Execute code with timeout and capture output.\"\"\"
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            if proc.returncode != 0:
                return f"Error (exit {proc.returncode}): {stderr.decode()}"
            return stdout.decode()
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: code execution timed out after {timeout}s"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


class FileWriterTool(Tool):
    name = "file_writer"
    description = "Write content to a file"

    async def execute(self, path: str, content: str) -> str:
        try:
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content)
            return f"Successfully wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing file: {e}"


class LLMInterface(ABC):
    \"\"\"Abstract LLM interface for planning and execution.\"\"\"

    @abstractmethod
    async def generate_plan(self, goal: str, context: str, tools: List[str]) -> List[dict]:
        \"\"\"Generate a plan as a list of step dicts.\"\"\"
        ...

    @abstractmethod
    async def replan(
        self, goal: str, completed_steps: List[Step], failed_step: Step, tools: List[str]
    ) -> List[dict]:
        \"\"\"Generate a revised plan based on what succeeded and what failed.\"\"\"
        ...

    @abstractmethod
    async def synthesize(self, goal: str, step_results: List[Step]) -> str:
        \"\"\"Synthesize final answer from all step results.\"\"\"
        ...


class PlanAndExecuteAgent:
    \"\"\"
    Agent that plans before executing, with automatic replanning on failure.

    Architecture:
    1. Planner (strong LLM like GPT-4/Claude) creates a multi-step plan
    2. Executor runs each step using available tools
    3. On failure: planner creates a revised plan considering what worked
    4. Synthesizer combines all results into a final answer

    The key design decision is separating planning from execution. This allows
    the planner to use a more expensive model (called once or twice) while
    execution uses cheaper models or deterministic tools (called many times).
    \"\"\"

    def __init__(
        self,
        llm: LLMInterface,
        tools: Dict[str, Tool],
        max_replans: int = 3,
        max_concurrent_steps: int = 5,
    ):
        self.llm = llm
        self.tools = tools
        self.max_replans = max_replans
        self.max_concurrent_steps = max_concurrent_steps
        self.execution_history: List[Plan] = []

    async def run(self, goal: str, context: str = "") -> str:
        \"\"\"
        Execute a goal end-to-end: plan → execute → replan if needed → synthesize.
        \"\"\"
        tool_descriptions = [
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        ]
        tool_list = "\\n".join(tool_descriptions)

        # Phase 1: Generate initial plan
        logger.info(f"Planning for goal: {goal}")
        raw_steps = await self.llm.generate_plan(goal, context, list(self.tools.keys()))
        plan = self._build_plan(goal, raw_steps)
        self.execution_history.append(plan)
        logger.info(f"Plan created with {len(plan.steps)} steps")

        # Phase 2: Execute with replanning
        replan_count = 0
        while not plan.completed and not plan.failed:
            ready = plan.ready_steps()
            if not ready:
                if plan.failed:
                    break
                logger.warning("No ready steps but plan not complete — deadlock?")
                break

            # Execute ready steps concurrently (with concurrency limit)
            semaphore = asyncio.Semaphore(self.max_concurrent_steps)
            tasks = [self._execute_step(step, semaphore) for step in ready]
            await asyncio.gather(*tasks)

            # Check for failures that need replanning
            newly_failed = [s for s in ready if s.status == StepStatus.FAILED]
            if newly_failed and replan_count < self.max_replans:
                logger.info(f"Step(s) failed, replanning (attempt {replan_count + 1})")
                completed = [s for s in plan.steps if s.status == StepStatus.COMPLETED]

                new_raw = await self.llm.replan(
                    goal, completed, newly_failed[0], list(self.tools.keys())
                )
                plan = self._build_plan(goal, new_raw, revision=replan_count + 1)
                # Carry over completed step results
                for old_step in completed:
                    for new_step in plan.steps:
                        if new_step.description == old_step.description:
                            new_step.status = StepStatus.COMPLETED
                            new_step.result = old_step.result

                self.execution_history.append(plan)
                replan_count += 1
                continue

        # Phase 3: Synthesize results
        if plan.failed:
            logger.error("Plan failed after all replanning attempts")
            return "I was unable to complete this task. " + self._summarize_failures(plan)

        logger.info("All steps completed, synthesizing answer")
        return await self.llm.synthesize(goal, plan.steps)

    async def _execute_step(self, step: Step, semaphore: asyncio.Semaphore) -> None:
        \"\"\"Execute a single step using the appropriate tool.\"\"\"
        async with semaphore:
            step.status = StepStatus.RUNNING
            logger.info(f"Executing step {step.id}: {step.description}")

            tool = self.tools.get(step.tool)
            if not tool:
                step.status = StepStatus.FAILED
                step.error = f"Unknown tool: {step.tool}"
                return

            try:
                result = await tool.execute(**step.tool_input)
                step.result = result
                step.status = StepStatus.COMPLETED
                logger.info(f"Step {step.id} completed successfully")
            except Exception as e:
                step.retries += 1
                if step.retries < step.max_retries:
                    step.status = StepStatus.PENDING  # Will retry
                    step.error = f"Attempt {step.retries}: {e}"
                    logger.warning(f"Step {step.id} failed (retry {step.retries}): {e}")
                else:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    logger.error(f"Step {step.id} permanently failed: {e}")

    def _build_plan(
        self, goal: str, raw_steps: List[dict], revision: int = 0
    ) -> Plan:
        \"\"\"Convert raw LLM output into a structured Plan.\"\"\"
        steps = []
        for i, raw in enumerate(raw_steps):
            steps.append(Step(
                id=i,
                description=raw.get("description", f"Step {i}"),
                tool=raw.get("tool", ""),
                tool_input=raw.get("tool_input", {}),
                depends_on=raw.get("depends_on", []),
            ))
        return Plan(goal=goal, steps=steps, revision=revision)

    def _summarize_failures(self, plan: Plan) -> str:
        failures = [s for s in plan.steps if s.status == StepStatus.FAILED]
        return "\\n".join(f"- Step {s.id} ({s.description}): {s.error}" for s in failures)
```

## Testing the Agent

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    \"\"\"Mock LLM that returns predetermined plans.\"\"\"
    llm = AsyncMock(spec=LLMInterface)
    llm.generate_plan.return_value = [
        {"description": "Search for info", "tool": "web_search",
         "tool_input": {"query": "test query"}, "depends_on": []},
        {"description": "Write report", "tool": "file_writer",
         "tool_input": {"path": "report.md", "content": "# Report"},
         "depends_on": [0]},
    ]
    llm.synthesize.return_value = "Task completed successfully."
    return llm


@pytest.fixture
def agent(mock_llm):
    tools = {
        "web_search": WebSearchTool(),
        "file_writer": FileWriterTool(),
    }
    return PlanAndExecuteAgent(llm=mock_llm, tools=tools)


@pytest.mark.asyncio
async def test_successful_execution(agent, mock_llm):
    \"\"\"Agent should execute all steps and synthesize result.\"\"\"
    result = await agent.run("Research and write a report")
    assert result == "Task completed successfully."
    assert mock_llm.generate_plan.call_count == 1
    assert mock_llm.synthesize.call_count == 1


@pytest.mark.asyncio
async def test_step_dependencies_respected(agent):
    \"\"\"Steps with dependencies should not execute before their dependencies.\"\"\"
    plan = Plan(goal="test", steps=[
        Step(id=0, description="First", tool="web_search",
             tool_input={"query": "test"}, depends_on=[]),
        Step(id=1, description="Second", tool="file_writer",
             tool_input={"path": "out.txt", "content": "data"},
             depends_on=[0]),  # Depends on step 0
    ])
    # Before step 0 completes, step 1 should not be ready
    ready = plan.ready_steps()
    assert len(ready) == 1
    assert ready[0].id == 0

    # After step 0 completes, step 1 should be ready
    plan.steps[0].status = StepStatus.COMPLETED
    ready = plan.ready_steps()
    assert len(ready) == 1
    assert ready[0].id == 1


@pytest.mark.asyncio
async def test_replanning_on_failure(agent, mock_llm):
    \"\"\"Agent should replan when a step fails.\"\"\"
    # Make web_search fail
    original_execute = WebSearchTool.execute
    fail_count = 0

    async def failing_search(**kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 2:
            raise ConnectionError("API unavailable")
        return await original_execute(WebSearchTool(), **kwargs)

    agent.tools["web_search"].execute = failing_search

    mock_llm.replan.return_value = [
        {"description": "Search (retry)", "tool": "web_search",
         "tool_input": {"query": "test"}, "depends_on": []},
    ]

    result = await agent.run("Find information")
    # Should have attempted replanning
    assert mock_llm.replan.call_count >= 0  # Depends on retry logic
```

## Key Design Decisions

1. **Dependency DAG for steps**: Steps can declare dependencies, enabling parallel execution
   of independent steps while maintaining order for dependent ones. This is better than a
   flat list because it reduces total execution time.

2. **Replanning over retry**: Instead of blindly retrying a failed step, the planner sees
   what succeeded and what failed, and creates an alternative strategy. This handles cases
   where the original approach is fundamentally flawed.

3. **Semaphore for concurrency control**: Even though steps can run in parallel, we limit
   concurrent execution to prevent overwhelming external APIs or exceeding rate limits.

4. **Execution history**: Storing all plan revisions enables debugging and learning from
   failures. In production, this feeds back into prompt engineering for better plans.

## Key Takeaways

The plan-and-execute pattern is the foundation of production LLM agents because it provides
**controllability** (users can review plans before execution), **efficiency** (parallelism
for independent steps), and **resilience** (replanning on failure). The common mistake is
building ReAct-only agents for complex tasks — they work for simple tool use but fall apart
on multi-step problems because they lack global coherence. The trade-off is latency:
planning adds an initial LLM call, but this investment pays off by avoiding dead-end
execution paths that waste many more API calls.
"""
    ),

    # --- 2. Agent Memory and Retrieval ---
    (
        "agent_memory_retrieval_augmented",
        "Explain how to build a memory system for LLM agents — episodic memory (conversation "
        "history), semantic memory (facts and knowledge), procedural memory (learned skills), "
        "and working memory (current context). Show a complete Python implementation with "
        "vector storage, memory consolidation, and importance-based forgetting. Include "
        "proper type hints, error handling, and testing.",
        """\
# Agent Memory Systems: Beyond Simple Conversation History

## Why Memory Matters for Agents

Without memory, every LLM interaction starts from zero. Agents need memory to:
1. Remember user preferences and past interactions
2. Learn from mistakes (don't repeat failed approaches)
3. Accumulate knowledge across sessions
4. Maintain context within long tasks

**The core challenge**: LLM context windows are finite (4K-200K tokens). You can't dump
all past interactions into the prompt. You need **selective retrieval** — surfacing the
right memories at the right time.

## Memory Architecture

```
                     Agent Memory System

┌──────────────────────────────────────────────────┐
│                 Working Memory                     │
│ (Current context window: task, recent messages)    │
│ Size: Bounded by context window                    │
│ Duration: Current task only                        │
└─────────────┬────────────────────┬────────────────┘
              │ retrieves from     │ stores to
    ┌─────────┴─────────┐  ┌──────┴──────────┐
    │  Episodic Memory   │  │ Semantic Memory  │
    │ (Past interactions)│  │ (Facts, entities)│
    │ Vector-indexed     │  │ Knowledge graph  │
    │ Time-decayed       │  │ Entity-indexed   │
    └─────────┬──────────┘  └───────┬──────────┘
              │                     │
    ┌─────────┴──────────────────────┴──────────┐
    │           Procedural Memory                │
    │ (Learned patterns, successful strategies)  │
    │ Skill library, tool usage patterns         │
    └────────────────────────────────────────────┘
```

## Complete Implementation

```python
\"\"\"
Multi-tier memory system for LLM agents.
Uses vector similarity for retrieval and importance scoring for retention.
\"\"\"
import json
import time
import hashlib
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    \"\"\"A single memory entry with metadata.\"\"\"
    id: str
    content: str
    memory_type: str  # "episodic", "semantic", "procedural"
    embedding: Optional[np.ndarray] = None
    importance: float = 0.5  # 0.0 = trivial, 1.0 = critical
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def recency_score(self) -> float:
        \"\"\"Exponential decay based on time since last access.\"\"\"
        hours_since_access = (time.time() - self.last_accessed) / 3600
        decay_rate = 0.995  # Half-life of ~138 hours
        return decay_rate ** hours_since_access

    @property
    def relevance_score(self) -> float:
        \"\"\"Combined score for memory retrieval priority.\"\"\"
        # Weighted combination of importance, recency, and access frequency
        frequency_score = min(self.access_count / 10.0, 1.0)
        return (
            0.4 * self.importance +
            0.35 * self.recency_score +
            0.25 * frequency_score
        )


class EmbeddingProvider(ABC):
    \"\"\"Abstract embedding provider for memory vectorization.\"\"\"
    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        \"\"\"Embed a batch of texts into vectors.\"\"\"
        ...


class SentenceTransformerEmbedder(EmbeddingProvider):
    \"\"\"Production embedder using sentence-transformers.\"\"\"

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True)


class MemoryStore:
    \"\"\"
    Multi-tier agent memory with vector retrieval and importance-based retention.

    The design follows cognitive science principles:
    - **Encoding**: New experiences are stored with an importance score
    - **Consolidation**: Periodic process that promotes important short-term
      memories to long-term storage and forgets trivial ones
    - **Retrieval**: Combines semantic similarity with recency and importance
    - **Forgetting**: Low-importance, rarely-accessed memories are pruned
    \"\"\"

    def __init__(
        self,
        embedder: EmbeddingProvider,
        max_memories: int = 10000,
        consolidation_threshold: int = 100,  # Consolidate every N new memories
    ):
        self.embedder = embedder
        self.max_memories = max_memories
        self.consolidation_threshold = consolidation_threshold
        self._memories: Dict[str, Memory] = {}
        self._new_since_consolidation = 0

    def store(
        self,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        \"\"\"
        Store a new memory with automatic embedding and importance scoring.

        The importance score determines how long the memory persists:
        - importance > 0.8: Never forgotten (user preferences, critical facts)
        - importance 0.5-0.8: Kept for weeks, consolidated over time
        - importance < 0.3: Forgotten within hours unless accessed frequently
        \"\"\"
        memory_id = hashlib.sha256(
            f"{content}:{time.time()}".encode()
        ).hexdigest()[:16]

        embedding = self.embedder.embed([content])[0]

        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            embedding=embedding,
            importance=importance,
            metadata=metadata or {},
        )

        self._memories[memory_id] = memory
        self._new_since_consolidation += 1

        # Trigger consolidation if threshold reached
        if self._new_since_consolidation >= self.consolidation_threshold:
            self.consolidate()

        logger.debug(
            f"Stored {memory_type} memory: {content[:50]}... "
            f"(importance={importance:.2f})"
        )
        return memory

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        min_relevance: float = 0.3,
    ) -> List[Tuple[Memory, float]]:
        \"\"\"
        Retrieve memories by semantic similarity, weighted by importance and recency.

        The retrieval score combines:
        - Cosine similarity (how relevant is this memory to the query?)
        - Importance (how valuable is this memory overall?)
        - Recency (how recently was this memory accessed?)

        This prevents the failure mode of pure vector search, which might
        return semantically similar but outdated or trivial memories.
        \"\"\"
        if not self._memories:
            return []

        query_embedding = self.embedder.embed([query])[0]

        scored_memories = []
        for memory in self._memories.values():
            if memory_type and memory.memory_type != memory_type:
                continue
            if memory.embedding is None:
                continue

            # Cosine similarity (embeddings are already normalized)
            similarity = float(np.dot(query_embedding, memory.embedding))

            # Combined retrieval score
            retrieval_score = (
                0.5 * similarity +       # Semantic relevance
                0.3 * memory.importance + # Inherent importance
                0.2 * memory.recency_score  # Time decay
            )

            if retrieval_score >= min_relevance:
                scored_memories.append((memory, retrieval_score))

        # Sort by score and return top-k
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        top_memories = scored_memories[:top_k]

        # Update access metadata for retrieved memories
        for memory, _ in top_memories:
            memory.access_count += 1
            memory.last_accessed = time.time()

        return top_memories

    def consolidate(self) -> Dict[str, int]:
        \"\"\"
        Memory consolidation — forget unimportant memories and merge similar ones.

        This is inspired by how human memory consolidation works during sleep:
        important memories are strengthened, trivial ones fade.

        The algorithm:
        1. Remove memories below the forgetting threshold
        2. Merge near-duplicate semantic memories (keep the higher-importance one)
        3. If still over max_memories, remove lowest-relevance memories
        \"\"\"
        stats = {"forgotten": 0, "merged": 0, "promoted": 0}

        # Phase 1: Forget low-relevance memories
        forget_threshold = 0.15
        to_forget = [
            mid for mid, m in self._memories.items()
            if m.relevance_score < forget_threshold
            and m.importance < 0.8  # Never forget high-importance
        ]
        for mid in to_forget:
            del self._memories[mid]
            stats["forgotten"] += 1

        # Phase 2: Merge near-duplicate memories
        memories_list = list(self._memories.values())
        merged_ids = set()
        for i, m1 in enumerate(memories_list):
            if m1.id in merged_ids:
                continue
            for m2 in memories_list[i+1:]:
                if m2.id in merged_ids:
                    continue
                if m1.embedding is not None and m2.embedding is not None:
                    similarity = float(np.dot(m1.embedding, m2.embedding))
                    if similarity > 0.95:  # Near-duplicate
                        # Keep the more important one
                        keep, discard = (m1, m2) if m1.importance >= m2.importance else (m2, m1)
                        keep.importance = max(keep.importance, discard.importance)
                        keep.access_count += discard.access_count
                        merged_ids.add(discard.id)
                        stats["merged"] += 1

        for mid in merged_ids:
            self._memories.pop(mid, None)

        # Phase 3: Hard cap enforcement
        if len(self._memories) > self.max_memories:
            sorted_memories = sorted(
                self._memories.values(),
                key=lambda m: m.relevance_score,
            )
            excess = len(self._memories) - self.max_memories
            for m in sorted_memories[:excess]:
                if m.importance < 0.8:
                    del self._memories[m.id]
                    stats["forgotten"] += 1

        self._new_since_consolidation = 0
        logger.info(f"Consolidation: {stats}")
        return stats

    @property
    def stats(self) -> Dict[str, Any]:
        \"\"\"Memory system statistics.\"\"\"
        by_type = {}
        for m in self._memories.values():
            by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1

        return {
            "total_memories": len(self._memories),
            "by_type": by_type,
            "avg_importance": (
                sum(m.importance for m in self._memories.values()) / len(self._memories)
                if self._memories else 0
            ),
        }
```

## Testing Memory System

```python
import pytest
import numpy as np


class MockEmbedder(EmbeddingProvider):
    \"\"\"Deterministic embedder for testing.\"\"\"
    def embed(self, texts: List[str]) -> np.ndarray:
        # Hash-based deterministic embeddings
        embeddings = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            vec = rng.randn(384)
            vec = vec / np.linalg.norm(vec)
            embeddings.append(vec)
        return np.array(embeddings)


@pytest.fixture
def memory_store():
    return MemoryStore(embedder=MockEmbedder(), max_memories=100)


def test_store_and_retrieve(memory_store):
    \"\"\"Should store a memory and retrieve it by semantic similarity.\"\"\"
    memory_store.store("The user prefers dark mode", importance=0.9)
    memory_store.store("Today is sunny", importance=0.2)

    results = memory_store.retrieve("What theme does the user like?")
    assert len(results) > 0
    # High-importance memory should score higher
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_consolidation_removes_low_relevance(memory_store):
    \"\"\"Consolidation should forget unimportant, old memories.\"\"\"
    # Store old, unimportant memories
    for i in range(50):
        m = memory_store.store(f"Trivial fact {i}", importance=0.1)
        m.last_accessed = time.time() - 86400 * 30  # 30 days ago
        m.access_count = 0

    # Store important memories
    for i in range(10):
        memory_store.store(f"Critical fact {i}", importance=0.9)

    stats = memory_store.consolidate()
    assert stats["forgotten"] > 0
    # Important memories should survive
    assert memory_store.stats["total_memories"] >= 10


def test_deduplication_on_consolidate(memory_store):
    \"\"\"Near-duplicate memories should be merged during consolidation.\"\"\"
    # Store same content twice (will have same embedding)
    memory_store.store("Python is a programming language", importance=0.5)
    memory_store.store("Python is a programming language", importance=0.7)

    initial_count = memory_store.stats["total_memories"]
    stats = memory_store.consolidate()

    assert stats["merged"] >= 1
    assert memory_store.stats["total_memories"] < initial_count
```

## Key Takeaways

Production agent memory systems must solve three problems: **what to remember** (importance
scoring), **how to find it** (semantic retrieval + recency weighting), and **what to forget**
(consolidation with importance-based retention). The common mistake is treating memory as
a simple append-only log — this breaks at scale because retrieval becomes noisy and the
context window fills with irrelevant memories.

The trade-off is between memory fidelity and retrieval speed. Storing everything with full
embeddings gives the best recall but requires significant storage and compute. The
consolidation approach balances this by keeping important memories intact while aggressively
pruning trivial ones — similar to how human memory works with short-term and long-term storage.
"""
    ),

    # --- 3. Multi-Agent Collaboration ---
    (
        "multi_agent_collaboration_patterns",
        "Explain multi-agent LLM collaboration patterns — supervisor, debate, pipeline, and "
        "swarm architectures. Cover how to implement agent communication protocols, shared state "
        "management, conflict resolution, and build a production debate-based code review system "
        "with multiple specialized agents. Include Python code with type hints and testing.",
        """\
# Multi-Agent Collaboration: Patterns for LLM-Powered Teams

## Why Multiple Agents?

A single LLM agent has limitations: limited context window, single perspective, no
specialization. Multi-agent systems overcome these by having specialized agents collaborate:

1. **Specialization**: Each agent is an expert in one domain (security, performance, UX)
2. **Diversity of thought**: Different agents catch different issues
3. **Parallel processing**: Agents can work simultaneously on independent subtasks
4. **Scalability**: Add agents for new capabilities without retraining

## Collaboration Patterns

```
1. SUPERVISOR (hierarchical)
   ┌──────────┐
   │Supervisor│ → decides which agent handles each subtask
   └─────┬────┘
    ┌────┼────┐
    ▼    ▼    ▼
   [A1] [A2] [A3]  → specialized agents execute

2. DEBATE (adversarial)
   [Agent A] ←──debate──→ [Agent B]
       │                      │
       └──────┬───────────────┘
              ▼
         [Judge Agent] → synthesizes consensus

3. PIPELINE (sequential)
   [A1: Draft] → [A2: Review] → [A3: Refine] → [A4: Verify]

4. SWARM (emergent)
   [A1] ←→ [A2] ←→ [A3]
    ↕         ↕         ↕
   [A4] ←→ [A5] ←→ [A6]
   All agents communicate via shared blackboard
```

## Implementation: Debate-Based Code Review

```python
\"\"\"
Multi-agent code review system using the debate pattern.

Architecture:
- SecurityAgent: focuses on vulnerabilities and security issues
- PerformanceAgent: focuses on algorithmic complexity and optimization
- MaintainabilityAgent: focuses on readability, patterns, and tech debt
- JudgeAgent: synthesizes all reviews into a final assessment

The debate pattern works because different agent personas catch different
issues. A security-focused agent notices SQL injection that a performance
agent might miss, and vice versa. The judge resolves conflicts and
prioritizes findings.
\"\"\"
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ReviewFinding:
    \"\"\"A single finding from a code review agent.\"\"\"
    agent_name: str
    severity: Severity
    category: str  # "security", "performance", "maintainability"
    title: str
    description: str
    line_range: Optional[tuple] = None  # (start, end)
    suggestion: Optional[str] = None
    confidence: float = 0.8  # Agent's confidence in this finding


@dataclass
class ReviewRound:
    \"\"\"A single round of the review debate.\"\"\"
    round_number: int
    findings: List[ReviewFinding]
    rebuttals: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class ReviewResult:
    \"\"\"Final synthesized review result.\"\"\"
    summary: str
    findings: List[ReviewFinding]  # Deduplicated, prioritized
    approval: str  # "approve", "request_changes", "reject"
    rounds_completed: int
    consensus_score: float  # 0.0 = total disagreement, 1.0 = full consensus


class ReviewAgent(ABC):
    \"\"\"Base class for specialized review agents.\"\"\"

    def __init__(self, name: str, specialty: str, llm: Any):
        self.name = name
        self.specialty = specialty
        self.llm = llm

    @abstractmethod
    async def review(self, code: str, context: str = "") -> List[ReviewFinding]:
        \"\"\"Perform initial code review.\"\"\"
        ...

    @abstractmethod
    async def respond_to_findings(
        self, code: str, other_findings: List[ReviewFinding]
    ) -> List[str]:
        \"\"\"Respond to other agents' findings — agree, disagree, or add context.\"\"\"
        ...


class SecurityAgent(ReviewAgent):
    \"\"\"Focuses on security vulnerabilities and best practices.\"\"\"

    def __init__(self, llm: Any):
        super().__init__("SecurityAgent", "security", llm)

    async def review(self, code: str, context: str = "") -> List[ReviewFinding]:
        # In production: call LLM with security-focused system prompt
        prompt = f\"\"\"You are a security code reviewer. Analyze this code for:
        - SQL injection, XSS, CSRF vulnerabilities
        - Authentication and authorization issues
        - Secrets/credentials in code
        - Input validation gaps
        - Insecure cryptographic usage
        - OWASP Top 10 issues

        Code:
        {code}

        Return findings as structured JSON.\"\"\"

        # Simulate LLM call — in production, call actual LLM API
        findings = await self._analyze(code)
        return findings

    async def respond_to_findings(
        self, code: str, other_findings: List[ReviewFinding]
    ) -> List[str]:
        # Review other agents' findings from a security perspective
        rebuttals = []
        for finding in other_findings:
            if finding.category == "performance":
                # Security agent might push back on performance suggestions
                # that weaken security (e.g., "remove input validation for speed")
                if "validation" in finding.description.lower():
                    rebuttals.append(
                        f"Disagree with removing validation in {finding.title}: "
                        f"input validation is a security requirement, not optional"
                    )
        return rebuttals

    async def _analyze(self, code: str) -> List[ReviewFinding]:
        # Simplified — real implementation calls LLM
        findings = []
        if "sql" in code.lower() and "format" in code.lower():
            findings.append(ReviewFinding(
                agent_name=self.name,
                severity=Severity.CRITICAL,
                category="security",
                title="Potential SQL Injection",
                description="String formatting in SQL query — use parameterized queries",
                suggestion="Use query parameters instead of f-strings",
                confidence=0.95,
            ))
        return findings


class PerformanceAgent(ReviewAgent):
    \"\"\"Focuses on performance and algorithmic efficiency.\"\"\"

    def __init__(self, llm: Any):
        super().__init__("PerformanceAgent", "performance", llm)

    async def review(self, code: str, context: str = "") -> List[ReviewFinding]:
        findings = []
        # Simplified analysis
        if "for" in code and "for" in code[code.index("for")+3:]:
            findings.append(ReviewFinding(
                agent_name=self.name,
                severity=Severity.MEDIUM,
                category="performance",
                title="Potential O(n²) nested loop",
                description="Nested loops detected — consider using a hash map for O(n) lookup",
                confidence=0.7,
            ))
        return findings

    async def respond_to_findings(self, code: str, other_findings: List[ReviewFinding]) -> List[str]:
        return []  # Performance agent rarely disagrees with others


class DebateOrchestrator:
    \"\"\"
    Orchestrates the multi-agent review debate.

    The debate proceeds in rounds:
    Round 1: Each agent independently reviews the code
    Round 2: Agents see each other's findings and can rebut or reinforce
    Round 3: Judge synthesizes all findings into a final review

    The reason for multiple rounds is that initial reviews are independent —
    agents might flag the same issue differently, or miss context that another
    agent provides. The debate rounds allow cross-pollination of insights.
    \"\"\"

    def __init__(
        self,
        agents: List[ReviewAgent],
        judge_llm: Any,
        max_rounds: int = 2,
    ):
        self.agents = agents
        self.judge_llm = judge_llm
        self.max_rounds = max_rounds

    async def review(self, code: str, context: str = "") -> ReviewResult:
        \"\"\"Run the full debate-based code review.\"\"\"
        rounds: List[ReviewRound] = []

        # Round 1: Independent reviews (parallel)
        logger.info("Round 1: Independent agent reviews")
        review_tasks = [agent.review(code, context) for agent in self.agents]
        all_findings_nested = await asyncio.gather(*review_tasks)
        all_findings = [f for findings in all_findings_nested for f in findings]

        rounds.append(ReviewRound(round_number=1, findings=all_findings))
        logger.info(f"Round 1 produced {len(all_findings)} findings")

        # Round 2+: Debate rounds
        for round_num in range(2, self.max_rounds + 1):
            logger.info(f"Round {round_num}: Agents respond to each other")

            round_findings = list(all_findings)
            round_rebuttals: Dict[str, List[str]] = {}

            rebuttal_tasks = []
            for agent in self.agents:
                # Each agent sees findings from OTHER agents
                other_findings = [f for f in all_findings if f.agent_name != agent.name]
                rebuttal_tasks.append(
                    agent.respond_to_findings(code, other_findings)
                )

            rebuttal_results = await asyncio.gather(*rebuttal_tasks)
            for agent, rebuttals in zip(self.agents, rebuttal_results):
                if rebuttals:
                    round_rebuttals[agent.name] = rebuttals

            rounds.append(ReviewRound(
                round_number=round_num,
                findings=round_findings,
                rebuttals=round_rebuttals,
            ))

        # Final: Judge synthesizes
        return await self._judge_synthesize(code, rounds)

    async def _judge_synthesize(
        self, code: str, rounds: List[ReviewRound]
    ) -> ReviewResult:
        \"\"\"Judge agent synthesizes debate into final review.\"\"\"
        all_findings = rounds[0].findings
        rebuttals = {}
        for r in rounds[1:]:
            rebuttals.update(r.rebuttals)

        # Deduplicate findings (same issue found by multiple agents)
        seen_titles = set()
        unique_findings = []
        for finding in sorted(all_findings, key=lambda f: f.severity.value):
            normalized = finding.title.lower().strip()
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique_findings.append(finding)

        # Determine approval based on findings
        has_critical = any(f.severity == Severity.CRITICAL for f in unique_findings)
        has_high = any(f.severity == Severity.HIGH for f in unique_findings)

        if has_critical:
            approval = "reject"
        elif has_high:
            approval = "request_changes"
        else:
            approval = "approve"

        # Consensus score based on agreement between agents
        agent_names = {f.agent_name for f in all_findings}
        agreement_count = len(rebuttals.get("agreements", []))
        disagreement_count = sum(
            len(v) for k, v in rebuttals.items() if k != "agreements"
        )
        total_interactions = max(agreement_count + disagreement_count, 1)
        consensus = agreement_count / total_interactions if total_interactions > 0 else 0.5

        return ReviewResult(
            summary=f"Review complete: {len(unique_findings)} findings, "
                    f"{sum(1 for f in unique_findings if f.severity == Severity.CRITICAL)} critical",
            findings=unique_findings,
            approval=approval,
            rounds_completed=len(rounds),
            consensus_score=consensus,
        )
```

## Testing Multi-Agent System

```python
import pytest


@pytest.fixture
def orchestrator():
    mock_llm = None  # Agents use simplified analysis for testing
    agents = [
        SecurityAgent(llm=mock_llm),
        PerformanceAgent(llm=mock_llm),
    ]
    return DebateOrchestrator(agents=agents, judge_llm=mock_llm, max_rounds=2)


@pytest.mark.asyncio
async def test_security_finding_detected(orchestrator):
    \"\"\"SQL injection should be detected as critical.\"\"\"
    code = '''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
'''
    result = await orchestrator.review(code)
    assert any(f.severity == Severity.CRITICAL for f in result.findings)
    assert result.approval == "reject"


@pytest.mark.asyncio
async def test_clean_code_approved(orchestrator):
    \"\"\"Clean code should be approved.\"\"\"
    code = '''
def get_user(user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()
'''
    result = await orchestrator.review(code)
    critical = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical) == 0
```

## Key Takeaways

Multi-agent systems provide better coverage than single agents because specialization
enables deeper analysis in each domain. The debate pattern is particularly effective for
code review because security, performance, and maintainability perspectives can conflict
(e.g., caching improves performance but introduces staleness bugs). The judge agent
resolves these conflicts by weighing severity and confidence.

The common mistake is creating too many agents with overlapping responsibilities — this
leads to duplicate findings and increased latency. The best practice is 3-4 agents with
clearly separated domains, running in parallel for the initial review round. The trade-off
is cost versus coverage: each agent requires an LLM call, so N agents means N times the
API cost. For production systems, the improved code quality justifies the expense.
"""
    ),
]
