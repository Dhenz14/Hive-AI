"""AI agent frameworks — LangChain, LlamaIndex, CrewAI, custom agent architectures."""

PAIRS = [
    (
        "ai/agent-memory",
        "Show AI agent memory patterns: short-term (conversation), long-term (vector store), episodic memory, and memory management.",
        '''Agent memory systems:

```python
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
from typing import Optional
import json


@dataclass
class Memory:
    content: str
    timestamp: datetime
    importance: float = 0.5
    access_count: int = 0
    last_accessed: datetime = None
    embedding: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)


class ShortTermMemory:
    """Conversation buffer with sliding window."""

    def __init__(self, max_messages: int = 20, max_tokens: int = 4000):
        self.messages: list[dict] = []
        self.max_messages = max_messages
        self.max_tokens = max_tokens

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        self._trim()

    def _trim(self):
        """Keep recent messages within limits."""
        while len(self.messages) > self.max_messages:
            self.messages.pop(0)

        # Estimate tokens and trim if needed
        total_tokens = sum(len(m["content"]) // 4 for m in self.messages)
        while total_tokens > self.max_tokens and len(self.messages) > 2:
            self.messages.pop(0)
            total_tokens = sum(len(m["content"]) // 4 for m in self.messages)

    def get_context(self) -> list[dict]:
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]

    def summarize_old(self, llm_fn) -> str:
        """Summarize oldest messages before removing them."""
        if len(self.messages) <= 5:
            return ""
        old = self.messages[:len(self.messages) - 5]
        text = "\\n".join(f"{m['role']}: {m['content']}" for m in old)
        return llm_fn(f"Summarize this conversation concisely:\\n{text}")


class LongTermMemory:
    """Vector-based long-term memory with importance scoring."""

    def __init__(self, embed_fn, max_memories: int = 10000):
        self.embed_fn = embed_fn
        self.memories: list[Memory] = []
        self.max_memories = max_memories

    def store(self, content: str, importance: float = 0.5, **metadata):
        embedding = self.embed_fn(content)
        memory = Memory(
            content=content,
            timestamp=datetime.now(),
            importance=importance,
            embedding=embedding,
            metadata=metadata,
        )
        self.memories.append(memory)

        # Evict low-importance memories if over limit
        if len(self.memories) > self.max_memories:
            self.memories.sort(key=lambda m: self._relevance_score(m))
            self.memories = self.memories[len(self.memories) - self.max_memories:]

    def recall(self, query: str, top_k: int = 5) -> list[Memory]:
        """Retrieve relevant memories using similarity + recency + importance."""
        query_emb = self.embed_fn(query)
        scored = []
        now = datetime.now()

        for memory in self.memories:
            if memory.embedding is None:
                continue

            # Cosine similarity
            sim = np.dot(query_emb, memory.embedding) / (
                np.linalg.norm(query_emb) * np.linalg.norm(memory.embedding) + 1e-8
            )

            # Recency decay
            hours_ago = (now - memory.timestamp).total_seconds() / 3600
            recency = np.exp(-0.01 * hours_ago)

            # Combined score
            score = 0.5 * sim + 0.3 * recency + 0.2 * memory.importance
            scored.append((memory, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Update access counts
        for memory, _ in scored[:top_k]:
            memory.access_count += 1
            memory.last_accessed = now

        return [m for m, _ in scored[:top_k]]

    def _relevance_score(self, memory: Memory) -> float:
        hours_ago = (datetime.now() - memory.timestamp).total_seconds() / 3600
        recency = np.exp(-0.01 * hours_ago)
        return 0.4 * memory.importance + 0.3 * recency + 0.3 * (memory.access_count / 10)


class EpisodicMemory:
    """Store and recall complete episodes (task sequences)."""

    def __init__(self):
        self.episodes: list[dict] = []

    def start_episode(self, goal: str):
        self.current = {
            "goal": goal,
            "steps": [],
            "start_time": datetime.now().isoformat(),
            "outcome": None,
        }

    def add_step(self, action: str, result: str, success: bool):
        self.current["steps"].append({
            "action": action,
            "result": result,
            "success": success,
        })

    def end_episode(self, outcome: str, success: bool):
        self.current["outcome"] = outcome
        self.current["success"] = success
        self.current["end_time"] = datetime.now().isoformat()
        self.episodes.append(self.current)
        self.current = None

    def find_similar_episodes(self, goal: str) -> list[dict]:
        """Find past episodes with similar goals."""
        # Simple keyword matching (use embeddings in production)
        goal_words = set(goal.lower().split())
        scored = []
        for ep in self.episodes:
            ep_words = set(ep["goal"].lower().split())
            overlap = len(goal_words & ep_words) / max(len(goal_words | ep_words), 1)
            scored.append((ep, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, score in scored[:3] if score > 0.2]


class AgentMemorySystem:
    """Combined memory system for AI agents."""

    def __init__(self, embed_fn):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(embed_fn)
        self.episodic = EpisodicMemory()

    def get_context(self, query: str) -> dict:
        """Get relevant context from all memory types."""
        return {
            "conversation": self.short_term.get_context(),
            "relevant_memories": [m.content for m in self.long_term.recall(query)],
            "similar_episodes": self.episodic.find_similar_episodes(query),
        }
```

Key patterns:
1. **Layered memory** — short-term (conversation), long-term (facts), episodic (experiences)
2. **Importance scoring** — weight memories by relevance, recency, and importance for retrieval
3. **Memory eviction** — remove low-scoring memories when over limit; bounded storage
4. **Summarization** — compress old conversation into summary before evicting
5. **Episode recall** — find similar past task sequences to inform current planning'''
    ),
    (
        "ai/agent-evaluation",
        "Show AI agent evaluation patterns: task success metrics, trajectory analysis, cost tracking, and benchmark frameworks.",
        '''Agent evaluation framework:

```python
import time
import json
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict


@dataclass
class AgentStep:
    action: str
    input: dict
    output: Any
    duration_ms: float
    tokens_used: int = 0
    cost: float = 0.0
    error: str = None


@dataclass
class AgentRun:
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    success: bool = False
    final_answer: str = ""
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    metadata: dict = field(default_factory=dict)


class AgentEvaluator:
    """Evaluate agent performance across multiple dimensions."""

    def __init__(self):
        self.runs: list[AgentRun] = []

    def evaluate_run(self, run: AgentRun, expected_answer: str = None) -> dict:
        """Evaluate a single agent run."""
        metrics = {
            "task": run.task,
            "success": run.success,
            "n_steps": len(run.steps),
            "duration_ms": run.total_duration_ms,
            "total_tokens": run.total_tokens,
            "total_cost": run.total_cost,
            "errors": sum(1 for s in run.steps if s.error),
            "tool_usage": self._tool_distribution(run),
        }

        # Answer accuracy (if expected provided)
        if expected_answer and run.final_answer:
            metrics["answer_match"] = self._check_answer(
                run.final_answer, expected_answer
            )

        # Efficiency metrics
        if run.success:
            metrics["cost_per_success"] = run.total_cost
            metrics["steps_per_success"] = len(run.steps)
        else:
            metrics["cost_per_success"] = float("inf")

        return metrics

    def _tool_distribution(self, run: AgentRun) -> dict:
        dist = defaultdict(int)
        for step in run.steps:
            dist[step.action] += 1
        return dict(dist)

    def _check_answer(self, actual: str, expected: str) -> float:
        """Simple answer matching (use LLM judge in production)."""
        actual_lower = actual.lower().strip()
        expected_lower = expected.lower().strip()

        if expected_lower in actual_lower:
            return 1.0

        # Word overlap
        actual_words = set(actual_lower.split())
        expected_words = set(expected_lower.split())
        if expected_words:
            overlap = len(actual_words & expected_words) / len(expected_words)
            return overlap

        return 0.0

    def aggregate_results(self, results: list[dict]) -> dict:
        """Aggregate metrics across multiple runs."""
        n = len(results)
        return {
            "n_tasks": n,
            "success_rate": sum(r["success"] for r in results) / n,
            "avg_steps": sum(r["n_steps"] for r in results) / n,
            "avg_duration_ms": sum(r["duration_ms"] for r in results) / n,
            "avg_cost": sum(r["total_cost"] for r in results) / n,
            "avg_tokens": sum(r["total_tokens"] for r in results) / n,
            "error_rate": sum(r["errors"] > 0 for r in results) / n,
            "cost_efficiency": sum(r["total_cost"] for r in results if r["success"]) / max(sum(r["success"] for r in results), 1),
        }

    def compare_agents(self, agent_results: dict[str, list[dict]]) -> dict:
        """Compare multiple agents on same benchmark."""
        comparison = {}
        for agent_name, results in agent_results.items():
            comparison[agent_name] = self.aggregate_results(results)
        return comparison
```

Agent evaluation dimensions:

| Metric | What it measures | Ideal |
|--------|-----------------|-------|
| **Success rate** | Task completion | Higher |
| **Steps to success** | Efficiency | Lower |
| **Cost per task** | API spend | Lower |
| **Error recovery** | Robustness | Higher recovery rate |
| **Answer accuracy** | Correctness | Higher |
| **Latency** | User experience | Lower |

Key patterns:
1. **Multi-dimensional metrics** — success, efficiency, cost, and quality all matter
2. **Per-step tracking** — log every action, token count, latency, and errors
3. **Cost tracking** — total API cost per task; essential for production budgeting
4. **Agent comparison** — benchmark multiple agents on same tasks for fair comparison
5. **Error rate** — how often the agent hits errors; measures robustness of tool use'''
    ),
    (
        "ai/multi-agent-systems",
        "Show multi-agent LLM systems: agent orchestration, delegation, debate, and collaborative problem-solving.",
        '''Multi-agent LLM orchestration:

```python
from dataclasses import dataclass, field
from typing import Callable
from anthropic import Anthropic
import json


@dataclass
class AgentRole:
    name: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)


class MultiAgentOrchestrator:
    """Orchestrate multiple specialized agents working together."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model
        self.agents: dict[str, AgentRole] = {}
        self.conversation_log: list[dict] = []

    def register_agent(self, role: AgentRole):
        self.agents[role.name] = role

    def delegate(self, task: str, agent_name: str, context: str = "") -> str:
        """Delegate task to a specific agent."""
        agent = self.agents[agent_name]
        prompt = f"Context from team:\\n{context}\\n\\nYour task: {task}" if context else task

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.content[0].text
        self.conversation_log.append({
            "agent": agent_name,
            "task": task,
            "result": result,
        })
        return result

    def debate(self, topic: str, agents: list[str], rounds: int = 3) -> dict:
        """Multi-agent debate: agents argue different perspectives."""
        history = []

        for round_num in range(rounds):
            for agent_name in agents:
                context = "\\n".join(
                    f"{h['agent']}: {h['argument']}" for h in history
                )

                prompt = f"Debate topic: {topic}\\n\\n"
                if history:
                    prompt += f"Previous arguments:\\n{context}\\n\\n"
                prompt += "Present your argument. Address counterpoints from others if applicable."

                argument = self.delegate(prompt, agent_name)
                history.append({"agent": agent_name, "round": round_num, "argument": argument})

        # Synthesize final answer
        synthesis = self.delegate(
            f"Synthesize the strongest arguments from this debate into a balanced conclusion:\\n\\n"
            + "\\n".join(f"{h['agent']}: {h['argument']}" for h in history),
            agents[0],  # Use first agent as synthesizer
        )

        return {"debate_history": history, "synthesis": synthesis}

    def pipeline(self, task: str, stages: list[tuple[str, str]]) -> dict:
        """Sequential pipeline: output of one agent feeds into next."""
        context = ""
        results = {}

        for agent_name, stage_prompt in stages:
            full_prompt = f"{stage_prompt}\\n\\nPrevious work:\\n{context}" if context else stage_prompt
            result = self.delegate(full_prompt, agent_name, context)
            results[agent_name] = result
            context = result

        return results

    def parallel_then_merge(self, task: str, workers: list[str],
                             merger: str) -> str:
        """Fan-out to workers, fan-in to merger."""
        # Parallel work (could use asyncio in production)
        worker_results = {}
        for worker_name in workers:
            result = self.delegate(task, worker_name)
            worker_results[worker_name] = result

        # Merge results
        merge_prompt = f"Original task: {task}\\n\\nResults from specialists:\\n"
        for name, result in worker_results.items():
            merge_prompt += f"\\n{name}:\\n{result}\\n"
        merge_prompt += "\\nSynthesize these into a comprehensive final answer."

        return self.delegate(merge_prompt, merger)


# === Setup Example ===

def create_coding_team():
    orchestrator = MultiAgentOrchestrator()

    orchestrator.register_agent(AgentRole(
        name="architect",
        system_prompt="You are a senior software architect. Focus on system design, patterns, and high-level structure.",
    ))
    orchestrator.register_agent(AgentRole(
        name="developer",
        system_prompt="You are an expert developer. Write clean, production-quality code with proper error handling.",
    ))
    orchestrator.register_agent(AgentRole(
        name="reviewer",
        system_prompt="You are a code reviewer. Find bugs, security issues, and suggest improvements.",
    ))
    orchestrator.register_agent(AgentRole(
        name="tester",
        system_prompt="You are a QA engineer. Write comprehensive tests and identify edge cases.",
    ))

    return orchestrator
```

Multi-agent patterns:

| Pattern | Use case | Overhead |
|---------|---------|---------|
| **Pipeline** | Sequential processing | Low |
| **Debate** | Complex reasoning | High |
| **Fan-out/Fan-in** | Parallel analysis | Medium |
| **Delegation** | Specialized tasks | Low |
| **Voting** | Consensus decisions | Medium |

Key patterns:
1. **Specialized roles** — each agent has focused system prompt; domain expertise
2. **Debate protocol** — multiple rounds of argumentation; stronger reasoning on complex topics
3. **Pipeline** — sequential handoff; architect → developer → reviewer → tester
4. **Fan-out/fan-in** — parallel work then merge; faster than sequential for independent subtasks
5. **Context passing** — previous agent output feeds into next; maintains continuity'''
    ),
]
"""
